"""The 1225b study: U.S. Code sentences shaped like 8 U.S.C. § 1225(b)(2)(A).

Candidates are the sentences matching any of the RA's nine Westlaw queries (QUERIES), or their
mirror images with the "if" first (MIRRORED, ours: they find the phrase inside an if-clause).
Each is dependency-parsed (Stanza, UD; parser "electra-dep") and the dependency query
(barbosa.depquery) checks the structure, in two patterns: the phrase before the if-clause, as in
the provision, or inside it. The provision's own pattern:

1. a phrase like "in the case of" followed by an indefinite noun phrase ("an alien who is an
   applicant for admission"), and
2. an if-clause, modifying the same head as the phrase (both modify the main clause, as in the
   provision), that repeats that indefinite noun phrase with a different modifier ("an alien
   seeking admission").

Westlaw → regex: ``"p #w a" OR "p #w an"`` is the phrase followed by "a" or "an" (``#`` only
turns off Westlaw's plurals and equivalents, so the word is matched as written); ``x +s y`` is
"x precedes y in the same sentence". Matching is case-insensitive on whole words, within one
segmented sentence.
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from negconj.report import consistency_checks, publish
from negconj.stages import load_units
from negconj.study import Study
from negconj.util import atomic_write_csv, atomic_write_parquet, md_table, title_sort_key

from . import depquery

PROVISION = "/us/usc/t8/s1225/b/2/A"

# (id, the RA's query as written, the phrase it anchors on)
QUERIES = [
    ("case_of", 'adv: ("in the case #of a" OR "in the case #of an") +s if +s (a OR an)', "in the case of"),
    ("with_regard_to", 'adv: ("with regard #to a" OR "with regard #to an") +s if +s (a OR an)', "with regard to"),
    ("regarding", 'adv: ("regarding a" OR "regarding an") +s if +s (a OR an)', "regarding"),
    ("concerning", 'adv: ("concerning a" OR "concerning an") +s if +s (a OR an)', "concerning"),
    ("respecting", 'adv: ("respecting a" OR "respecting an") +s if +s (a OR an)', "respecting"),
    ("in_regard_to", 'adv: ("in regard #to a" OR "in regard #to an") +s if +s (a OR an)', "in regard to"),
    ("with_respect_to", 'adv: ("with respect #to a" OR "with respect #to an") +s if +s (a OR an)', "with respect to"),
    ("event_that", 'adv: ("in the event #that a" OR "in the event #that an") +s if +s (a OR an)', "in the event that"),
    ("event_of", 'adv: ("in the event #of a" OR "in the event #of an") +s if +s (a OR an)', "in the event of"),
]
PHRASES = {qid: tuple(phrase.split()) for qid, _, phrase in QUERIES}


def _mirror(query: str) -> str:
    """'adv: (P) +s if +s (a OR an)' -> 'adv: if +s (P) +s (a OR an)'."""
    m = re.fullmatch(r"adv: (\(.*\)) \+s if \+s \(a OR an\)", query)
    return f"adv: if +s {m.group(1)} +s (a OR an)"


# The same phrases with the "if" first, for the phrase inside an if-clause (not the RA's).
MIRRORED = [(f"if_{qid}", _mirror(q), phrase) for qid, q, phrase in QUERIES]
ALL_QUERIES = QUERIES + MIRRORED
SOURCE = {qid: "RA" for qid, _, _ in QUERIES} | {qid: "mirrored" for qid, _, _ in MIRRORED}


def _phrase_re(phrase: str) -> str:
    return r"\s+".join(map(re.escape, phrase.split()))


def query_re(phrase: str, if_first: bool = False) -> re.Pattern:
    p = rf"\b{_phrase_re(phrase)}\s+an?\b"
    body = rf"\bif\b.*{p}.*\ban?\b" if if_first else rf"{p}.*\bif\b.*\ban?\b"
    return re.compile(body, re.IGNORECASE | re.DOTALL)


QUERY_RES = {qid: query_re(phrase, SOURCE[qid] == "mirrored") for qid, _, phrase in ALL_QUERIES}
_ALT = rf"\b(?:{'|'.join(_phrase_re(p) for _, _, p in QUERIES)})\s+an?\b"
ANY_QUERY = re.compile(rf"{_ALT}.*\bif\b.*\ban?\b|\bif\b.*{_ALT}.*\ban?\b", re.IGNORECASE | re.DOTALL)


def queries_matching(text: str) -> list[str]:
    return [qid for qid, rx in QUERY_RES.items() if rx.search(text)]


# --------------------------------------------------------------------------
# Classify
# --------------------------------------------------------------------------

MATCH_COLUMNS = ["sent_id", "title", "section", "identifier", "elem_source", "is_appendix",
                 "queries", "text", "text_display", "conllu"]


def classify_stage(root: Path) -> dict:
    """candidates, sentences_classified (every parsed match) and matches (the sentences the
    dependency query matches), in results/."""
    root = Path(root)
    res = root / "results"
    parses = pd.read_parquet(res / "parses.parquet")
    cands, sents = depquery.classify_frame(parses, PHRASES)
    sents["queries"] = [queries_matching(t) for t in sents["text"]]
    titles = sorted(parses["title"].unique(), key=title_sort_key)
    units = load_units(root, titles)[["unit_id", "identifier", "elem_source", "is_appendix",
                                      "text_display"]]
    sents = sents.merge(units, on="unit_id", how="left", validate="many_to_one")
    atomic_write_parquet(cands, res / "candidates.parquet")
    atomic_write_parquet(sents, res / "sentences_classified.parquet")
    hits = sents[sents["matches"]][MATCH_COLUMNS]
    atomic_write_parquet(hits, res / "matches.parquet")
    atomic_write_csv(hits.drop(columns="conllu"), res / "matches.csv")
    return {"candidates": len(cands), "dep_query_matches": len(hits),
            **{f"dep_query_matches_{p}": int(sents[f"matches_{p}"].sum()) for p in depquery.PATTERNS},
            "near_misses": int(near_misses(sents).sum())}


def near_misses(sents: pd.DataFrame) -> pd.Series:
    """Sentences that do not match but whose best candidate meets all but one of its pattern's
    conditions, with the same head for the outside pattern (the phrase and the if-clause modify
    the same head)."""
    return (~sents["matches"] & (sents["best_n_met"] == sents["best_n_conditions"] - 1)
            & ((sents["best_pattern"] != "outside") | sents["best_same_governor"]))


# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------

PATTERN_TEXT = {
    "outside": "the phrase before the if-clause (as in § 1225(b)(2)(A))",
    "inside": "the phrase inside the if-clause, before the repeated noun",
}
CONDITION_TEXT = {
    "outside": {
        "frame_np": "the phrase introduces an indefinite noun phrase (N1)",
        "if_outside": "an if-clause after it, outside the phrase",
        "same_governor": "the phrase and the if-clause modify the same head",
        "repeated_np": "the if-clause has an indefinite noun phrase with N1's head noun (N2)",
        "different_mods": "N1 and N2 are both modified, with different modifiers",
    },
    "inside": {
        "frame_np": "the phrase introduces an indefinite noun phrase (N1)",
        "phrase_in_if": "the phrase is part of an if-clause that starts before it",
        "repeated_np": "later in the if-clause, outside the phrase, an indefinite noun phrase with N1's head noun (N2)",
        "different_mods": "N1 and N2 are both modified, with different modifiers",
    },
}

LIMITATIONS = """\
- **Candidates come from the linear queries.** A sentence is only parsed if it matches one of the
  RA's nine queries or their mirror images ("if" first); paraphrases outside them ("where an
  alien …", "in the case of any alien", "in the case of the alien") are not looked at.
