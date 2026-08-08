from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from aql import AqlContract, AqlDecision, operation_for_path
from patchdsl import PatchDocument


def canonical_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def load_process_pack(root: str | Path) -> dict[str, Any]:
    directory = Path(root) / "config/process-packs/live-evolution"
    pack = {}
    for name in ("process.v1.json", "operations.v1.oql.json", "recipe.v1.urirun.json", "expectations.v1.eql.json"):
        pack[name] = json.loads((directory / name).read_text(encoding="utf-8"))
    return pack


def authorize_patch(doc: PatchDocument, contract: AqlContract) -> list[AqlDecision]:
    decisions = []
    for change in doc.changes:
        if change.path == ".env" or change.path.startswith("secrets/"):
            raise ValueError("secret values cannot cross PatchDSL; use a bound secret reference and vault rotation route")
        oql, uri = operation_for_path(change.path)
        decisions.append(contract.require("bot:evolution-agent", oql, uri))
    return decisions


def build_process_envelope(
    *, incident_id: str, doc: PatchDocument, contract: AqlContract,
    decisions: list[AqlDecision], process_pack: dict[str, Any], preflight: dict[str, Any],
) -> dict[str, Any]:
    proposal = {
        "patch_id": doc.patch_id,
        "summary": doc.summary,
        "changes": [{"path": c.path, "base_sha256": c.base_sha256} for c in doc.changes],
    }
    proposal_hash = canonical_hash(proposal)
    pack_hash = canonical_hash(process_pack)
    return {
        "schema": "subactor.process-envelope.v2",
        "state": "authorized",
        "principal": "bot:evolution-agent",
        "incident_id": incident_id,
        "proposal": proposal,
        "proposal_hash": proposal_hash,
        "acceptance": {
            "kind": "prior_policy_grant",
            "bound_proposal_hash": proposal_hash,
            "aql_contract_hash": contract.sha256,
            "process_pack_hash": pack_hash,
        },
        "doql": {"profile": "doql:runtime-facts/v1", "read_only": True, "facts": preflight},
        "aql": [asdict(decision) for decision in decisions],
        "oql": sorted({operation_for_path(c.path)[0] for c in doc.changes}),
        "uri_process": sorted({operation_for_path(c.path)[1] for c in doc.changes}),
        "eql": {"profile": "eql:expectation/v1", "read_only": True, "status": "pending"},
    }


def complete_envelope(envelope: dict[str, Any], *, tests: str, health: str) -> dict[str, Any]:
    result = json.loads(json.dumps(envelope))
    result["state"] = "verified"
    result["eql"] = {
        "profile": "eql:expectation/v1", "read_only": True, "status": "green",
        "evidence": {"tests": tests, "health": health},
    }
    result["receipt"] = {
        "profile": "sodl:subactor-observation/v1",
        "result": "verified",
        "envelope_hash": canonical_hash({k: v for k, v in result.items() if k != "receipt"}),
    }
    return result


def reject_envelope(envelope: dict[str, Any], *, reason: str, rolled_back: bool) -> dict[str, Any]:
    result = json.loads(json.dumps(envelope))
    result["state"] = "rolled_back" if rolled_back else "rejected"
    result["eql"] = {
        "profile": "eql:expectation/v1", "read_only": True, "status": "red",
        "evidence": {"reason": reason[:2000]},
    }
    result["receipt"] = {
        "profile": "sodl:subactor-observation/v1",
        "result": result["state"],
        "envelope_hash": canonical_hash({k: v for k, v in result.items() if k != "receipt"}),
    }
    return result
