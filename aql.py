from __future__ import annotations

import fnmatch
import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


class AqlError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class AqlDecision:
    allowed: bool
    principal: str
    oql: str
    uri_process: str
    reason: str
    contract: str
    contract_sha256: str


class AqlContract:
    """Small compatible reader for Subactor's canonical aql:contract/v1 profile."""

    def __init__(self, fields: dict[str, str], repeated: dict[str, tuple[str, ...]], source: str):
        self.fields = fields
        self.repeated = repeated
        self.source = source
        self.sha256 = "sha256:" + hashlib.sha256(source.encode("utf-8")).hexdigest()

    @classmethod
    def parse(cls, text: str) -> "AqlContract":
        fields: dict[str, str] = {}
        repeated: dict[str, list[str]] = {
            "ALLOW MODEL": [], "ALLOW OQL": [], "ALLOW URI_PROCESS": [],
            "ALLOW ACCESS": [], "ALLOW VARIABLE": [],
        }
        for number, raw in enumerate(text.splitlines(), 1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            matched = False
            for directive in repeated:
                prefix = directive + " "
                if line.startswith(prefix):
                    repeated[directive].append(line[len(prefix):].strip())
                    matched = True
                    break
            if matched:
                continue
            parts = line.split(None, 1)
            if len(parts) != 2:
                raise AqlError(f"invalid AQL line {number}: {line!r}")
            key, value = parts
            if key in {"PROFILE", "VERSION", "CONTRACT", "DELEGATED_BY", "PRINCIPAL", "EXPIRES"}:
                fields[key] = value.strip()
            elif key in {"LIMIT", "REQUIRE", "ALLOW"}:
                # Retain canonical directives not evaluated by this narrow runtime.
                fields[f"{key}:{number}"] = value.strip()
            else:
                raise AqlError(f"unknown AQL directive at line {number}: {key}")
        required = {"PROFILE", "VERSION", "CONTRACT", "DELEGATED_BY", "PRINCIPAL", "EXPIRES"}
        missing = sorted(required - fields.keys())
        if missing:
            raise AqlError("missing AQL fields: " + ", ".join(missing))
        if fields["PROFILE"] != "aql:contract/v1" or fields["VERSION"] != "1":
            raise AqlError("only PROFILE aql:contract/v1 VERSION 1 is supported")
        if not fields["DELEGATED_BY"].startswith("organization:"):
            raise AqlError("DELEGATED_BY must name an organization authority")
        return cls(fields, {key: tuple(value) for key, value in repeated.items()}, text)

    @classmethod
    def from_file(cls, path: str | Path) -> "AqlContract":
        return cls.parse(Path(path).read_text(encoding="utf-8"))

    @staticmethod
    def _matches(value: str, patterns: tuple[str, ...]) -> bool:
        return any(fnmatch.fnmatchcase(value, pattern) for pattern in patterns)

    def decide(self, principal: str, oql: str, uri_process: str, *, now: datetime | None = None) -> AqlDecision:
        reason = "allowed"
        allowed = True
        if principal != self.fields["PRINCIPAL"]:
            allowed, reason = False, "principal_mismatch"
        else:
            try:
                expires = datetime.fromisoformat(self.fields["EXPIRES"].replace("Z", "+00:00"))
            except ValueError:
                allowed, reason = False, "invalid_expiry"
            else:
                current = now or datetime.now(timezone.utc)
                if expires.tzinfo is None:
                    expires = expires.replace(tzinfo=timezone.utc)
                if current >= expires:
                    allowed, reason = False, "contract_expired"
        if allowed and not self._matches(oql, self.repeated["ALLOW OQL"]):
            allowed, reason = False, "oql_not_granted"
        if allowed and not self._matches(uri_process, self.repeated["ALLOW URI_PROCESS"]):
            allowed, reason = False, "uri_process_not_granted"
        return AqlDecision(
            allowed, principal, oql, uri_process, reason,
            self.fields["CONTRACT"], self.sha256,
        )

    def require(self, principal: str, oql: str, uri_process: str) -> AqlDecision:
        decision = self.decide(principal, oql, uri_process)
        if not decision.allowed:
            raise AqlError(f"AQL denied {oql} through {uri_process}: {decision.reason}")
        return decision

    def require_secret_rotation(self, principal: str, secret_ref: str) -> AqlDecision:
        if not secret_ref.startswith("secret:") or any(char.isspace() for char in secret_ref):
            raise AqlError("secret rotation requires an opaque secret:<id> reference")
        decision = self.require(principal, "secret.rotate", "vault://workspace/secret/command/rotate")
        if not self._matches(f"ROTATE {secret_ref}", self.repeated["ALLOW ACCESS"]):
            raise AqlError(f"AQL did not grant ROTATE for {secret_ref}")
        variable_ref = "secret-ref:" + secret_ref.split(":", 1)[1]
        if not self._matches(f"WRITE {variable_ref}", self.repeated["ALLOW VARIABLE"]):
            raise AqlError(f"AQL did not grant WRITE for {variable_ref}")
        return decision

    def public_status(self) -> dict:
        return {
            "profile": self.fields["PROFILE"],
            "contract": self.fields["CONTRACT"],
            "principal": self.fields["PRINCIPAL"],
            "expires": self.fields["EXPIRES"],
            "sha256": self.sha256,
            "allowed_oql": list(self.repeated["ALLOW OQL"]),
            "allowed_uri_process": list(self.repeated["ALLOW URI_PROCESS"]),
            "allowed_access": list(self.repeated["ALLOW ACCESS"]),
        }


PATH_ROUTES = (
    ((".env", "secrets/"), "secret.rotate", "vault://workspace/secret/command/rotate"),
    (("requirements.txt", "pyproject.toml", "package.json", "package-lock.json"), "dependency.change", "repo://workspace/dependency/command/patch"),
    (("Dockerfile", "Dockerfile.", "docker-compose.yml", "compose.yml"), "docker.change", "repo://workspace/docker/command/patch"),
    (("runtime/",), "runtime.change", "repo://workspace/runtime/command/patch"),
    (("evolution.py", "patchdsl.py", "aql.py", "scripts/autonomous_repair.py", "scripts/live_supervisor.py", "config/process-packs/", "config/contracts/"), "evolution.change", "repo://workspace/evolution/command/patch"),
)


def operation_for_path(path: str) -> tuple[str, str]:
    for patterns, oql, uri in PATH_ROUTES:
        if any(path == pattern or (pattern.endswith(("/", ".")) and path.startswith(pattern)) for pattern in patterns):
            return oql, uri
    return "code.change", "repo://workspace/source/command/patch"
