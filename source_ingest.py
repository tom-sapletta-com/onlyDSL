from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class SourceIngestError(ValueError):
    pass


def _q(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _sid(path: Path, index: int = 0) -> str:
    # Stable across scans: adding another file must not renumber existing provenance IDs.
    rel = path.as_posix()
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "-", path.stem).strip("-.") or "doc"
    if not stem[0].isalpha():
        stem = "doc-" + stem
    suffix = hashlib.sha256(rel.encode("utf-8")).hexdigest()[:10]
    return f"source_{stem}_{suffix}"[:95]


@dataclass(slots=True)
class MarkdownDocument:
    source_id: str
    path: str
    digest: str
    headings: list[tuple[int, str]] = field(default_factory=list)
    paragraphs: list[str] = field(default_factory=list)
    bullets: list[str] = field(default_factory=list)
    code_blocks: list[tuple[str, str, str]] = field(default_factory=list)  # lang, digest, content


@dataclass(slots=True)
class SourceIndex:
    root: str
    documents: list[MarkdownDocument]
    generated_at: str

    def to_markdown(self) -> str:
        lines = [
            "SOURCE_INDEX markdown_sources",
            f"ROOT {_q(self.root)}",
        ]
        for doc in self.documents:
            lines.extend([
                f"DOC {doc.source_id}",
                f"  PATH {_q(doc.path)}",
                f"  SHA256 {doc.digest}",
            ])
            for level, title in doc.headings:
                lines.append(f"  HEADING {level} {_q(title)}")
            for text in doc.paragraphs:
                lines.append(f"  PARAGRAPH {_q(text)}")
            for bullet in doc.bullets:
                lines.append(f"  BULLET {_q(bullet)}")
            for lang, digest, content in doc.code_blocks:
                lines.append(f"  CODE {lang or 'text'} HASH {digest} CONTENT {_q(content)}")
            lines.append("END")
        lines.append("END_SOURCE_INDEX")
        return "```sourceindexdsl\n" + "\n".join(lines) + "\n```"

    def envelope(self) -> dict[str, str]:
        """Keep execution time outside the deterministic semantic document."""
        markdown = self.to_markdown()
        return {
            "schema": "onlydsl.source-index-envelope/v1",
            "generatedAt": self.generated_at,
            "contentHash": "sha256:" + hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
            "sourceIndexDSL": markdown,
        }

    def source_refs(self) -> list[dict[str, str]]:
        return [{"id": d.source_id, "path": d.path, "digest": d.digest} for d in self.documents]


def _normalize_text(text: str) -> str:
    return " ".join(text.split())


def _extract_code_blocks(raw: str, max_item_chars: int) -> tuple[list[tuple[str, str, str]], list[tuple[int, int]]]:
    code_re = re.compile(r"```([^\n`]*)\n(.*?)```", re.S)
    blocks: list[tuple[str, str, str]] = []
    code_spans: list[tuple[int, int]] = []
    for match in code_re.finditer(raw):
        lang = match.group(1).strip().split()[0] if match.group(1).strip() else "text"
        content = match.group(2).strip()
        cdig = "sha256:" + hashlib.sha256(match.group(2).encode("utf-8")).hexdigest()
        blocks.append((lang, cdig, content[:max_item_chars]))
        code_spans.append((match.start(), match.end()))
    return blocks, code_spans


def _flush_paragraph(doc: MarkdownDocument, lines: list[str], max_item_chars: int) -> list[str]:
    value = _normalize_text(" ".join(lines))[:max_item_chars]
    if value:
        doc.paragraphs.append(value)
    return []


def _parse_text_content(
    doc: MarkdownDocument, raw: str, code_spans: list[tuple[int, int]], max_item_chars: int
) -> None:
    def in_code(position: int) -> bool:
        return any(start <= position < end for start, end in code_spans)

    para: list[str] = []
    offset = 0
    for raw_line in raw.splitlines(keepends=True):
        line = raw_line.rstrip("\r\n")
        if in_code(offset):
            offset += len(raw_line)
            continue
        stripped = line.strip()
        if not stripped:
            if para:
                para = _flush_paragraph(doc, para, max_item_chars)
            offset += len(raw_line)
            continue
        hm = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if hm:
            if para:
                para = _flush_paragraph(doc, para, max_item_chars)
            doc.headings.append((len(hm.group(1)), _normalize_text(hm.group(2))[:max_item_chars]))
        elif re.match(r"^[-*+]\s+", stripped):
            if para:
                para = _flush_paragraph(doc, para, max_item_chars)
            doc.bullets.append(_normalize_text(re.sub(r"^[-*+]\s+", "", stripped))[:max_item_chars])
        else:
            # Strip common markdown decorations, but keep semantic text as a typed DSL literal.
            cleaned = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", stripped)
            cleaned = cleaned.replace("**", "").replace("__", "").replace("`", "")
            para.append(cleaned)
        offset += len(raw_line)
    if para:
        _flush_paragraph(doc, para, max_item_chars)


