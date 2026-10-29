"""The 1225b study: the RA's linear queries, the dependency query, and the regression case
8 U.S.C. § 1225(b)(2)(A), which must match.

fixtures/s1225b2.json holds 1225(b)(2)(A)–(C) as segmented and parsed by the pipeline's
tokenizer and the "electra-dep" parser. The last test reads the results directory in
$BARBOSA_RESULTS (default barbosa/results) when it exists.
"""

import json
import os
from pathlib import Path

import pandas as pd
import pytest

from barbosa import depquery as dq
from barbosa.study import ANY_QUERY, PHRASES, PROVISION, QUERIES, queries_matching

HERE = Path(__file__).resolve().parent
FIXTURE = {r["identifier"]: r for r in json.loads((HERE / "fixtures" / "s1225b2.json").read_text())}
A = FIXTURE[PROVISION]
RESULTS = Path(os.environ.get("BARBOSA_RESULTS", HERE.parent / "results"))


def conllu(rows):
    """CoNLL-U from (form, lemma, upos, head, deprel) rows; heads are 1-based, 0 = root."""
    return "\n".join(f"{i}\t{f}\t{l}\t{u}\t_\t_\t{h}\t{d}\t_\t_"
                     for i, (f, l, u, h, d) in enumerate(rows, 1))


def edit(text, changes):
    """Change columns of CoNLL-U lines: {word id: {column index: value}}."""
    out = []
    for line in text.splitlines():
        f = line.split("\t")
        for col, v in changes.get(int(f[0]) if f[0].isdigit() else None, {}).items():
            f[col] = str(v)
        out.append("\t".join(f))
    return "\n".join(out)


def summary(text):
    return dq.classify_conllu("s", text, PHRASES)[1]


def met(text):
    s = summary(text)
    return {k for k in dq.CONDITIONS if s[f"best_{k}"]}


# --------------------------------------------------------------------------
# Linear queries
# --------------------------------------------------------------------------

def test_queries_cover_the_screenshot():
    assert len(QUERIES) == 9 and len(PHRASES) == 9
    assert all(q.startswith("adv: (") and q.endswith("+s if +s (a OR an)") for _, q, _ in QUERIES)


@pytest.mark.parametrize("qid,_q,phrase", QUERIES)
def test_each_query(qid, _q, phrase):
    assert queries_matching(f"{phrase.capitalize()} an employer, if a plan fails") == [qid]
    assert queries_matching(f"x {phrase} a person who, IF NOT, an y") == [qid]
    assert not queries_matching(f"if a plan fails, {phrase} an employer")  # if must follow
    assert not queries_matching(f"{phrase} any employer, if a plan fails")  # a/an right after
    assert not queries_matching(f"{phrase} an employer, iff a plan fails")  # whole words
    assert not queries_matching(f"{phrase} an employer, if the plan fails")


def test_provision_matches_case_of_only():
    assert queries_matching(A["text"]) == ["case_of"]
    assert ANY_QUERY.search(A["text"])
    assert not ANY_QUERY.search(FIXTURE["/us/usc/t8/s1225/b/2/C"]["text"])  # no "if"


# --------------------------------------------------------------------------
# Dependency query
# --------------------------------------------------------------------------

def test_provision_matches_all_conditions():
    rows, s = dq.classify_conllu("a", A["conllu"], PHRASES)
    assert s["matches"] and s["strict"] and s["best_n_met"] == 5
    [r] = rows
    t = dq.read_conllu(A["conllu"])
    w = lambda i: t.words[i].form
    assert (w(r["frame"]), w(r["governor"]), w(r["mark"]), w(r["if_head"])) == \
        ("case", "detained", "if", "determines")
    assert w(r["n1"]) == w(r["n2"]) == "alien" and r["n1"] < r["mark"] < r["n2"]
    assert t.text(list(range(r["mods1"][0][0], r["mods1"][0][1] + 1))) == "who is an applicant for admission"
    assert t.text(list(range(r["mods2"][0][0], r["mods2"][0][1] + 1))) == "seeking admission"


def test_neighbouring_paragraph_has_no_if_clause():
    assert met(FIXTURE["/us/usc/t8/s1225/b/2/C"]["conllu"]) == {"frame_np"}


# Word ids in the provision's CoNLL-U (see the module docstring of depquery).
CASE, ALIEN2, SEEKING, DETERMINES, APPLICANT, DETAINED = 14, 33, 34, 30, 21, 52


def test_ids_of_the_fixture():
    t = dq.read_conllu(A["conllu"])
    assert [t.words[i - 1].form for i in (CASE, ALIEN2, SEEKING, DETERMINES, APPLICANT, DETAINED)] == \
        ["case", "alien", "seeking", "determines", "applicant", "detained"]


def test_unmodified_repeat_is_not_different_mods():
    text = edit(A["conllu"], {SEEKING: {6: 43, 7: "advcl"}})  # "seeking" leaves the noun
    assert met(text) == set(dq.CONDITIONS) - {"different_mods"}


