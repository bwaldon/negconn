"""The negated-connective studies: negative conjunction (``and``) and disjunction (``or``).

Prefilter: a unit's lowercased text contains "not" and the connective as words. Sentence regex:
``\\bnot\\b.*\\b{conn}\\b`` (not precedes the connective, whole words). Trees come from the
constituency parser; classification is criterion C2 (negconj.classify). The two runs differ only
in the connective.
"""

from __future__ import annotations

import re
from functools import partial
from pathlib import Path

import pandas as pd

from .classify import classify_frame
from .report import consistency_checks, publish, stratified_sample
from .stages import load_units
from .study import Study
from .util import atomic_write_csv, atomic_write_parquet, md_table, title_sort_key

CONNECTIVES = ("and", "or")
NOT_RE = re.compile(r"\bnot\b")
CONN_RES = {c: re.compile(rf"\b{c}\b") for c in CONNECTIVES}
MATCH_RES = {c: re.compile(rf"\bnot\b.*\b{c}\b", re.IGNORECASE | re.DOTALL) for c in CONNECTIVES}

PULSIFER = "/us/usc/t18/s3553/f"
CAMPOS_CHAVES = "/us/usc/t8/s1229a/b/5/C"
REVIEW_SEED = 20261019

# Per connective: study name, short tag, regression case (identifier, heading),
# and the phrases that are not coordinations for the limitations section.
INFO = {
    "and": {"name": "Negative conjunctions", "tag": "negconj",
            "regression": (PULSIFER, "Pulsifer: 18 U.S.C. § 3553(f)"),
            "not_coord": "`and/or` (one token), `as well as`"},
    "or": {"name": "Negative disjunctions", "tag": "negdisj",
           "regression": (CAMPOS_CHAVES, "Campos-Chaves: 8 U.S.C. § 1229a(b)(5)(C)"),
           "not_coord": "`and/or` (one token), `nor`"},
}


# --------------------------------------------------------------------------
# Classify
# --------------------------------------------------------------------------

def classify_stage(root: Path, conn: str = "and") -> dict:
    """pairs, sentences_classified (all matches) and flagged, in results/."""
    root = Path(root)
    res = root / "results"
    parses = pd.read_parquet(res / "parses.parquet")
    pairs, sents = classify_frame(parses, conn)
    titles = sorted(parses["title"].unique(), key=title_sort_key)
    units = load_units(root, titles)[["unit_id", "identifier", "elem_source", "is_appendix",
                                      "text_display"]]
    sents = sents.merge(units, on="unit_id", how="left", validate="many_to_one")
    atomic_write_parquet(pairs, res / "pairs.parquet")
    atomic_write_parquet(sents, res / "sentences_classified.parquet")
    flagged = sents[sents["flagged"]]
    cols = ["sent_id", "title", "section", "identifier", "elem_source", "is_appendix",
            "text", "text_display", "tree", "flagged_relaxed"]
    atomic_write_parquet(flagged[cols], res / "flagged.parquet")
    atomic_write_csv(flagged[cols], res / "flagged.csv")
    return {f"not_{conn}_pairs": len(pairs), "flagged": int(sents["flagged"].sum()),
            "flagged_relaxed": int(sents["flagged_relaxed"].sum())}


# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------

def limitations(conn: str = "and") -> str:
    return f"""\
- **Regex recall.** Only sentences matching `\\bnot\\b.*\\b{conn}\\b` are found: no `n't`, `cannot`,
  `nor`, `without`, `no`, `neither`, and no `{conn}` that precedes the negation.
- **Coordination = CC "{conn}".** A coordination node is the parent of a `CC` preterminal whose word is
  `{conn}`. {INFO[conn]["not_coord"]}, and an `{conn}` mis-tagged by the parser are not
  coordinations here.
- **Parser errors**, especially on very long condensed-chapeau sentences (hundreds of tokens),
  which are far outside the parser's training distribution. Stanza returns one best tree;
  no alternative parses are considered.
- **Syntactic, not interpretive.** `flagged` says the VP that is *not*'s parent dominates the
  coordination. It is not a judgment about which scope reading is correct in context, which,
  as the Campos-Chaves amicus brief stresses, depends on context.
- **Segmentation.** Stanza's sentence splitter plus a re-merge post-pass; residual splitting
  errors can split or join sentences.
"""


