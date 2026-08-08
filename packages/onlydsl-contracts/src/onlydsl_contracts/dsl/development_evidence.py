"""DevelopmentEvidenceBundleDSL shared by evidence producers and SSOT consumers."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .common import ControlDslError, HASH_RE, ID_RE, canonical_hash, extract_one, json_string, quoted

SCHEMA = "onlydsl.development-evidence/v1"
ASSESSMENTS = {"accepted", "incomplete", "rejected"}
GIT_OBJECT_RE = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
IMMUTABLE_URI_RE = re.compile(r"^urn:[A-Za-z0-9][A-Za-z0-9:._-]*:sha256:[0-9a-f]{64}$")
FIELDS = {
    "SCHEMA", "PROJECT", "REPOSITORY", "REPOSITORY_REVISION", "REPOSITORY_TREE",
    "PRODUCER", "PRODUCER_VERSION", "GRAPH_URI", "DIAGNOSTICS_URI", "MANIFEST_URI",
    "GRAPH_FINGERPRINT", "ASSESSMENT", "BLOCKING_DIAGNOSTICS", "WARNING_DIAGNOSTICS",
    "SEMANTIC_HASH", "EVIDENCE_URI", "AUTHORITY_EFFECT", "MUTATION_EFFECT",
}


@dataclass(frozen=True, slots=True)
class DevelopmentEvidenceBundle:
    id: str
    project_id: str
    repository_id: str
    repository_revision: str
    repository_tree: str
    producer: str
    producer_version: str
    graph_uri: str
    diagnostics_uri: str
    manifest_uri: str
    graph_fingerprint: str
    assessment: str
    blocking_diagnostics: int
    warning_diagnostics: int
    semantic_hash: str
    evidence_uri: str


def _semantic_payload(value: DevelopmentEvidenceBundle) -> dict[str, object]:
    return {
        "schema": SCHEMA,
        "id": value.id,
        "projectId": value.project_id,
        "repositoryId": value.repository_id,
        "repositoryRevision": value.repository_revision,
        "repositoryTree": value.repository_tree,
        "producer": value.producer,
        "producerVersion": value.producer_version,
        "graphUri": value.graph_uri,
        "diagnosticsUri": value.diagnostics_uri,
        "manifestUri": value.manifest_uri,
        "graphFingerprint": value.graph_fingerprint,
        "assessment": value.assessment,
        "blockingDiagnostics": value.blocking_diagnostics,
        "warningDiagnostics": value.warning_diagnostics,
        "authorityEffect": "none",
        "mutationEffect": "none",
    }


def _validate_values(value: DevelopmentEvidenceBundle) -> None:
    for label, identifier in (("bundle", value.id), ("project", value.project_id), ("repository", value.repository_id)):
        if not ID_RE.fullmatch(identifier):
            raise ControlDslError(f"invalid {label} identifier")
    for label, revision in (("repository revision", value.repository_revision), ("repository tree", value.repository_tree)):
        if not GIT_OBJECT_RE.fullmatch(revision):
            raise ControlDslError(f"invalid {label}")
    if value.producer != "todo2code":
        raise ControlDslError("DevelopmentEvidenceBundleDSL producer must be todo2code")
    if not value.producer_version.strip() or any(char in value.producer_version for char in "\r\n"):
        raise ControlDslError("invalid producer version")
    for label, uri in (
        ("graph", value.graph_uri), ("diagnostics", value.diagnostics_uri),
        ("manifest", value.manifest_uri), ("evidence", value.evidence_uri),
    ):
        if not IMMUTABLE_URI_RE.fullmatch(uri):
            raise ControlDslError(f"{label} URI must be an immutable content URN")
    if not HASH_RE.fullmatch(value.graph_fingerprint) or not HASH_RE.fullmatch(value.semantic_hash):
        raise ControlDslError("DevelopmentEvidenceBundleDSL contains an invalid hash")
    if value.assessment not in ASSESSMENTS:
        raise ControlDslError("invalid development evidence assessment")
    if value.blocking_diagnostics < 0 or value.warning_diagnostics < 0:
        raise ControlDslError("diagnostic counts must be non-negative")
    if value.assessment == "accepted" and value.blocking_diagnostics:
        raise ControlDslError("accepted development evidence cannot contain blocking diagnostics")
    if value.assessment == "incomplete" and not value.blocking_diagnostics:
        raise ControlDslError("incomplete development evidence requires a blocking diagnostic")


def create_development_evidence(
    *, bundle_id: str, project_id: str, repository_id: str, repository_revision: str,
    repository_tree: str, producer_version: str, graph_uri: str, diagnostics_uri: str,
    manifest_uri: str, graph_fingerprint: str, assessment: str,
    blocking_diagnostics: int, warning_diagnostics: int,
) -> DevelopmentEvidenceBundle:
    provisional = DevelopmentEvidenceBundle(
        bundle_id, project_id, repository_id, repository_revision, repository_tree,
        "todo2code", producer_version, graph_uri, diagnostics_uri, manifest_uri,
        graph_fingerprint, assessment, blocking_diagnostics, warning_diagnostics,
        "sha256:" + "0" * 64, "urn:onlydsl:development-evidence:sha256:" + "0" * 64,
    )
    _validate_values(provisional)
    semantic_hash = canonical_hash(_semantic_payload(provisional))
    evidence_uri = "urn:onlydsl:development-evidence:" + semantic_hash
    return DevelopmentEvidenceBundle(
        bundle_id, project_id, repository_id, repository_revision, repository_tree,
        "todo2code", producer_version, graph_uri, diagnostics_uri, manifest_uri,
        graph_fingerprint, assessment, blocking_diagnostics, warning_diagnostics,
        semantic_hash, evidence_uri,
    )


def render_development_evidence(value: DevelopmentEvidenceBundle) -> str:
    _validate_values(value)
    expected = create_development_evidence(
        bundle_id=value.id, project_id=value.project_id, repository_id=value.repository_id,
        repository_revision=value.repository_revision, repository_tree=value.repository_tree,
        producer_version=value.producer_version, graph_uri=value.graph_uri,
        diagnostics_uri=value.diagnostics_uri, manifest_uri=value.manifest_uri,
        graph_fingerprint=value.graph_fingerprint, assessment=value.assessment,
        blocking_diagnostics=value.blocking_diagnostics, warning_diagnostics=value.warning_diagnostics,
    )
    if value.semantic_hash != expected.semantic_hash or value.evidence_uri != expected.evidence_uri:
        raise ControlDslError("development evidence semantic identity does not match its content")
    return "\n".join([
        "```developmentevidencedsl",
        f"DEVELOPMENT_EVIDENCE {value.id}",
        f"SCHEMA {SCHEMA}",
        f"PROJECT {value.project_id}",
        f"REPOSITORY {value.repository_id}",
        f"REPOSITORY_REVISION {value.repository_revision}",
        f"REPOSITORY_TREE {value.repository_tree}",
        "PRODUCER todo2code",
        f"PRODUCER_VERSION {quoted(value.producer_version)}",
        f"GRAPH_URI {value.graph_uri}",
        f"DIAGNOSTICS_URI {value.diagnostics_uri}",
        f"MANIFEST_URI {value.manifest_uri}",
        f"GRAPH_FINGERPRINT {value.graph_fingerprint}",
        f"ASSESSMENT {value.assessment}",
        f"BLOCKING_DIAGNOSTICS {value.blocking_diagnostics}",
        f"WARNING_DIAGNOSTICS {value.warning_diagnostics}",
        f"SEMANTIC_HASH {value.semantic_hash}",
        f"EVIDENCE_URI {value.evidence_uri}",
        "AUTHORITY_EFFECT none",
        "MUTATION_EFFECT none",
        "END_DEVELOPMENT_EVIDENCE",
        "```",
    ])


def parse_development_evidence(markdown: str) -> DevelopmentEvidenceBundle:
    lines = [line.strip() for line in extract_one(markdown, "developmentevidencedsl").splitlines() if line.strip()]
    if not lines or not lines[0].startswith("DEVELOPMENT_EVIDENCE ") or lines[-1] != "END_DEVELOPMENT_EVIDENCE":
        raise ControlDslError("invalid DevelopmentEvidenceBundleDSL envelope")
    bundle_id = lines[0].split(None, 1)[1]
    fields: dict[str, str] = {}
    for line in lines[1:-1]:
        key, separator, raw = line.partition(" ")
        if not separator or key not in FIELDS or key in fields:
            raise ControlDslError(f"invalid or duplicate development evidence field {key!r}")
        fields[key] = raw
    if set(fields) != FIELDS:
        raise ControlDslError(f"DevelopmentEvidenceBundleDSL fields differ: {sorted(FIELDS - fields.keys())}")
    if fields["SCHEMA"] != SCHEMA:
        raise ControlDslError("unsupported DevelopmentEvidenceBundleDSL schema")
    if fields["AUTHORITY_EFFECT"] != "none" or fields["MUTATION_EFFECT"] != "none":
        raise ControlDslError("development evidence cannot grant authority or mutation")
    try:
        blocking = int(fields["BLOCKING_DIAGNOSTICS"])
        warnings = int(fields["WARNING_DIAGNOSTICS"])
    except ValueError as exc:
        raise ControlDslError("diagnostic counts must be integers") from exc
    value = DevelopmentEvidenceBundle(
        bundle_id, fields["PROJECT"], fields["REPOSITORY"], fields["REPOSITORY_REVISION"],
        fields["REPOSITORY_TREE"], fields["PRODUCER"],
        json_string(fields["PRODUCER_VERSION"], "PRODUCER_VERSION"),
        fields["GRAPH_URI"], fields["DIAGNOSTICS_URI"], fields["MANIFEST_URI"],
        fields["GRAPH_FINGERPRINT"], fields["ASSESSMENT"], blocking, warnings,
        fields["SEMANTIC_HASH"], fields["EVIDENCE_URI"],
    )
    _validate_values(value)
    expected = create_development_evidence(
        bundle_id=value.id, project_id=value.project_id, repository_id=value.repository_id,
        repository_revision=value.repository_revision, repository_tree=value.repository_tree,
        producer_version=value.producer_version, graph_uri=value.graph_uri,
        diagnostics_uri=value.diagnostics_uri, manifest_uri=value.manifest_uri,
        graph_fingerprint=value.graph_fingerprint, assessment=value.assessment,
        blocking_diagnostics=value.blocking_diagnostics, warning_diagnostics=value.warning_diagnostics,
    )
    if value.semantic_hash != expected.semantic_hash or value.evidence_uri != expected.evidence_uri:
        raise ControlDslError("development evidence semantic identity does not match its content")
    return value


__all__ = [
    "ASSESSMENTS", "DevelopmentEvidenceBundle", "create_development_evidence",
    "parse_development_evidence", "render_development_evidence",
]