def test_other_noun_is_not_a_repeat():
    text = edit(A["conllu"], {ALIEN2: {1: "person", 2: "person"}})
    assert met(text) == {"frame_np", "if_outside", "same_governor"}


def test_if_clause_inside_the_frame():
    text = edit(A["conllu"], {DETERMINES: {6: APPLICANT, 7: "advcl"}})  # if-clause under the relcl
    assert {"if_outside", "same_governor"}.isdisjoint(met(text))


def test_frame_attached_inside_the_if_clause_is_not_same_governor():
    text = edit(A["conllu"], {CASE: {6: DETERMINES}})
    assert met(text) == set(dq.CONDITIONS) - {"same_governor"}
    assert summary(text)["matches"] and not summary(text)["strict"]  # a match, not a strict one


def test_frame_at_the_root():
    """A fragment parse with the phrase's head as root: no governor, so no same_governor."""
    text = edit(A["conllu"], {CASE: {6: 0, 7: "root"}, DETAINED: {6: CASE, 7: "acl"},
                              DETERMINES: {6: CASE, 7: "advcl"}})
    assert met(text) == {"frame_np"} | {"repeated_np", "different_mods"}
    assert dq.read_conllu(text).head(-1) == -1


PLAN = [("In", "in", "ADP", 3, "case"), ("the", "the", "DET", 3, "det"), ("case", "case", "NOUN", 18, "obl"),
        ("of", "of", "ADP", 7, "case"), ("a", "a", "DET", 7, "det"), ("covered", "cover", "VERB", 7, "amod"),
        ("plan", "plan", "NOUN", 3, "nmod"), (",", ",", "PUNCT", 3, "punct"), ("if", "if", "SCONJ", 13, "mark"),
        ("a", "a", "DET", 12, "det"), ("covered", "cover", "VERB", 12, "amod"), ("plan", "plan", "NOUN", 13, "nsubj"),
        ("fails", "fail", "VERB", 18, "advcl"), (",", ",", "PUNCT", 13, "punct"), ("the", "the", "DET", 16, "det"),
        ("sponsor", "sponsor", "NOUN", 18, "nsubj"), ("shall", "shall", "AUX", 18, "aux"), ("pay", "pay", "VERB", 0, "root"),
        (".", ".", "PUNCT", 18, "punct")]


def test_same_modifier_is_not_different():
    assert met(conllu(PLAN)) == set(dq.CONDITIONS) - {"different_mods"}
    other = list(PLAN)
    other[10] = ("qualified", "qualified", "ADJ", 12, "amod")
    assert summary(conllu(other))["matches"]


CREDIT = [("In", "in", "ADP", 3, "case"), ("the", "the", "DET", 3, "det"), ("case", "case", "NOUN", 26, "obl"),
          ("of", "of", "ADP", 6, "case"), ("an", "a", "DET", 6, "det"), ("extension", "extension", "NOUN", 3, "nmod"),
          ("of", "of", "ADP", 8, "case"), ("credit", "credit", "NOUN", 6, "nmod"), ("secured", "secure", "VERB", 6, "acl"),
          ("by", "by", "ADP", 11, "case"), ("land", "land", "NOUN", 9, "obl"), (",", ",", "PUNCT", 3, "punct"),
          ("if", "if", "SCONJ", 21, "mark"), ("an", "a", "DET", 15, "det"), ("extension", "extension", "NOUN", 21, "nsubj"),
          ("of", "of", "ADP", 17, "case"), ("credit", "credit", "NOUN", 15, "nmod"), ("secured", "secure", "VERB", 17, "acl"),
          ("by", "by", "ADP", 20, "case"), ("land", "land", "NOUN", 18, "obl"), ("fails", "fail", "VERB", 26, "advcl"),
          (",", ",", "PUNCT", 21, "punct"), ("the", "the", "DET", 24, "det"), ("lender", "lender", "NOUN", 26, "nsubj"),
          ("shall", "shall", "AUX", 26, "aux"), ("pay", "pay", "VERB", 0, "root"), (".", ".", "PUNCT", 26, "punct")]


def test_same_modifier_words_attached_differently():
    """N1 has 'of credit' and 'secured by land' as two modifiers, N2 one modifier with both: same words."""
    assert met(conllu(CREDIT)) == set(dq.CONDITIONS) - {"different_mods"}
    other = list(CREDIT)
    other[19] = ("water", "water", "NOUN", 18, "obl")
    assert summary(conllu(other))["strict"]


