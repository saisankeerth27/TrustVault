"""Safe plain-text change summaries for audit history."""

from __future__ import annotations

from difflib import SequenceMatcher


def summarize_text_changes(previous: str, updated: str) -> dict[str, int]:
    previous_lines = previous.splitlines()
    updated_lines = updated.splitlines()
    matcher = SequenceMatcher(
        None,
        previous_lines,
        updated_lines,
        autojunk=False,
    )

    lines_added = 0
    lines_removed = 0
    lines_unchanged = 0
    change_blocks = 0
    for operation, old_start, old_end, new_start, new_end in matcher.get_opcodes():
        if operation == "equal":
            lines_unchanged += new_end - new_start
            continue
        change_blocks += 1
        lines_removed += old_end - old_start
        lines_added += new_end - new_start

    return {
        "lines_added": lines_added,
        "lines_removed": lines_removed,
        "lines_unchanged": lines_unchanged,
        "change_blocks": change_blocks,
    }