- **Westlaw vs. this regex.** Westlaw's own sentence boundaries, plurals and equivalents are not
  reproduced; sentences are this pipeline's segmentation (Stanza plus the statutory re-merge pass,
  with condensed chapeaus as one sentence).
- **Parser errors.** Each condition rests on one best UD parse. Attachment of the frame phrase and of
  the if-clause is the weakest point on long sentences, and `same_governor` depends on both: a
  provision of the right shape that the parser attaches differently is missed.
- **Repetition is by head lemma.** "An alien … if an alien" repeats; "an individual … if a person"
  does not. Modifiers are compared as text (amod, acl, nmod, compound dependents of the noun).
- **Syntactic, not interpretive.** A match says the sentence has the provision's shape, not that the
  two noun phrases are read as the same or as different sets.
"""


def _funnel(cands: pd.DataFrame, n_sents: int, pattern: str) -> pd.DataFrame:
    rows = [("matches a linear query (parsed)", n_sents)]
    conds = depquery.PATTERNS[pattern]
    met = cands["pattern"] == pattern
    for k in conds:
        met &= cands[k]
        label = f"+ {CONDITION_TEXT[pattern][k]}" + (" = **match**" if k == conds[-1] else "")
        rows.append((label, int(cands.loc[met, "sent_id"].nunique())))
    return pd.DataFrame(rows, columns=["sentences with a candidate where …", "sentences"])


def summary_md(stage_counts: dict, cls: pd.DataFrame, cands: pd.DataFrame,
               fails: pd.DataFrame, checks: dict) -> str:
    by_query = pd.DataFrame([
        {"query": f"`{q}`", "parsed sentences": int(cls["queries"].map(lambda qs: qid in qs).sum()),
         **{f"matches ({p})": int(cls.loc[cls[f"matches_{p}"], "queries"].map(lambda qs: qid in qs).sum())
            for p in depquery.PATTERNS}}
        for qid, q, _ in ALL_QUERIES])
    near = cls[near_misses(cls)]
    missing = pd.DataFrame([{"pattern": p, "condition not met": k,
                             "near misses": int(((near["best_pattern"] == p) & ~near[f"best_{k}"]).sum())}
                            for p, conds in depquery.PATTERNS.items() for k in conds])
    by_title = (cls.groupby("title").agg(parsed=("sent_id", "size"),
                                         **{f"matches_{p}": (f"matches_{p}", "sum") for p in depquery.PATTERNS}))
    by_title = by_title.loc[sorted(by_title.index, key=title_sort_key)].reset_index()
    prov = cls[cls["identifier"] == PROVISION]
    out = ["# Sentences shaped like 8 U.S.C. § 1225(b)(2)(A): run summary", ""]
    out += ["## Stage counts", "", md_table(pd.DataFrame(
        list(stage_counts.items()), columns=["stage", "count"])), ""]
    for p in depquery.PATTERNS:
        out += [f"## Dependency query: {PATTERN_TEXT[p]}", "",
                "Each row adds one condition; a sentence counts when one (phrase, if) candidate of this "
                "pattern meets all conditions so far.", "", md_table(_funnel(cands, len(cls), p)), ""]
    out += ["## Near misses", "",
            "Best candidate meets all but one of its pattern's conditions (for the phrase before the "
            "if-clause: with the same head).", "", md_table(missing[missing["near misses"] > 0]), ""]
    out += ["## By linear query", "",
            "A sentence can match several queries (`if +s …` ones are the mirror images, not the RA's).",
            "", md_table(by_query), ""]
    out += ["## By title", "", md_table(by_title[by_title["parsed"] > 0]), ""]
    out += ["## 8 U.S.C. § 1225(b)(2)(A)", ""]
    if prov.empty:
        out += ["**Not found in the classified table.**", ""]
    for r in prov.itertuples():
        conds = ", ".join(f"{k} {'✓' if getattr(r, f'best_{k}') else '✗'}"
                          for k in depquery.PATTERNS[r.best_pattern])
        out += [f"- `{r.sent_id}`: matches = **{r.matches}**, pattern {r.best_pattern} ({conds})", "",
                f"  > {r.text}", ""]
    out += ["## Parse failures", "", f"{len(fails)} sentences were not parsed.", ""]
    if len(fails):
        out += [md_table(fails[["sent_id", "error"]].head(50)), ""]
    out += ["## Consistency checks", "", md_table(pd.DataFrame(
        list(checks.items()), columns=["check", "result"])), ""]
    out += ["## Known limitations", "", LIMITATIONS]
    return "\n".join(out)


def report_stage(root: Path, plan: dict[str, list[str]], manifest: dict, stage_counts: dict) -> dict:
    """Write summary.md, then publish (manifest, inputs, checksums)."""
    root = Path(root)
    res = root / "results"
    cls = pd.read_parquet(res / "sentences_classified.parquet")
    cands = pd.read_parquet(res / "candidates.parquet")
    fails = pd.read_parquet(res / "failures.parquet")
    checks = consistency_checks(root, plan)
    (res / "summary.md").write_text(summary_md(stage_counts, cls, cands, fails, checks))
    publish(root, {**manifest, "study": "1225b", "queries": ALL_QUERIES, "counts": stage_counts,
                   "checks": checks})
    return checks


STUDY = Study(name="1225b", unit_patterns=(ANY_QUERY,), sentence_pattern=ANY_QUERY,
              parser="electra-dep", classify=classify_stage, report=report_stage)
