"""The dependency query: sentences shaped like 8 U.S.C. § 1225(b)(2)(A).

    Subject to subparagraphs (B) and (C), in the case of [an alien]N1 [who is an applicant for
    admission]mod1, if the examining immigration officer determines that [an alien]N2 [seeking
    admission]mod2 is not clearly and beyond a doubt entitled to be admitted, the alien shall be
    detained for a proceeding under section 1229a of this title.

Its UD parse (Stanza, depparse combined_electra-large), the parts the query looks at:

    detained ─obl→ case ─nmod→ alien (N1) ─acl:relcl→ applicant
        └─advcl→ determines ─mark→ if
                     └─ccomp→ entitled ─nsubj→ alien (N2) ─acl→ seeking

Parses are read from CoNLL-U (negconj.parse, kind "dependency"); word indices here are 0-based
(CoNLL-U ID − 1) and a head of -1 is the root.

Definitions
-----------
frame phrase   one of the RA's phrases ("in the case of", "with respect to", …; barbosa.study),
               matched on lowercased word forms and immediately followed by "a" or "an".
N1             the word that this "a"/"an" is the ``det`` of: the head of the indefinite noun
               phrase. Must be a NOUN or PROPN.
frame          the lowest word dominating both the first word of the frame phrase and N1: for
               "in the case of an alien", "case"; for "with respect to an alien" parsed as a
               fixed expression, N1 itself.
governor       the frame's head (what the frame phrase modifies).
if-clause      a word "if" attached as ``mark``, after N1's determiner; the clause is its head H
               and everything H dominates.
modifier       a dependent of a noun whose relation is amod, acl (acl:relcl, …), nmod (nmod:*,
               …) or compound. A noun's modifier text is every word its modifiers dominate, in
               sentence order, so the same words attached differently compare as equal.

Conditions, checked for every (frame phrase, if) candidate in a sentence
------------------------------------------------------------------------
frame_np        the frame phrase introduces an indefinite noun phrase (N1 exists).
if_outside      an if-clause comes after N1's determiner and lies outside the frame (H is not
                dominated by the frame).
repeated_np     the if-clause contains another indefinite noun phrase N2 ("a"/"an" as its det)
                whose head has N1's lemma.
different_mods  N1 and N2 both have modifiers, and their modifier texts differ.
same_governor   H and the frame are dependents of the same governor: both modify the main
                clause, as in the provision.

The first four are the two structural properties asked for (an indefinite noun phrase after the
phrase; an if-clause that repeats it with a different modifier): a sentence **matches** when one
candidate meets them. It is a **strict** match when that candidate also meets same_governor. The
best candidate is a strict match if there is one, else a match, else the one meeting the most
conditions (ties: the longest run of conditions met in the order above, then the earliest).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

INDEFINITE = frozenset({"a", "an"})
NOMINAL = frozenset({"NOUN", "PROPN"})
MODIFIER_RELS = frozenset({"amod", "acl", "nmod", "compound"})
CONDITIONS = ("frame_np", "if_outside", "repeated_np", "different_mods", "same_governor")
REQUIRED = CONDITIONS[:4]


@dataclass(frozen=True)
class Word:
    form: str
    lemma: str
    upos: str
    xpos: str
    feats: str
    head: int  # 0-based; -1 for the root
    deprel: str


class DepTree:
    """Words of one sentence with child lists and dominance."""

    def __init__(self, words: list[Word]):
        self.words = words
        self.children: list[list[int]] = [[] for _ in words]
        for i, w in enumerate(words):
            if w.head >= 0:
                self.children[w.head].append(i)
        self.lower = [w.form.lower() for w in words]

    def __len__(self) -> int:
        return len(self.words)

    def head(self, i: int) -> int:
        return self.words[i].head if i >= 0 else -1

    def ancestors(self, i: int) -> list[int]:
        """i, its head, its head's head, … up to the root."""
        out, seen = [], set()
        while i >= 0 and i not in seen:  # a malformed cycle ends the walk
            out.append(i)
            seen.add(i)
            i = self.words[i].head
        return out

    def dominates(self, a: int, b: int) -> bool:
        """a dominates b or is b."""
        return a in self.ancestors(b)

    def lca(self, a: int, b: int) -> int:
        up = set(self.ancestors(a))
        return next((x for x in self.ancestors(b) if x in up), -1)

    def subtree(self, i: int) -> list[int]:
        out, stack = [], [i]
        while stack:
            n = stack.pop()
            out.append(n)
            stack.extend(self.children[n])
        return sorted(out)

    def text(self, idx: list[int]) -> str:
        return " ".join(self.words[i].form for i in idx)

    def det_of(self, i: int) -> int:
        """The noun an "a"/"an" at i is the det of, or -1."""
        w = self.words[i]
        if self.lower[i] in INDEFINITE and w.deprel.split(":")[0] == "det" and w.head >= 0:
            return w.head
        return -1

    def indefinite_det(self, n: int) -> int:
        """The "a"/"an" det child of n, or -1."""
        return next((c for c in self.children[n] if self.det_of(c) == n), -1)

    def modifiers(self, n: int) -> list[int]:
        return [c for c in self.children[n] if self.words[c].deprel.split(":")[0] in MODIFIER_RELS]


