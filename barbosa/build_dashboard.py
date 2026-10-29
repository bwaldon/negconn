"""Build the static dashboard for the 1225b run.

    python -m barbosa.build_dashboard --results barbosa/results --out site/1225b

Every parsed sentence is included (the page filters to dependency-query matches by default).
Writes ``{out}/index.html`` plus ``data/index.js`` (sentences, linear queries, the dependency
query's candidates: everything filtering and the text view need) and ``data/parses-{title}.js``
(CoNLL-U, loaded when a sentence is opened). Published as bwaldon.github.io/negconn/1225b,
next to the negated-connectives dashboard.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from negconj.dashboard import manifest_meta, render_page, write_call
from negconj.util import title_sort_key

from .depquery import CONDITIONS, REQUIRED, read_conllu
from .study import PROVISION, QUERIES, CONDITION_TEXT

HERE = Path(__file__).resolve().parent
QUERY_INDEX = {qid: i for i, (qid, _, _) in enumerate(QUERIES)}
ROLE_COLUMNS = ["phrase_start", "phrase_end", "det1", "n1", "frame", "governor", "mark", "if_head",
                "n2", "det2"]


def _bits(c) -> int:
    return sum(1 << k for k, name in enumerate(CONDITIONS) if bool(c[name]))


def _spans(v) -> list[list[int]]:
    return [[int(a), int(b)] for a, b in v]


def build(results: Path, out: Path) -> dict:
    cls = pd.read_parquet(results / "sentences_classified.parquet")
    cands = pd.read_parquet(results / "candidates.parquet")
    fails = pd.read_parquet(results / "failures.parquet")
    by_sent = {sid: g for sid, g in cands.groupby("sent_id", sort=False)}
    rows, parses = [], {}
    for r in cls.itertuples(index=False):
        words = [w.form for w in read_conllu(r.conllu).words]
        cs = [[QUERY_INDEX[c.query], *(int(getattr(c, k)) for k in ROLE_COLUMNS),
               _spans(c.mods1), _spans(c.mods2), _bits(c._asdict())]
              for c in by_sent[r.sent_id].itertuples(index=False)] if r.sent_id in by_sent else []
        rows.append([r.sent_id, str(r.title), r.identifier, r.elem_source, " ".join(words),
                     [QUERY_INDEX[q] for q in r.queries], bool(r.matches), bool(r.strict),
                     int(r.best_n_met), int(r.best), cs])
        parses.setdefault(str(r.title), {})[r.sent_id] = r.conllu
    d = out / "data"
    meta = {"run": results.resolve().name, "manifest": manifest_meta(results), "provision": PROVISION,
            "queries": [[qid, q, phrase] for qid, q, phrase in QUERIES],
            "conditions": [[k, CONDITION_TEXT[k]] for k in CONDITIONS], "n_required": len(REQUIRED),
            "n_failures": len(fails), "titles": sorted(parses, key=title_sort_key)}
    write_call(d / "index.js", "DEP.index", {**meta, "rows": rows})
    for title, pmap in parses.items():
        write_call(d / f"parses-{title}.js", "DEP.parses", title, pmap)
    render_page(HERE / "dashboard_template.html", out / "index.html", ["1225b"])
    sizes = {p.name: p.stat().st_size for p in d.iterdir()}
    return {"rows": len(rows), "matches": int(cls["matches"].sum()), "strict": int(cls["strict"].sum()),
            "index_mb": sizes["index.js"] / 1e6,
            "parses_mb": sum(v for k, v in sizes.items() if k.startswith("parses")) / 1e6}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", type=Path, default=Path("barbosa/results"))
    ap.add_argument("--out", type=Path, default=Path("site/1225b"))
    a = ap.parse_args()
    print(build(a.results, a.out))
    print(f"wrote {a.out / 'index.html'}")


if __name__ == "__main__":
    main()
