"""Build and publish the complete onlyDSL package workspace as one release set."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import NamedTuple


ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"


class Distribution(NamedTuple):
    name: str
    root: Path

    @property
    def normalized_name(self) -> str:
        return self.name.lower().replace("-", "_")


DISTRIBUTIONS = (
    Distribution("onlydsl-contracts", ROOT / "packages/onlydsl-contracts"),
    Distribution("onlydsl-core", ROOT / "packages/onlydsl-core"),
    Distribution("onlydsl-ssot", ROOT / "packages/onlydsl-ssot"),
    Distribution("onlyDSL", ROOT),
)


def declared_version(distribution: Distribution) -> str:
    if distribution.root == ROOT:
        return (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    metadata = tomllib.loads((distribution.root / "pyproject.toml").read_text(encoding="utf-8"))
    return str(metadata["project"]["version"])


def verify_versions(expected: str) -> None:
    mismatches = {
        distribution.name: declared_version(distribution)
        for distribution in DISTRIBUTIONS
        if declared_version(distribution) != expected
    }
    if mismatches:
        raise SystemExit(f"workspace release version mismatch: expected={expected} actual={mismatches}")


def resolve_version(raw: str) -> str:
    if raw == "{version}":
        return (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    return raw


def release_artifacts(expected: str) -> list[Path]:
    artifacts = sorted(path for path in DIST.glob("*") if path.is_file() and expected in path.name)
    missing = [
        distribution.name
        for distribution in DISTRIBUTIONS
        if not any(path.name.lower().replace("-", "_").startswith(distribution.normalized_name + "_") for path in artifacts)
    ]
    if missing:
        raise SystemExit(f"workspace release artifacts missing: {missing}")
    return artifacts


def build(expected: str) -> None:
    verify_versions(expected)
    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir()
    for distribution in DISTRIBUTIONS:
        subprocess.run(
            [sys.executable, "-m", "build", "--outdir", str(DIST), str(distribution.root)],
            cwd=ROOT,
            check=True,
        )
    release_artifacts(expected)


def publish(expected: str) -> None:
    verify_versions(expected)
    artifacts = release_artifacts(expected)
    subprocess.run([sys.executable, "-m", "twine", "upload", *map(str, artifacts)], cwd=ROOT, check=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("build", "publish"))
    parser.add_argument("--version", required=True)
    args = parser.parse_args()
    version = resolve_version(args.version)
    if args.action == "build":
        build(version)
    else:
        publish(version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
