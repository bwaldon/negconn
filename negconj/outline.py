"""The nested structure of condensed chapeau units, recovered for display.

A condensed unit (uslm_extract.extract_title, elem_source "chapeau_condensed") is one string: its
text elements (chapeau, content, continuation, proviso) joined in document order, with the
sub-levels' numbers ("(A)", "(ii)") in ``text_display`` and without them in ``text_parse``. The
elements table lists the same elements, in the same order, each with its own @identifier.
Aligning the two recovers the structure:

  depth   how many levels the element's identifier lies below the unit's
          (/us/usc/t8/s1225/b/2/B → 0, …/B/ii → 1)
  label   the numbers that open the element in text_display ("(ii)", or "(A) (i)" when a level
          opens straight into a sub-level); empty for a continuation or the unit's chapeau.
          A line labelled "(A) (i)" is placed at (A)'s depth, as the Code prints it.

An outline is a list of ``(start, end, depth, label)``, offsets into ``text_parse``. A unit
whose elements cannot all be placed, or that lack identifiers under the unit's (some appendix
titles), has no outline and is shown as flat text.
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

Outline = list[tuple[int, int, int, str]]
_NUM = re.compile(r"\([^()\s]+\)")


def _depth(unit_ident, ident) -> int | None:
    """Levels ident lies below unit_ident; None when either is missing (NaN) or unrelated."""
    if not (isinstance(ident, str) and isinstance(unit_ident, str)) or not (
            ident == unit_ident or ident.startswith(unit_ident + "/")):
        return None
    return ident[len(unit_ident):].count("/")


def unit_outline(identifier: str | None, text_parse: str, text_display: str,
                 elements: pd.DataFrame) -> Outline | None:
    """Outline of one condensed unit; ``elements`` are its rows of the elements table (columns
    identifier, text), in document order."""
    out: Outline = []
    pc = dc = 0  # cursors in text_parse and text_display
    for ident, text in zip(elements["identifier"], elements["text"]):
        if not text:
            continue
        depth = _depth(identifier, ident)
        d = text_display.find(text, dc)
        p = text_parse.find(text, pc)
        if p < 0 and out and text in text_parse[out[-1][0]:out[-1][1]]:
            continue  # nested inside the previous element (e.g. a proviso within content)
        if depth is None or d < 0 or p < 0:
            return None
        label = text_display[dc:d].strip()
        depth -= max(0, len(_NUM.findall(label)) - 1)
        out.append((p, p + len(text), depth, label))
        pc, dc = p + len(text), d + len(text)
    return out or None


def sentence_breaks(outline: Outline | None, unit_text: str, sent_text: str,
                    words: list[str]) -> list[list]:
    """Where a sentence's words start new outline lines: ``[[word index, depth, label], …]``
    (the first entry is word 0). Words are matched to the text in order; a word not found as
    written (a multi-word token's part) takes its predecessor's position. Empty without an
    outline."""
    if not outline:
        return []
    start = unit_text.find(sent_text)
    if start < 0:
        return []
    offsets, cur = [], 0
    for w in words:
        k = sent_text.find(w, cur)
        if 0 <= k - cur <= 3:  # words are separated by at most a space (whitespace is normalized)
            offsets.append(start + k)
            cur = k + len(w)
        else:
            offsets.append(start + cur)
    breaks: list[list] = []
    for s, e, depth, label in outline:
        if e <= start or s >= start + len(sent_text):
            continue
        i = next((j for j, o in enumerate(offsets) if o >= s), None)
        if i is None:
            continue
        if s <= start:  # the sentence starts inside this element
            i, label = 0, label if s == start else ""
        if breaks and breaks[-1][0] == i:
            breaks[-1] = [i, depth, label or breaks[-1][2]]
        else:
            breaks.append([i, depth, label])
    return breaks if len(breaks) > 1 or (breaks and breaks[0][1] > 0) else []


def load_outlines(results: Path, unit_ids: set[str]) -> dict[str, tuple[str, Outline | None]]:
    """unit_id -> (text_parse, outline) for the given units, from results/units and
    results/elements. Non-condensed units get no outline."""
    out: dict[str, tuple[str, Outline | None]] = {}
    for up in sorted((Path(results) / "units").glob("*.parquet")):
        units = pd.read_parquet(up, columns=["unit_id", "identifier", "elem_source", "text_parse",
                                             "text_display"])
        units = units[units["unit_id"].isin(unit_ids)]
        if units.empty:
            continue
        cond = units[units["elem_source"] == "chapeau_condensed"]
        els = pd.read_parquet(Path(results) / "elements" / up.name, columns=["identifier", "text", "consumed_by"])
        els = {k: g for k, g in els[els["consumed_by"].isin(set(cond["unit_id"]))].groupby("consumed_by", sort=False)}
        for r in units.itertuples(index=False):
            ol = (unit_outline(r.identifier, r.text_parse, r.text_display, els[r.unit_id])
                  if r.elem_source == "chapeau_condensed" and r.unit_id in els else None)
            out[r.unit_id] = (r.text_parse, ol)
    return out
