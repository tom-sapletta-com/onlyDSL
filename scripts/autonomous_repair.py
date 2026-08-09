from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aql import AqlContract, operation_for_path  # noqa: E402
from boundary import assert_dsl_only, code_dsl  # noqa: E402
from evolution import EvolutionStore  # noqa: E402
from governance import authorize_patch, build_process_envelope, complete_envelope, load_process_pack, reject_envelope  # noqa: E402
from ifuri_core.dsl_document import make_dsl_document  # noqa: E402
from ifuri_core.dsl_pb2 import DslDocument  # noqa: E402
from ifuri_core.envelope import EnvelopeCodec  # noqa: E402
from ifuri_core.llm_gateway import build_llm_patch_handler  # noqa: E402
from ifuri_core.manifest import CapabilityRegistry  # noqa: E402
from ifuri_core.runtime import IfuriRuntime  # noqa: E402
from ifuri_core.transport import InProcessTransport  # noqa: E402
from patchdsl import PatchDocument, parse_patchdsl, validate_patch_policy  # noqa: E402


class RepairError(RuntimeError):
    pass


class AutonomousRepairAgent:
    def __init__(self, workspace: str | Path | None = None, store: EvolutionStore | None = None):
        self.workspace = Path(workspace or os.getenv("EVOLUTION_WORKSPACE", ROOT)).resolve()
        self.store = store or EvolutionStore(os.getenv("EVOLUTION_STATE_DIR", self.workspace / "runtime/evolution"))
        self.mode = os.getenv("EVOLUTION_MODE", "observe").lower()
        self.backend = os.getenv("EVOLUTION_LLM_BACKEND", "openrouter")
        self.health_url = os.getenv("EVOLUTION_HEALTH_URL", "http://live-app:8787/api/health")
        self.poll_seconds = max(0.2, float(os.getenv("EVOLUTION_POLL_SECONDS", "2")))
        self.test_timeout = max(10, int(os.getenv("EVOLUTION_TEST_TIMEOUT_SECONDS", "180")))
        contract_path = os.getenv(
            "EVOLUTION_AQL_CONTRACT",
            str(ROOT / "config/contracts/evolution-agent.contract.aql"),
        )
        self.contract = AqlContract.from_file(contract_path)
        self.process_pack = load_process_pack(ROOT)

    def _candidate_files(self, incident: str) -> dict[str, str]:
        candidates: list[str] = []
        for raw in re.findall(r'(?:/app/|/workspace/)?([A-Za-z0-9_./-]+\.(?:py|html|js|mjs|ts|ya?ml))', incident):
            path = raw.lstrip("/")
            if path.startswith(("app/", "workspace/")):
                path = path.split("/", 1)[1]
            if path not in candidates:
                candidates.append(path)
        if not candidates:
            candidates.append("server.py")
        files: dict[str, str] = {}
        budget = max(8000, int(os.getenv("EVOLUTION_MAX_CODE_CHARS", "60000")))
        for rel in candidates[:6]:
            target = (self.workspace / rel).resolve()
            try:
                target.relative_to(self.workspace)
            except ValueError:
                continue
            if not target.is_file() or rel == ".env" or rel.startswith((
                "state/", ".git/", "secrets/", "config/contracts/", "config/process-packs/",
            )) or rel in {"aql.py", "diagnostics.py", "governance.py", "patchdsl.py", "scripts/autonomous_repair.py"}:
                continue
            content = target.read_text(encoding="utf-8", errors="replace")
            if len(content) > budget:
                content = content[:budget]
            files[rel] = content
            budget -= len(content)
            if budget <= 0:
                break
        if not files:
            raise RepairError("incident does not identify an existing repairable source file")
        return files

    def _git_apply(self, patch: str, *, check: bool = False) -> None:
        command = ["git", "apply", "--whitespace=error-all"]
        if check:
            command.append("--check")
        result = subprocess.run(
            command,
            cwd=self.workspace,
            input=patch,
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
        if result.returncode:
            raise RepairError(f"git apply {'check ' if check else ''}failed: {(result.stderr or result.stdout)[:2000]}")

    def _propose(self, incident: str, guidance: list[str], code_files: dict[str, str], diagnostic: str = "") -> dict:
        verification: list[str] = []
        match = re.search(r'^FIELD testqldsl\s+(".*")$', incident, re.M)
        if match:
            try:
                name = json.loads(match.group(1))
                path = self.store.testql / Path(str(name)).name
                if path.is_file():
                    verification.append(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        # Authority is projected by the system only after the model returns a proposal.
        # The model sees incident/evidence/code, never a writable or copyable grant surface.
        markdown = "\n".join([*guidance, *verification, incident, diagnostic, *(code_dsl(path, content) for path, content in sorted(code_files.items()))])
        assert_dsl_only(markdown, {"guidancedsl", "testqldsl", "incidentdsl", "diagnosticdsl", "codedsl"})
        registry = CapabilityRegistry.from_file(self.workspace / "manifests" / "capabilities.yaml")
        transport = InProcessTransport()
        transport.register("llm.repair.propose", build_llm_patch_handler(self.backend))
        runtime = IfuriRuntime(registry, {"inproc": transport})
        reply, route = asyncio.run(runtime.call(
            "ifuri://llm/repair/default/commands/propose",
            make_dsl_document("dslbundle", markdown),
            source_uri="ifuri://evolution/repair/default/commands/request",
        ))
        output = DslDocument()
        EnvelopeCodec.unpack(reply, output)
        usage = {}
        try:
            usage = json.loads(reply.metadata.get("usage", "{}"))
        except (TypeError, ValueError):
            pass
        return {
            "markdown": output.markdown,
            "usage": usage,
            "repair_attempts": int(reply.metadata.get("repair_attempts", "0")),
            "route": route.to_dict(),
        }

    def _backup(self, doc: PatchDocument) -> Path:
        backup = self.store.backups / doc.patch_id
        if backup.exists():
            raise RepairError(f"backup already exists for patch {doc.patch_id}")
        backup.mkdir(parents=True)
        manifest: dict[str, str] = {}
        for change in doc.changes:
            source = self.workspace / change.path
            target = backup / change.path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            manifest[change.path] = "sha256:" + hashlib.sha256(source.read_bytes()).hexdigest()
        (backup / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return backup

    def _restore(self, doc: PatchDocument, backup: Path) -> None:
        for change in doc.changes:
            saved = backup / change.path
            target = self.workspace / change.path
            if saved.is_file():
                shutil.copy2(saved, target)

    def _tests(self) -> tuple[bool, str]:
        result = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
            cwd=self.workspace,
            text=True,
            capture_output=True,
            timeout=self.test_timeout,
            check=False,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        output = (result.stdout + "\n" + result.stderr)[-12000:]
        return result.returncode == 0, output

    def _wait_for_health(self, timeout: float = 45) -> tuple[bool, str]:
        deadline = time.monotonic() + timeout
        last = "no response"
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(self.health_url, timeout=3) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                    if response.status == 200 and payload.get("ok") is True:
                        return True, f"HTTP {response.status} ok"
                    last = f"HTTP {response.status}: {str(payload)[:500]}"
            except (urllib.error.URLError, TimeoutError, ValueError) as exc:
                last = str(exc)
            time.sleep(1)
        return False, last

    def process_once(self) -> bool:
        if os.getenv("EVOLUTION_ENABLED", "0") != "1":
            return False
        if self.mode != "apply":
            return False
        incident_path = self.store.claim_incident()
        if incident_path is None:
            return False
        incident = incident_path.read_text(encoding="utf-8")
        incident_id = incident_path.name.split("-", 1)[-1].split(".", 1)[0]
        self.store.add_event("repair_started", {"incident_id": incident_id, "backend": self.backend})
        success = False
        deferred = False
        backup: Path | None = None
        doc: PatchDocument | None = None
        envelope: dict | None = None
        try:
            diagnostic = self.store.diagnostic_for_incident(incident_id)
            if not diagnostic:
                diagnostic = self.store.add_diagnostic(incident_id, incident)["markdown"]
            action_match = re.search(r"^ACTION\s+(\S+)", diagnostic, re.M)
            code_match = re.search(r"^ERROR_CODE\s+(\S+)", diagnostic, re.M)
            diagnostic_action = action_match.group(1) if action_match else "manual"
            error_code = code_match.group(1) if code_match else "UNKNOWN"
            if diagnostic_action in {"defer", "manual"}:
                deferred = True
                self.store.add_event("repair_deferred", {
                    "incident_id": incident_id,
                    "error_code": error_code,
                    "action": diagnostic_action,
                    "reason": "diagnostic_policy_forbids_automatic_patch",
                })
                return True
            code_files = self._candidate_files(incident + "\n" + diagnostic)
            result = self._propose(incident, self.store.latest_guidance(), code_files, diagnostic)
            patch_markdown = result["markdown"]
            patch_path = self.store._write(self.store.patches, incident_id, "patchdsl", patch_markdown)
            doc = parse_patchdsl(patch_markdown)
            errors = validate_patch_policy(doc, self.workspace)
            if errors:
                raise RepairError("patch policy rejected: " + "; ".join(errors))
            decisions = authorize_patch(doc, self.contract)
            preflight = {
                "files": [{"path": change.path, "sha256": change.base_sha256} for change in doc.changes],
                "aql_contract_sha256": self.contract.sha256,
            }
            envelope = build_process_envelope(
                incident_id=incident_id, doc=doc, contract=self.contract,
                decisions=decisions, process_pack=self.process_pack, preflight=preflight,
            )
            envelope_path = self.store.add_json_record("envelope", doc.patch_id, envelope)
            combined = "".join(change.diff for change in doc.changes)
            self._git_apply(combined, check=True)
            backup = self._backup(doc)
            self._git_apply(combined)
            self.store.add_event("patch_applied", {
                "incident_id": incident_id,
                "patch_id": doc.patch_id,
                "patch_file": patch_path.name,
                "files": [change.path for change in doc.changes],
                "repair_attempts": result.get("repair_attempts", 0),
                "usage": result.get("usage", {}),
                "process_envelope": envelope_path.name,
            })
            tests_ok, test_output = self._tests()
            if not tests_ok:
                raise RepairError("test suite failed: " + test_output)
            health_ok, health_detail = self._wait_for_health()
            if not health_ok:
                raise RepairError("live healthcheck failed: " + health_detail)
            verified = complete_envelope(envelope, tests="unit-test-process:exit-0", health=health_detail)
            self.store.add_json_record("envelope", doc.patch_id + "-verified", verified)
            receipt_path = self.store.add_json_record("receipt", doc.patch_id, verified["receipt"])
            self.store.add_event("repair_verified", {
                "incident_id": incident_id,
                "patch_id": doc.patch_id,
                "health": health_detail,
                "receipt": receipt_path.name,
            })
            success = True
        except Exception as exc:
            if doc is not None and backup is not None:
                self._restore(doc, backup)
                rollback_ok, rollback_health = self._wait_for_health()
                self.store.add_event("patch_rolled_back", {
                    "incident_id": incident_id,
                    "patch_id": doc.patch_id,
                    "health_restored": rollback_ok,
                    "health": rollback_health,
                })
            if envelope is not None and doc is not None:
                rejected = reject_envelope(envelope, reason=str(exc), rolled_back=backup is not None)
                self.store.add_json_record("envelope", doc.patch_id + "-failed", rejected)
                self.store.add_json_record("receipt", doc.patch_id + "-failed", rejected["receipt"])
            self.store.add_event("repair_failed", {
                "incident_id": incident_id,
                "error_type": type(exc).__name__,
                "message": str(exc)[:8000],
            })
        finally:
            if deferred:
                self.store.defer_incident(incident_path)
            else:
                self.store.finish_incident(incident_path, success=success)
        return True

    def run(self, *, once: bool = False) -> int:
        self.store.add_event("repair_agent_started", {
            "mode": self.mode,
            "backend": self.backend,
            "workspace": str(self.workspace),
        })
        if once:
            self.process_once()
            return 0
        while True:
            processed = self.process_once()
            if not processed:
                time.sleep(self.poll_seconds)


def main() -> int:
    parser = argparse.ArgumentParser(description="Guarded DSL autonomous repair agent")
    parser.add_argument("--once", action="store_true", help="process at most one queued incident")
    args = parser.parse_args()
    return AutonomousRepairAgent().run(once=args.once)


if __name__ == "__main__":
    raise SystemExit(main())
