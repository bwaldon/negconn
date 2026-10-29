"""File-level pipeline stages shared by the local runner and the Modal app.

Every stage reads and writes under one root directory (``/data`` on the
Modal Volume, ``data/`` locally) and is skipped when its output exists.
The study (negconj.study) supplies the prefilter; classify and report are the
study's own stages (``study.classify``, ``study.report``).
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from . import uslm_extract
from .shards import merge_shards, plan_shards, prefilter
from .study import Study
from .util import atomic_write_bytes, atomic_write_parquet, title_sort_key


def title_of(xml: Path) -> str:
    return uslm_extract._title_from_path(Path(xml))[0]


def extract_stage(xml: Path, root: Path, study: Study) -> dict:
    root = Path(root)
    title = title_of(xml)
    u_out, e_out = root / "units" / f"{title}.parquet", root / "elements" / f"{title}.parquet"
    if not (u_out.exists() and e_out.exists()):
        elements, units = uslm_extract.extract_title(xml)
        atomic_write_parquet(elements, e_out)
        atomic_write_parquet(units, u_out)  # written last: its presence marks completion
    units = pd.read_parquet(u_out)
    pre = prefilter(units, study.unit_patterns)
    return {"title": title, "units": len(units),
            "units_by_source": units["elem_source"].value_counts().to_dict(),
            "no_section": int(units["section"].isna().sum()),
            "prefilter_units": len(pre),
            "prefilter_sections": int(pre["section_key"].nunique()),
            "prefilter_chars": int(pre["text_parse"].str.len().sum())}


def titles_on_disk(root: Path) -> list[str]:
    return sorted((p.stem for p in (Path(root) / "units").glob("*.parquet")), key=title_sort_key)


def load_units(root: Path, titles: list[str] | None = None) -> pd.DataFrame:
    titles = titles or titles_on_disk(root)
    return pd.concat([pd.read_parquet(Path(root) / "units" / f"{t}.parquet") for t in titles],
                     ignore_index=True)


def load_prefiltered(root: Path, study: Study,
                     titles: list[str] | None = None) -> dict[str, pd.DataFrame]:
    titles = titles or titles_on_disk(root)
    return {t: prefilter(pd.read_parquet(Path(root) / "units" / f"{t}.parquet"), study.unit_patterns)
            for t in titles}


def plan_stage(root: Path, target_chars: int, study: Study,
               titles: list[str] | None = None) -> dict[str, list[str]]:
    path = Path(root) / "shards.json"
    if path.exists():
        return json.loads(path.read_text())
    plan = plan_shards(load_prefiltered(root, study, titles), target_chars)
    atomic_write_bytes(path, json.dumps(plan, indent=1).encode())
    return plan


def merge_stage(root: Path, plan: dict[str, list[str]], study: Study) -> dict:
    titles = sorted({sid.rsplit("-", 1)[0] for sid in plan}, key=title_sort_key)
    pre = pd.concat(load_prefiltered(root, study, titles).values(), ignore_index=True)
    return merge_shards(root, plan, pre)
