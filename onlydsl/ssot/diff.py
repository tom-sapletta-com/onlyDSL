from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FileChange:
    operation: str
    path: str
    before_hash: str | None
    after_hash: str | None


def calculate_diff(before: dict[str, str], after: dict[str, str]) -> tuple[FileChange, ...]:
    changes: list[FileChange] = []
    for path in sorted(set(before) | set(after)):
        if path not in before:
            changes.append(FileChange("add", path, None, after[path]))
        elif path not in after:
            changes.append(FileChange("remove", path, before[path], None))
        elif before[path] != after[path]:
            changes.append(FileChange("change", path, before[path], after[path]))
    return tuple(changes)


def render_diff(candidate_id: str, base_revision: str, changes: tuple[FileChange, ...]) -> str:
    rows = [f"SSOT_DIFF {candidate_id}", f"BASE_REVISION {base_revision}"]
    for item in changes:
        rows.append(
            "CHANGE " + json.dumps(item.path, ensure_ascii=False) +
            f" OPERATION {item.operation} FROM {item.before_hash or 'none'} TO {item.after_hash or 'none'}"
        )
    rows.extend([f"CHANGES {len(changes)}", "END_SSOT_DIFF"])
    return "\n".join(rows) + "\n"
