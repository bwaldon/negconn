# negconn

Negated connectives in the primary statutory text of the U.S. Code: negative conjunctions
(`… not … and …`) and negative disjunctions (`… not … or …`). Every matching sentence is
constituency-parsed with Stanza, and the pipeline flags those where *not* is the child of a VP that
dominates the coordination (criterion C2). The method adapts the negative-disjunction search in the
Champollion et al. amicus brief in *Campos-Chaves v. Garland* (Nos. 22-674 & 22-884).

**Dashboard:** <https://bwaldon.github.io/negconn/>. All 41,869 flagged sentences from both runs,
with their trees. Pick a connective (*and*, *or*, or both) and search or filter by text, citation,
title, unit type, coordination label and position (e.g. inside an *if*-clause, with *not* and the
coordination both in it). Review marks can be saved in the browser and exported as CSV. The pages
load per-title tree files on demand, so the site also works opened from disk
(`site/index.html` after building).

**Also here:** [`barbosa/`](barbosa/README.md), U.S. Code sentences shaped like 8 U.S.C.
§ 1225(b)(2)(A) (*in the case of an alien who …, if … an alien seeking admission …*), found with a
dependency-parse query over the RA's linear-query hits. Dashboard:
<https://bwaldon.github.io/negconn/1225b/>.

## Pipeline

The Python package and the Modal app and Volume are still named `negconj` (and `negconj-data`).

A run carries out one study (`--study`, see `negconj/study.py`): `and` and `or` are the negated
connectives (`negconj/connectives.py`: prefilter, sentence regex, C2 classification and summary;
only the connective changes between them), `1225b` is the study in `barbosa/`. Extraction,
segmentation, sharded and checkpointed parsing, merge, consistency checks and the dashboard
scaffolding (`negconj/dashboard.py`, `negconj/assets/`) are shared by every study.

| Stage | Module | What it does |
|---|---|---|
| Extract | `negconj/uslm_extract.py` | USLM XML → text units; notes and footnote markers removed; chapeaus condensed into one sentence |
| Plan | `negconj/shards.py` | prefilter units with the study's patterns (here: both *not* and the connective); group sections into GPU shards |
| Segment | `negconj/segment.py` | Stanza sentence splitting plus a re-merge pass for statutory punctuation; the study's regex (here `\bnot\b.*\b(and|or)\b`) picks the sentences to parse |
| Parse | `negconj/parse.py` | Stanza constituency parser (`ptb3-revised_electra-large`), one best tree per sentence (the dependency parser for `1225b`); matches over 4,000 tokens are recorded as failures, not parsed |
| Classify | `negconj/classify.py`, `negconj/connectives.py` | C2 for every (not, connective) pair: *not*'s parent is a VP that dominates the coordination node |
| Report | `negconj/report.py`, `negconj/connectives.py` | consistency checks, stratified review sample, summary, manifest, checksums |
| Run | `negconj/modal_app.py`, `scripts/launch.py` | Modal orchestration on L4 GPUs (A10G, then L40S, when no L4 is free); resumable, checkpointed per section |

The disjunction run reuses a tree from the conjunction run when a sentence matches both patterns
and its tokens and model package are identical (25,098 sentences).

`negconj_workplan.md` is the original specification for the conjunction study; `RUNLOG.md` records
every decision, count and anomaly, including where the code departs from the work plan.

## Running

```sh
python3.12 -m venv .venv && .venv/bin/pip install -e .
.venv/bin/pytest                                     # unit, checkpoint and Pulsifer regression tests
.venv/bin/python scripts/run_local.py --titles 29 18 # local CPU run (--study and|or|1225b)
source scripts/modal_env.sh                          # Modal token from .env (not committed)
.venv/bin/python scripts/launch.py --run full --target-chars 2000000 --gpu-budget-seconds 45000
.venv/bin/python scripts/launch.py --run disj --study or --reuse-run full --target-chars 2000000 \
    --gpu-budget-seconds 30000 --no-deploy
scripts/watch_run.sh disj                            # follow a run's orchestrator log
scripts/pull_results.sh full                         # -> results/ (checksums verified)
scripts/pull_results.sh disj                         # -> results_disj/
.venv/bin/python scripts/build_dashboard.py --and results --or results_disj --out site
```

## Results (release point 119-121)

| | not … and | not … or |
|---|---|---|
| regex matches | 44,517 | 49,546 |
| parsed | 44,513 | 49,541 |
| not parsed (> 4,000 tokens) | 4 | 5 |
| flagged (C2) | 13,246 | 28,623 |
| regression case | Pulsifer, 18 U.S.C. § 3553(f): flagged | Campos-Chaves, 8 U.S.C. § 1229a(b)(5)(C): flagged |

Per-run detail is in `results*/summary.md` (not committed; produced by the report stage). The
result tables also carry a *relaxed* variant of C2 (skipping unary nodes such as `(ADVP (RB not))`
above *not*); it adds 19 (*and*) and 35 (*or*) sentences and is not shown on the dashboard.

## Limitations

Recall is bounded by the surface pattern (no *n't*, *cannot*, *nor*, *without*, *no*). Parser
accuracy degrades on very long condensed-chapeau sentences, and the longest (over 4,000 tokens;
4 conjunction and 5 disjunction matches, in Titles 34 and 42) are not parsed at all. The flag is
syntactic: it does not judge which scope reading is correct in context.