def read_conllu(text: str) -> DepTree:
    """Words of a CoNLL-U sentence (range and empty-node lines skipped)."""
    words = []
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        f = line.split("\t")
        if "-" in f[0] or "." in f[0]:
            continue
        words.append(Word(f[1], f[2], f[3], f[4], f[5], int(f[6]) - 1, f[7]))
    return DepTree(words)


@dataclass
class Candidate:
    query: str           # id of the RA query whose phrase this is
    phrase: tuple[int, int]  # first and last word of the frame phrase
    det1: int            # the "a"/"an" after the phrase
    n1: int = -1
    frame: int = -1
    governor: int = -1
    mark: int = -1       # "if"
    if_head: int = -1
    n2: int = -1
    det2: int = -1
    mods1: list[int] = field(default_factory=list)
    mods2: list[int] = field(default_factory=list)
    met: dict = field(default_factory=lambda: dict.fromkeys(CONDITIONS, False))

    @property
    def n_met(self) -> int:
        return sum(self.met.values())

    @property
    def run(self) -> int:
        """How many conditions hold in a row, in CONDITIONS order."""
        k = 0
        while k < len(CONDITIONS) and self.met[CONDITIONS[k]]:
            k += 1
        return k

    @property
    def matches(self) -> bool:
        return all(self.met[k] for k in REQUIRED)

    @property
    def strict(self) -> bool:
        return self.matches and self.met["same_governor"]


def _mod_text(t: DepTree, mods: list[int]) -> str:
    return t.text(sorted(i for m in mods for i in t.subtree(m))).lower()


def _repeat(t: DepTree, n1: int, if_head: int) -> tuple[int, int]:
    """Best N2 for N1 inside the if-clause: (n2, det2), preferring one with modifiers that
    differ from N1's; (-1, -1) if there is none."""
    lemma = t.words[n1].lemma.lower()
    found = [(n, t.indefinite_det(n)) for n in t.subtree(if_head)
             if n != n1 and t.words[n].upos in NOMINAL and t.words[n].lemma.lower() == lemma
             and t.indefinite_det(n) >= 0]
    if not found:
        return -1, -1
    m1 = _mod_text(t, t.modifiers(n1))
    differs = [f for f in found if t.modifiers(f[0]) and _mod_text(t, t.modifiers(f[0])) != m1]
    return (differs or found)[0]


