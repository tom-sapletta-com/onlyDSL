from __future__ import annotations

from pathlib import Path

from onlydsl_contracts.ifuri import IfUri


class ArtifactError(ValueError):
    pass


class LocalFileArtifactStore:
    """Maps logical IFURI artifact identity to a safe local file placement.

    The returned file:// URI is physical placement metadata and never replaces the
    logical `ifuri://.../artifacts/...` identity in domain messages.
    """

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, logical_uri: str) -> Path:
        uri = IfUri.parse(logical_uri)
        if uri.kind != "artifacts":
            raise ArtifactError("artifact store accepts only IFURI artifact addresses")
        path = (
            self.root
            / uri.bounded_context
            / uri.entity
            / uri.identity
            / f"{uri.operation}.bin"
        ).resolve()
        if self.root != path and self.root not in path.parents:
            raise ArtifactError("resolved artifact path escapes storage root")
        return path

    def put(self, logical_uri: str, data: bytes) -> str:
        path = self._path(logical_uri)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(path)
        return path.as_uri()

    def get(self, logical_uri: str) -> bytes:
        return self._path(logical_uri).read_bytes()

    def exists(self, logical_uri: str) -> bool:
        return self._path(logical_uri).is_file()
