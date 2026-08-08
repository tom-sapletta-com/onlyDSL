from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from source_ingest import build_source_index

from onlydsl_contracts.ssot import PromotionApproval, SsotError
from .registry import ProjectRegistry
from .writer import SsotStore


def _updates(values: list[str]) -> dict[str, bytes]:
    result: dict[str, bytes] = {}
    for value in values:
        relative, separator, source = value.partition("=")
        if not separator or not relative or not source:
            raise ValueError(f"--section requires RELATIVE_PATH=SOURCE_FILE, got {value!r}")
        result[relative] = Path(source).read_bytes()
    return result


def _json(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="onlydsl ssot", description="Single Source of Accepted Truth control plane")
    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init")
    init.add_argument("root", nargs="?", default=".")
    init.add_argument("--project-id", required=True)
    init.add_argument("--project-dsl")

    for name in ("status", "verify", "history"):
        command = commands.add_parser(name)
        command.add_argument("root", nargs="?", default=".")

    scan = commands.add_parser("scan")
    scan.add_argument("root", nargs="?", default=".")
    scan.add_argument("--source-root", default="sources")
    scan.add_argument("--id")

    candidate = commands.add_parser("candidate")
    candidate_commands = candidate.add_subparsers(dest="candidate_command", required=True)
    create = candidate_commands.add_parser("create")
    create.add_argument("root", nargs="?", default=".")
    create.add_argument("--id")
    create.add_argument("--section", action="append", default=[])
    create.add_argument("--remove", action="append", default=[])
    create.add_argument("--evidence", action="append", default=[])
    validate = candidate_commands.add_parser("validate")
    validate.add_argument("candidate_id")
    validate.add_argument("root", nargs="?", default=".")

    diff = commands.add_parser("diff")
    diff.add_argument("candidate_id")
    diff.add_argument("root", nargs="?", default=".")

    reconcile = commands.add_parser("reconcile")
    reconcile.add_argument("root", nargs="?", default=".")
    reconcile.add_argument("--id")
    reconcile.add_argument("--section", action="append", default=[])
    reconcile.add_argument("--remove", action="append", default=[])
    reconcile.add_argument("--evidence", action="append", default=[])

    promote = commands.add_parser("promote")
    promote.add_argument("candidate_id")
    promote.add_argument("root", nargs="?", default=".")
    promote.add_argument("--authority-hash", required=True)
    promote.add_argument("--testql", action="append", required=True)
    promote.add_argument("--eql", action="append", required=True)
    promote.add_argument("--integrity", choices=["pass", "fail"], default="pass")
    promote.add_argument("--completeness", choices=["complete", "incomplete"], default="complete")
    promote.add_argument("--allow-incomplete", action="store_true")

    registry = commands.add_parser("registry")
    registry_commands = registry.add_subparsers(dest="registry_command", required=True)
    add = registry_commands.add_parser("add")
    add.add_argument("root", nargs="?", default=".")
    add.add_argument("--registry")
    listing = registry_commands.add_parser("list")
    listing.add_argument("--registry")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "init":
            manifest = SsotStore(args.root).initialize(args.project_id, project_dsl=args.project_dsl)
            _json({"status": "initialized", "revision": manifest.revision_hash, "ssot": str(SsotStore(args.root).ssot_root)})
        elif args.command in {"status", "verify"}:
            store = SsotStore(args.root)
            _json(store.status() | {"verified": True})
        elif args.command == "scan":
            store = SsotStore(args.root)
            source_root = Path(args.source_root)
            if not source_root.is_absolute():
                source_root = Path(args.root) / source_root
            index = build_source_index(source_root)
            envelope = index.envelope()
            content_hash = envelope["contentHash"]
            value = store.create_candidate(
                updates={"sources/source-index.dsl": envelope["sourceIndexDSL"].encode("utf-8")},
                candidate_id=args.id,
                evidence_uris=("urn:subactor:source-index:" + content_hash,),
            )
            report = store.validate_candidate(value.candidate_id)
            _json({
                "candidate_id": value.candidate_id, "ok": report.ok,
                "content_hash": content_hash, "generated_at": envelope["generatedAt"],
                "documents": len(index.documents), "issues": report.issues,
            })
            return 0 if report.ok else 2
        elif args.command == "history":
            values = SsotStore(args.root).history()
            _json({"revisions": [{"revision": item.revision_hash, "parent": item.parent_hash, "created_at": item.created_at} for item in values]})
        elif args.command == "candidate" and args.candidate_command == "create":
            value = SsotStore(args.root).create_candidate(
                updates=_updates(args.section), removals=tuple(args.remove),
                candidate_id=args.id, evidence_uris=tuple(args.evidence),
            )
            _json({"candidate_id": value.candidate_id, "base_revision": value.base_revision, "state": value.state})
        elif args.command == "candidate" and args.candidate_command == "validate":
            report = SsotStore(args.root).validate_candidate(args.candidate_id)
            _json({"candidate_id": report.candidate_id, "ok": report.ok, "issues": report.issues, "candidate_revision": report.candidate_revision})
            return 0 if report.ok else 2
        elif args.command == "diff":
            print(SsotStore(args.root).candidate_diff(args.candidate_id), end="")
        elif args.command == "reconcile":
            store = SsotStore(args.root)
            value = store.create_candidate(
                updates=_updates(args.section), removals=tuple(args.remove),
                candidate_id=args.id, evidence_uris=tuple(args.evidence),
            )
            report = store.validate_candidate(value.candidate_id)
            print(store.candidate_diff(value.candidate_id), end="")
            if not report.ok:
                return 2
        elif args.command == "promote":
            manifest = SsotStore(args.root).promote(args.candidate_id, PromotionApproval(
                args.authority_hash, tuple(args.testql), tuple(args.eql), args.integrity,
                args.completeness, args.allow_incomplete,
            ))
            _json({"status": "accepted", "revision": manifest.revision_hash, "parent": manifest.parent_hash})
        elif args.command == "registry" and args.registry_command == "add":
            _json(asdict(ProjectRegistry(args.registry).register(args.root)))
        elif args.command == "registry" and args.registry_command == "list":
            _json({"projects": [asdict(entry) for entry in ProjectRegistry(args.registry).entries()]})
        else:
            raise ValueError("unsupported SSOT command")
        return 0
    except (SsotError, ValueError, OSError) as exc:
        _json({"error": type(exc).__name__, "message": str(exc)})
        return 2
