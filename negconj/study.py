"""A study: what a run looks for, how it parses it, and how it classifies and reports the parses.

The stages (extract → plan → segment + parse → merge → classify → report) are shared code; a
study supplies the unit prefilter, the sentence regex, the parser configuration and its own
classify and report stages. Runs name their study with a string, so the name crosses Modal
calls and the study is loaded where it is used.

    and    negative conjunction, ``not … and`` (negconj.connectives)
    or     negative disjunction, ``not … or`` (negconj.connectives)
    1225b  sentences shaped like 8 U.S.C. § 1225(b)(2)(A) (barbosa.study)
"""

from __future__ import annotations

import importlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

STUDIES = {
    "and": "negconj.connectives:AND",
    "or": "negconj.connectives:OR",
    "1225b": "barbosa.study:STUDY",
}


@dataclass(frozen=True)
class Study:
    name: str
    # A unit is prefiltered in when its lowercased text_parse matches every one of these.
    unit_patterns: tuple[re.Pattern, ...]
    # A segmented sentence is a match (and is parsed) when this pattern finds a hit in it.
    sentence_pattern: re.Pattern
    parser: str  # key of parse.PARSER_CONFIGS
    # classify(root) reads results/parses.parquet and writes the study's tables; returns counts.
    classify: Callable[[Path], dict]
    # report(root, plan, manifest, stage_counts) writes summary, manifest, checksums; returns checks.
    report: Callable[[Path, dict, dict, dict], dict]

    def is_match(self, text: str) -> bool:
        return self.sentence_pattern.search(text) is not None


def load_study(name: str) -> Study:
    module, attr = STUDIES[name].split(":")
    return getattr(importlib.import_module(module), attr)
