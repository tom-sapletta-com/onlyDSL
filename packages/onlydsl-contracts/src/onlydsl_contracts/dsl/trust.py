"""TrustDSL contract."""

from __future__ import annotations

from dataclasses import dataclass

from .common import ControlDslError, extract_one, list_value, parse_json_list


@dataclass(frozen=True, slots=True)
class TrustRole:
    id: str
    priority: int
    can_define: frozenset[str]


@dataclass(frozen=True, slots=True)
class TrustPolicy:
    id: str
    roles: dict[str, TrustRole]

    def priority_for(self, role: str, domain: str) -> int | None:
        value = self.roles.get(role)
        return value.priority if value and domain in value.can_define else None


def parse_trust_policy(markdown: str) -> TrustPolicy:
    lines = [line.strip() for line in extract_one(markdown, "trustdsl").splitlines() if line.strip()]
    if not lines or not lines[0].startswith("TRUST_POLICY ") or lines[-1] != "END_TRUST_POLICY":
        raise ControlDslError("invalid TrustDSL envelope")
    roles: dict[str, TrustRole] = {}
    index = 1
    while index < len(lines) - 1:
        if not lines[index].startswith("ROLE "):
            raise ControlDslError(f"expected ROLE, got {lines[index]!r}")
        role_id = lines[index].split(None, 1)[1]
        fields: dict[str, str] = {}
        index += 1
        while index < len(lines) and lines[index] != "END_ROLE":
            key, _, value = lines[index].partition(" ")
            if key not in {"PRIORITY", "CAN_DEFINE"} or key in fields:
                raise ControlDslError(f"invalid TrustDSL field {key!r}")
            fields[key] = value
            index += 1
        if set(fields) != {"PRIORITY", "CAN_DEFINE"} or role_id in roles:
            raise ControlDslError(f"role {role_id} is duplicate or incomplete")
        priority = int(fields["PRIORITY"])
        domains = frozenset(parse_json_list(fields["CAN_DEFINE"], "CAN_DEFINE"))
        if not 0 <= priority <= 100 or not domains:
            raise ControlDslError(f"role {role_id} requires priority 0..100 and domains")
        roles[role_id] = TrustRole(role_id, priority, domains)
        index += 1
    return TrustPolicy(lines[0].split(None, 1)[1], roles)


def render_trust_policy(policy: TrustPolicy) -> str:
    rows = ["```trustdsl", f"TRUST_POLICY {policy.id}"]
    for role in policy.roles.values():
        rows.extend([
            f"ROLE {role.id}", f"  PRIORITY {role.priority}",
            f"  CAN_DEFINE {list_value(sorted(role.can_define))}", "END_ROLE",
        ])
    rows.extend(["END_TRUST_POLICY", "```"])
    return "\n".join(rows)