def candidates(t: DepTree, phrases: dict[str, tuple[str, ...]]) -> list[Candidate]:
    """Every (frame phrase, if) candidate; ``phrases`` maps query id -> lowercased phrase words."""
    marks = [i for i in range(len(t)) if t.lower[i] == "if" and t.words[i].deprel == "mark"]
    out = []
    for qid, ph in phrases.items():
        k = len(ph)
        for i in range(len(t) - k):
            if tuple(t.lower[i:i + k]) != ph or t.lower[i + k] not in INDEFINITE:
                continue
            base = dict(query=qid, phrase=(i, i + k - 1), det1=i + k)
            n1 = t.det_of(i + k)
            if n1 < 0 or t.words[n1].upos not in NOMINAL:
                out.append(Candidate(**base))
                continue
            frame = t.lca(i, n1)
            later = [m for m in marks if m > i + k] or [-1]
            for m in later:
                c = Candidate(**base, n1=n1, frame=frame, governor=t.head(frame), mark=m,
                              mods1=t.modifiers(n1))
                c.met["frame_np"] = True
                if m >= 0:
                    c.if_head = t.head(m)
                    c.met["if_outside"] = c.if_head >= 0 and not t.dominates(frame, c.if_head)
                    c.met["same_governor"] = (c.governor >= 0 and c.if_head not in (-1, frame)
                                              and t.head(c.if_head) == c.governor)
                    if c.if_head >= 0:
                        c.n2, c.det2 = _repeat(t, n1, c.if_head)
                    c.met["repeated_np"] = c.n2 >= 0
                    if c.n2 >= 0:
                        c.mods2 = t.modifiers(c.n2)
                        c.met["different_mods"] = bool(c.mods1 and c.mods2) and (
                            _mod_text(t, c.mods1) != _mod_text(t, c.mods2))
                out.append(c)
    return out


def best(cands: list[Candidate]) -> Candidate | None:
    if not cands:
        return None
    return max(cands, key=lambda c: (c.strict, c.matches, c.n_met, c.run, -c.phrase[0], -c.mark))


# --------------------------------------------------------------------------
# Tables
# --------------------------------------------------------------------------

def _span(t: DepTree, i: int) -> list[int]:
    """First and last word that i dominates ([-1, -1] for no word)."""
    if i < 0:
        return [-1, -1]
    s = t.subtree(i)
    return [s[0], s[-1]]


def candidate_row(sent_id: str, t: DepTree, c: Candidate) -> dict:
    return {
        "sent_id": sent_id, "query": c.query, "phrase_start": c.phrase[0], "phrase_end": c.phrase[1],
        "det1": c.det1, "n1": c.n1, "frame": c.frame, "governor": c.governor, "mark": c.mark,
        "if_head": c.if_head, "n2": c.n2, "det2": c.det2,
        "n1_lemma": t.words[c.n1].lemma if c.n1 >= 0 else None,
        "mods1": [_span(t, m) for m in c.mods1], "mods2": [_span(t, m) for m in c.mods2],
        "frame_span": _span(t, c.frame), "if_span": _span(t, c.if_head),
        "if_deprel": t.words[c.if_head].deprel if c.if_head >= 0 else None,
        **c.met, "n_met": c.n_met, "matches": c.matches, "strict": c.strict,
    }


CANDIDATE_COLUMNS = list(candidate_row("", DepTree([]), Candidate("", (0, 0), 0)).keys())


def classify_conllu(sent_id: str, conllu: str,
                    phrases: dict[str, tuple[str, ...]]) -> tuple[list[dict], dict]:
    """(candidate rows, sentence summary) for one parse."""
    t = read_conllu(conllu)
    cands = candidates(t, phrases)
    rows = [candidate_row(sent_id, t, c) for c in cands]
    b = best(cands)
    summary = {"sent_id": sent_id, "n_words": len(t), "n_candidates": len(cands),
               "matches": any(c.matches for c in cands), "strict": any(c.strict for c in cands),
               "best": cands.index(b) if b is not None else -1,
               **{f"best_{k}": (b.met[k] if b is not None else False) for k in CONDITIONS},
               "best_n_met": b.n_met if b is not None else 0}
    return rows, summary


SENTENCE_COLUMNS = ["sent_id", "n_words", "n_candidates", "matches", "strict", "best",
                    *[f"best_{k}" for k in CONDITIONS], "best_n_met"]


def classify_frame(parses: pd.DataFrame,
                   phrases: dict[str, tuple[str, ...]]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Candidates and per-sentence results for a parses table (needs sent_id, conllu).
    Returns (candidates, sentences), sentences being the input with the summary joined on."""
    rows: list[dict] = []
    summaries: list[dict] = []
    for sid, conllu in zip(parses["sent_id"], parses["conllu"]):
        r, s = classify_conllu(sid, conllu, phrases)
        rows.extend(r)
        summaries.append(s)
    cands = pd.DataFrame(rows, columns=CANDIDATE_COLUMNS)
    summ = pd.DataFrame(summaries, columns=SENTENCE_COLUMNS)
    return cands, parses.merge(summ, on="sent_id", how="left", validate="one_to_one")