def parse_markdown(path: Path, root: Path, source_id: str, *, max_item_chars: int = 1800) -> MarkdownDocument:
    raw = path.read_text(encoding="utf-8", errors="replace")
    digest = "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()
    rel = path.relative_to(root).as_posix()
    doc = MarkdownDocument(source_id, f"sources/{rel}", digest)
    doc.code_blocks, code_spans = _extract_code_blocks(raw, max_item_chars)
    _parse_text_content(doc, raw, code_spans, max_item_chars)
    return doc


def build_source_index(
    root: str | Path = "sources",
    *,
    max_files: int | None = None,
    max_total_chars: int | None = None,
) -> SourceIndex:
    root_path = Path(root).resolve()
    if not root_path.exists():
        root_path.mkdir(parents=True, exist_ok=True)
    max_files = max_files or int(os.getenv("SOURCE_MAX_FILES", "64"))
    max_total_chars = max_total_chars or int(os.getenv("SOURCE_MAX_CHARS", "120000"))
    files = sorted([p for p in root_path.rglob("*.md") if p.is_file()])[:max_files]
    docs: list[MarkdownDocument] = []
    budget = max_total_chars
    for idx, path in enumerate(files, 1):
        if budget <= 0:
            break
        source_id = _sid(path.relative_to(root_path), idx)
        doc = parse_markdown(path, root_path, source_id)
        # Enforce a deterministic total-context budget after parsing.
        serialized = json.dumps({
            "h": doc.headings,
            "p": doc.paragraphs,
            "b": doc.bullets,
            "c": doc.code_blocks,
        }, ensure_ascii=False)
        if len(serialized) > budget:
            ratio = max(0.05, budget / max(1, len(serialized)))
            keep_p = max(0, int(len(doc.paragraphs) * ratio))
            keep_b = max(0, int(len(doc.bullets) * ratio))
            keep_c = max(0, int(len(doc.code_blocks) * ratio))
            doc.paragraphs = doc.paragraphs[:keep_p]
            doc.bullets = doc.bullets[:keep_b]
            doc.code_blocks = doc.code_blocks[:keep_c]
            budget = 0
        else:
            budget -= len(serialized)
        docs.append(doc)
    return SourceIndex(
        root="sources/",
        documents=docs,
        generated_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    )


def validate_sourceindex_markdown(markdown: str) -> dict[str, Any]:
    try:
        if not markdown.startswith("```sourceindexdsl\n") or not markdown.rstrip().endswith("```"):
            raise SourceIngestError("SourceIndexDSL requires one sourceindexdsl codeblock")
        body = markdown.split("\n", 1)[1].rsplit("```", 1)[0]
        lines = [x.strip() for x in body.splitlines() if x.strip()]
        if not lines or lines[0] != "SOURCE_INDEX markdown_sources" or lines[-1] != "END_SOURCE_INDEX":
            raise SourceIngestError("invalid SourceIndexDSL envelope")
        doc_ids = [x.split()[1] for x in lines if x.startswith("DOC ")]
        if len(doc_ids) != len(set(doc_ids)):
            raise SourceIngestError("duplicate source ids")
        return {"valid": True, "errors": [], "documents": len(doc_ids)}
    except Exception as exc:
        return {"valid": False, "errors": [str(exc)]}


def extract_source_refs(markdown: str) -> dict[str, dict[str, str]]:
    validation = validate_sourceindex_markdown(markdown)
    if not validation["valid"]:
        raise SourceIngestError("; ".join(validation["errors"]))
    body = markdown.split("\n", 1)[1].rsplit("```", 1)[0]
    refs: dict[str, dict[str, str]] = {}
    current = ""
    for raw in body.splitlines():
        line = raw.strip()
        if line.startswith("DOC "):
            current = line.split(None, 1)[1].strip()
            refs[current] = {"id": current, "path": "", "digest": ""}
        elif current and line.startswith("PATH "):
            refs[current]["path"] = json.loads(line[len("PATH "):])
        elif current and line.startswith("SHA256 "):
            refs[current]["digest"] = line.split(None, 1)[1].strip()
        elif line == "END":
            current = ""
    return refs