def test_parallel_frame_is_not_a_repeat():
    """'… if in the case of a qualified plan …': the second plan is a new frame's N1."""
    rows = [("In", "in", "ADP", 3, "case"), ("the", "the", "DET", 3, "det"), ("case", "case", "NOUN", 22, "obl"),
            ("of", "of", "ADP", 7, "case"), ("a", "a", "DET", 7, "det"), ("covered", "cover", "VERB", 7, "amod"),
            ("plan", "plan", "NOUN", 3, "nmod"), (",", ",", "PUNCT", 3, "punct"), ("if", "if", "SCONJ", 17, "mark"),
            ("in", "in", "ADP", 12, "case"), ("the", "the", "DET", 12, "det"), ("case", "case", "NOUN", 17, "obl"),
            ("of", "of", "ADP", 16, "case"), ("a", "a", "DET", 16, "det"), ("qualified", "qualified", "ADJ", 16, "amod"),
            ("plan", "plan", "NOUN", 12, "nmod"), ("fails", "fail", "VERB", 22, "advcl"), (",", ",", "PUNCT", 17, "punct"),
            ("the", "the", "DET", 20, "det"), ("sponsor", "sponsor", "NOUN", 22, "nsubj"), ("shall", "shall", "AUX", 22, "aux"),
            ("pay", "pay", "VERB", 0, "root"), (".", ".", "PUNCT", 22, "punct")]
    assert met(conllu(rows)) == {"frame_np", "if_outside", "same_governor"}


def test_fixed_expression_frame():
    """'With respect to' parsed as a fixed expression: the frame is N1 itself."""
    rows = [("With", "with", "ADP", 5, "case"), ("respect", "respect", "NOUN", 1, "fixed"),
            ("to", "to", "ADP", 1, "fixed"), ("an", "a", "DET", 5, "det"), ("employee", "employee", "NOUN", 20, "obl"),
            ("who", "who", "PRON", 7, "nsubj"), ("retires", "retire", "VERB", 5, "acl:relcl"),
            (",", ",", "PUNCT", 5, "punct"), ("if", "if", "SCONJ", 15, "mark"), ("an", "a", "DET", 11, "det"),
            ("employee", "employee", "NOUN", 15, "nsubj"), ("in", "in", "ADP", 14, "case"),
            ("a", "a", "DET", 14, "det"), ("union", "union", "NOUN", 11, "nmod"), ("quits", "quit", "VERB", 20, "advcl"),
            (",", ",", "PUNCT", 15, "punct"), ("the", "the", "DET", 18, "det"), ("plan", "plan", "NOUN", 20, "nsubj"),
            ("shall", "shall", "AUX", 20, "aux"), ("pay", "pay", "VERB", 0, "root"), (".", ".", "PUNCT", 20, "punct")]
    [r], s = dq.classify_conllu("w", conllu(rows), PHRASES)
    assert s["matches"] and r["query"] == "with_respect_to" and r["frame"] == r["n1"] == 4


def test_best_candidate():
    def cand(phrase, mark, conds):
        c = dq.Candidate("case_of", (phrase, phrase + 3), phrase + 4, mark=mark)
        c.met.update(dict.fromkeys(conds, True))
        return c
    early = cand(0, 10, ["frame_np", "repeated_np", "different_mods"])     # 3 met, run 1
    late = cand(0, 20, ["frame_np", "if_outside", "same_governor"])       # 3 met, run 2
    match = cand(0, 30, dq.REQUIRED)                                      # a match, not strict
    four = cand(0, 40, ["frame_np", "if_outside", "repeated_np", "same_governor"])
    full = cand(30, 40, dq.CONDITIONS)
    assert dq.best([early, late]) is late
    assert dq.best([four, match]) is match and match.matches and not match.strict
    assert dq.best([early, late, match, full]) is full and full.strict
    assert dq.best([cand(0, 10, ["frame_np"]), cand(0, 20, ["frame_np"])]).mark == 10
    assert dq.best([]) is None


def test_classify_frame_columns():
    parses = pd.DataFrame({"sent_id": ["a", "c"], "conllu": [A["conllu"], FIXTURE["/us/usc/t8/s1225/b/2/C"]["conllu"]]})
    cands, sents = dq.classify_frame(parses, PHRASES)
    assert list(cands.columns) == dq.CANDIDATE_COLUMNS and len(cands) == 2
    assert sents["matches"].tolist() == [True, False] and sents["best_n_met"].tolist() == [5, 1]
    assert sents["strict"].tolist() == [True, False]


# --------------------------------------------------------------------------
# Regression on a finished run
# --------------------------------------------------------------------------

@pytest.mark.skipif(not (RESULTS / "sentences_classified.parquet").exists(), reason="no 1225b results yet")
def test_provision_matches_in_results():
    cls = pd.read_parquet(RESULTS / "sentences_classified.parquet")
    hit = cls[cls["identifier"] == PROVISION]
    assert len(hit) == 1 and bool(hit.iloc[0]["matches"]) and bool(hit.iloc[0]["strict"])
    assert list(hit.iloc[0]["queries"]) == ["case_of"]
    assert list(hit.iloc[0]["tokens"]) == A["tokens"]
