from __future__ import annotations

from dataclasses import dataclass

from aql import AqlContract, AqlDecision
from onlydsl.dsl.common import canonical_hash


@dataclass(frozen=True, slots=True)
class AuthorityProjection:
    id: str
    contract_hash: str
    principal: str
    twin_id: str
    from_revision: int
    decisions: tuple[AqlDecision, ...]
    required_verification: tuple[str, ...]


def project_authority(
    contract: AqlContract, *, twin_id: str, from_revision: int,
    operations: list[tuple[str, str]], principal: str = "bot:evolution-agent",
) -> AuthorityProjection:
    decisions = tuple(contract.require(principal, oql, uri) for oql, uri in operations)
    projection_id = "authority-" + canonical_hash({
        "contract": contract.sha256, "twin": twin_id, "revision": from_revision,
        "operations": operations,
    }).split(":")[-1][:16]
    return AuthorityProjection(
        projection_id, contract.sha256, principal, twin_id, from_revision, decisions,
        ("testql.verify", "eql.verify", "independent-evaluator.verify"),
    )


def render_authority_projection(value: AuthorityProjection) -> str:
    rows = [
        "```authorityprojectiondsl", f"AUTHORITY_PROJECTION {value.id}",
        f"CONTRACT_HASH {value.contract_hash}", f"PRINCIPAL {value.principal}",
        f"TWIN {value.twin_id}", f"FROM_REVISION {value.from_revision}",
        "OWNERSHIP system", "NOTE model_cannot_create_or_modify_authority",
    ]
    for decision in value.decisions:
        rows.append(f"ALLOW {decision.oql} VIA {decision.uri_process}")
    rows.extend(f"REQUIRE_VERIFICATION {item}" for item in value.required_verification)
    rows.extend(["END_AUTHORITY_PROJECTION", "```"])
    return "\n".join(rows)
