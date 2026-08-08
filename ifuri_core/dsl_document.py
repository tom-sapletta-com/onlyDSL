from __future__ import annotations

import hashlib

from . import dsl_pb2


class DslDocumentError(ValueError):
    pass


_SUPPORTED = {
    "contextdsl", "intentdsl", "sourcedsl", "contractdsl", "taskdsl",
    "twindsl", "sourceindexdsl", "buildplanddsl", "dslbundle", "validationdsl",
}


def make_dsl_document(dsl_type: str, markdown: str, schema_version: int = 1) -> dsl_pb2.DslDocument:
    normalized_type = str(dsl_type).strip().lower()
    if normalized_type not in _SUPPORTED:
        raise DslDocumentError(f"unsupported DSL type: {dsl_type}")
    digest = hashlib.sha256(markdown.encode("utf-8")).hexdigest()
    return dsl_pb2.DslDocument(
        schema_version=int(schema_version),
        dsl_type=normalized_type,
        markdown=markdown,
        sha256=digest,
    )


def validate_dsl_document(doc: dsl_pb2.DslDocument) -> None:
    if doc.schema_version != 1:
        raise DslDocumentError(f"unsupported DSL schema version: {doc.schema_version}")
    if doc.dsl_type not in _SUPPORTED:
        raise DslDocumentError(f"unsupported DSL type: {doc.dsl_type}")
    expected = hashlib.sha256(doc.markdown.encode("utf-8")).hexdigest()
    if not doc.sha256 or doc.sha256 != expected:
        raise DslDocumentError("DSL document digest mismatch")
