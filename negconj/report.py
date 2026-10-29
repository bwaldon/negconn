"""Report pieces every study shares: consistency checks, stratified sampling, and publishing
results/ (manifest, copies of the inputs, checksums) (§7, §8). Each study writes its own
summary (negconj.connectives, barbosa.study)."""

from __future__ import annotations

import json
import random
import shutil
from pathlib import Path

import pandas as pd

from .shards import read_done
from .util import write_checksums


# --------------------------------------------------------------------------
# Checks
# --------------------------------------------------------------------------

def consistency_checks(root: Path, plan: dict[str, list[str]]) -> dict:
    root = Path(root)
    res = root / "results"
    segs = pd.read_parquet(res / "segments.parquet")
    parses = pd.read_parquet(res / "parses.parquet")
    fails = pd.read_parquet(res / "failures.parquet")
    cls = pd.read_parquet(res / "sentences_classified.parquet")
    checks: dict[str, bool | int] = {}

    matched = set(segs.loc[segs["matched"].astype(bool), "sent_id"])
    checks["every_match_has_one_parse_or_failure"] = (
        parses["sent_id"].is_unique and fails["sent_id"].is_unique
        and not (set(parses["sent_id"]) & set(fails["sent_id"]))
        and matched == set(parses["sent_id"]) | set(fails["sent_id"]))
    checks["no_duplicate_sent_ids"] = bool(segs["sent_id"].is_unique and parses["sent_id"].is_unique
                                           and cls["sent_id"].is_unique)
    checks["classified_equals_parses"] = set(cls["sent_id"]) == set(parses["sent_id"])
    checks["all_planned_sections_done"] = all(
        set(secs) <= set(read_done(root, sid)) for sid, secs in plan.items())

    # No text both standalone and inside a condensed chapeau.
    overlap = 0
    for p in sorted((root / "elements").glob("*.parquet")):
        el = pd.read_parquet(p, columns=["parent_id", "parent_position", "consumed_by"])
        un = pd.read_parquet(root / "units" / p.name, columns=["unit_id", "elem_source"])
        standalone = set(un.loc[un["elem_source"] != "chapeau_condensed", "unit_id"])
        consumed = el[el["consumed_by"].notna()]
        ids = consumed["parent_id"] + "_" + consumed["parent_position"].astype(str)
        overlap += int(ids.isin(standalone).sum())
    checks["standalone_and_condensed_overlap"] = overlap
    checks["ok"] = all(v for k, v in checks.items() if isinstance(v, bool)) and overlap == 0
    return checks


# --------------------------------------------------------------------------
# Review sample
# --------------------------------------------------------------------------

def _allocate(sizes: pd.Series, n: int) -> pd.Series:
    """Proportional allocation with largest remainders, capped at stratum size."""
    n = min(n, int(sizes.sum()))
    exact = sizes / sizes.sum() * n
    alloc = exact.astype(int)
    rem = (exact - alloc).sort_values(ascending=False, kind="stable")
    for k in rem.index:
        if alloc.sum() >= n:
            break
        if alloc[k] < sizes[k]:
            alloc[k] += 1
    return alloc


def stratified_sample(df: pd.DataFrame, n: int, seed: int) -> pd.DataFrame:
    if df.empty:
        return df
    strata = df.groupby(["title", "elem_source"], sort=True)
    alloc = _allocate(strata.size(), n)
    rng = random.Random(seed)
    picks = []
    for key, g in strata:
        k = int(alloc[key])
        if k:
            picks.append(g.loc[sorted(rng.sample(list(g.index), k))])
    return pd.concat(picks)


# --------------------------------------------------------------------------
# Publish
# --------------------------------------------------------------------------

def publish(root: Path, manifest: dict) -> None:
    """Copy units/ and elements/ into results/, write RUN_MANIFEST.json, then
    CHECKSUMS.sha256 (last)."""
    root = Path(root)
    res = root / "results"
    for sub in ("units", "elements"):
        (res / sub).mkdir(exist_ok=True)
        for p in (root / sub).glob("*.parquet"):
            dst = res / sub / p.name
            if not dst.exists() or dst.stat().st_size != p.stat().st_size:
                shutil.copy2(p, dst)
    (res / "RUN_MANIFEST.json").write_text(json.dumps(manifest, indent=1, default=str))
    write_checksums(res)
