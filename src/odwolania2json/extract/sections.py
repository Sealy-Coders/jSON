from __future__ import annotations

import regex as re
from typing import Any


def _first_match_pos(text: str, patterns: list[str]) -> int | None:
    best = None
    for p in patterns:
        m = re.search(p, text)
        if m:
            pos = m.start()
            if best is None or pos < best:
                best = pos
    return best


def slice_section(text: str, start_patterns: list[str], end_patterns: list[str]) -> str:
    start = _first_match_pos(text, start_patterns)
    if start is None:
        return ""
    rest = text[start:]
    # end relative to rest, but after some minimal length
    end_rel = _first_match_pos(rest[30:], end_patterns)
    if end_rel is None:
        return rest[:2500]
    return rest[: 30 + end_rel]


def build_sections(text: str, section_cfg: dict[str, Any] | None) -> dict[str, str]:
    if not section_cfg:
        return {"full": text}
    out = {"full": text}
    for name, cfg in section_cfg.items():
        out[name] = slice_section(text, cfg.get("start", []), cfg.get("end", []))
    return out
