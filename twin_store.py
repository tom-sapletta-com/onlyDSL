from __future__ import annotations

import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from digital_twin import TwinDocument, extract_twindsl, parse_twindsl, render_twin, validate_twin_markdown


class TwinStoreError(RuntimeError):
    pass


class TwinStore:
    def __init__(self, root: str | Path | None = None):
        self.root = Path(root or os.getenv("TWIN_STATE_DIR", "state")).resolve()
        self.history = self.root / "history"
        self.root.mkdir(parents=True, exist_ok=True)
        self.history.mkdir(parents=True, exist_ok=True)
        self.current_path = self.root / "digital_twin.md"

    def exists(self) -> bool:
        return self.current_path.exists()


    def reset_current(self) -> None:
        if self.current_path.exists():
            self.current_path.unlink()

    def load_markdown(self) -> str:
        if not self.exists():
            raise TwinStoreError("digital twin has not been bootstrapped yet")
        return self.current_path.read_text(encoding="utf-8")

    def load(self) -> TwinDocument:
        return parse_twindsl(extract_twindsl(self.load_markdown()))

    def save(self, markdown: str) -> TwinDocument:
        validation = validate_twin_markdown(markdown)
        if not validation["valid"]:
            raise TwinStoreError("invalid TwinDSL: " + "; ".join(validation["errors"]))
        doc = parse_twindsl(extract_twindsl(markdown))
        if self.exists():
            previous = self.load()
            if doc.revision <= previous.revision:
                raise TwinStoreError("new revision must be greater than current revision")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        hist = self.history / f"rev-{doc.revision:04d}-{stamp}.md"
        hist.write_text(markdown, encoding="utf-8")
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=self.root, delete=False) as fh:
            fh.write(markdown)
            tmp = Path(fh.name)
        tmp.replace(self.current_path)
        return doc