def review_sample(cls: pd.DataFrame, n_each: int = 100, seed: int = REVIEW_SEED,
                  conn: str = "and") -> pd.DataFrame:
    cols = ["sent_id", "title", "section", "identifier", "elem_source", "flagged",
            "flagged_relaxed", "text", "text_display", "tree"]
    parts = [stratified_sample(cls[cls["flagged"]], n_each, seed),
             stratified_sample(cls[~cls["flagged"]], n_each, seed + 1)]
    out = pd.concat(parts)[cols].reset_index(drop=True)
    out = out.sample(frac=1, random_state=seed).reset_index(drop=True)  # blind the order
    for c in (f"reviewer_is_{INFO[conn]['tag']}", "reviewer_scope_reading", "notes"):
        out[c] = ""
    return out


def regression_rows(cls: pd.DataFrame, pairs: pd.DataFrame,
                    conn: str = "and") -> tuple[pd.DataFrame, pd.DataFrame]:
    p = cls[cls["identifier"] == INFO[conn]["regression"][0]]
    return p, pairs[pairs["sent_id"].isin(p["sent_id"])]


def summary_md(stage_counts: dict, cls: pd.DataFrame, pairs: pd.DataFrame,
               fails: pd.DataFrame, checks: dict, conn: str = "and") -> str:
    by_title = (cls.groupby("title")
                .agg(matches=("sent_id", "size"), flagged=("flagged", "sum"),
                     flagged_relaxed=("flagged_relaxed", "sum")))
    by_title = by_title.loc[sorted(by_title.index, key=title_sort_key)].reset_index()
    flagged_pairs = pairs[pairs["c2_strict"]]
    by_label = (flagged_pairs.groupby("coord_label")["sent_id"].nunique()
                .sort_values(ascending=False).rename("flagged_sentences").reset_index())
    psent, ppairs = regression_rows(cls, pairs, conn)
    out = [f"# {INFO[conn]['name']} in the U.S. Code: run summary", ""]
    out += ["## Stage counts", "", md_table(pd.DataFrame(
        list(stage_counts.items()), columns=["stage", "count"])), ""]
    out += ["## Flagged sentences by title", "", md_table(by_title), ""]
    out += ["## Flagged sentences by coordination label (C2 strict)", "",
            "A sentence is counted under every label of a coordination that makes it flagged.", "",
            md_table(by_label), ""]
    out += [f"## {INFO[conn]['regression'][1]}", ""]
    if psent.empty:
        out += ["**Not found in the classified table.**", ""]
    for r in psent.itertuples():
        pp = ppairs[ppairs["sent_id"] == r.sent_id]
        out += [f"- `{r.sent_id}` ({r.n_tokens} tokens): flagged = **{r.flagged}**, "
                f"flagged_relaxed = **{r.flagged_relaxed}**, (not, {conn}) pairs = {len(pp)}, "
                f"strict pairs = {int(pp['c2_strict'].sum())}", "",
                f"  > {r.text[:600]}{'…' if len(r.text) > 600 else ''}", ""]
    out += ["## Parse failures", "", f"{len(fails)} sentences failed to parse.", ""]
    if len(fails):
        out += [md_table(fails[["sent_id", "error"]].head(50)), ""]
    out += ["## Consistency checks", "", md_table(pd.DataFrame(
        list(checks.items()), columns=["check", "result"])), ""]
    out += ["## Known limitations", "", limitations(conn)]
    return "\n".join(out)


def report_stage(root: Path, plan: dict[str, list[str]], manifest: dict,
                 stage_counts: dict, conn: str = "and") -> dict:
    """Write review_sample.csv and summary.md, then publish (manifest, inputs, checksums)."""
    root = Path(root)
    res = root / "results"
    cls = pd.read_parquet(res / "sentences_classified.parquet")
    pairs = pd.read_parquet(res / "pairs.parquet")
    fails = pd.read_parquet(res / "failures.parquet")
    checks = consistency_checks(root, plan)
    review_sample(cls, conn=conn).to_csv(res / "review_sample.csv", index=False)
    (res / "summary.md").write_text(summary_md(stage_counts, cls, pairs, fails, checks, conn))
    publish(root, {**manifest, "connective": conn, "counts": stage_counts, "checks": checks})
    return checks


def _study(conn: str) -> Study:
    return Study(name=conn, unit_patterns=(NOT_RE, CONN_RES[conn]), sentence_pattern=MATCH_RES[conn],
                 parser="electra", classify=partial(classify_stage, conn=conn),
                 report=partial(report_stage, conn=conn))


AND = _study("and")
OR = _study("or")
