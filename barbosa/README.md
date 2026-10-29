# Sentences shaped like 8 U.S.C. § 1225(b)(2)(A)

> Subject to subparagraphs (B) and (C), **in the case of an alien who is an applicant for
> admission**, **if** the examining immigration officer determines that **an alien seeking
> admission** is not clearly and beyond a doubt entitled to be admitted, the alien shall be detained
> for a proceeding under section 1229a of this title.

Which other U.S. Code provisions share this structure?

1. A phrase like *in the case of* followed by an indefinite noun phrase (*an alien who is an
   applicant for admission*; *a*/*an* signals indefiniteness), and
2. an *if*-clause (a conditional antecedent) that repeats that indefinite noun phrase with a
   different modifier (*an alien seeking admission*).

**Dashboard:** <https://bwaldon.github.io/negconn/1225b/>. Every sentence the RA's linear queries
find, with its dependency parse. By default the list shows the sentences the dependency query
matches; it can also show only strict matches, near misses (three of the four conditions of a
match) or everything, filtered by the condition not met, the RA's query, title, unit type or text. Review marks are saved in the
browser and can be exported as CSV.

## Method

**Candidates: the RA's linear queries.** Nine Westlaw queries of the form
`adv: ("in the case #of a" OR "in the case #of an") +s if +s (a OR an)`, with *in the case of*,
*with regard to*, *regarding*, *concerning*, *respecting*, *in regard to*, *with respect to*,
*in the event that* and *in the event of* (`study.QUERIES`, transcribed from the RA's list). Each
becomes a case-insensitive regex over one sentence: the phrase, then *a* or *an*, later *if*, later
*a* or *an*, all whole words (`+s` is "precedes, in the same sentence"; `#` only turns off
Westlaw's plurals and equivalents). Sentences are the pipeline's own segmentation of the extracted
statutory text (release point 119-121, condensed chapeaus as one sentence), the same units as the
negated-connective runs.

**Parse.** Every matching sentence is dependency-parsed with Stanza in Universal Dependencies
(parser config `electra-dep`: pos `combined_electra-large`, lemma `combined_charlm`, depparse
`combined_electra-large`, Stanza's most accurate English models), one best parse per sentence,
on Modal GPUs (L4, falling back to A10G or L40S). Sentences over 4,000 tokens are recorded as failures, not parsed.

**Dependency query** (`depquery.py`). In the provision's parse, *case* (with *in the* and the
*of*-phrase *an alien who is an applicant for admission*) and the *if*-clause headed by
*determines* are both dependents of the main verb *detained*; the second *alien* sits inside the
*if*-clause with its own modifier *seeking admission*:

```
detained ─obl→ case ─nmod→ alien (N1) ─acl:relcl→ applicant      who is an applicant for admission
    └─advcl→ determines ─mark→ if
                 └─ccomp→ entitled ─nsubj→ alien (N2) ─acl→ seeking      seeking admission
```

For each candidate pair (one occurrence of a query phrase + *a*/*an*, one *if*), five conditions:

| condition | holds when |
|---|---|
| `frame_np` | the *a*/*an* after the phrase is the `det` of a noun N1: an indefinite noun phrase |
| `if_outside` | an *if* attached as `mark` comes after it, and its clause is outside the phrase (not dominated by the phrase's head, e.g. *case*) |
| `repeated_np` | the *if*-clause contains another noun with N1's lemma whose `det` is *a*/*an* (N2) |
| `different_mods` | N1 and N2 both have modifiers (`amod`, `acl`, `acl:relcl`, `nmod`, `compound`), and the words of N2's modifiers, in sentence order, differ from N1's |
| `same_governor` | the phrase and the *if*-clause are dependents of the same word: both modify the main clause |

The first four are the two properties above: a sentence **matches** when one candidate meets
them, and is a **strict match** when that candidate also meets `same_governor`, the provision's
own shape (*case* and *determines* both depend on *detained*). A match that is not strict has its
*if*-clause attached elsewhere, either by a parse error or because it conditions another clause. The phrase's head is the lowest word
dominating both the phrase's first word and N1, so *with respect to an employee* parsed as a fixed
expression (the phrase's words hanging off *employee*) is handled like *in the case of an alien*.
8 U.S.C. § 1225(b)(2)(A) itself is the regression case (`tests/test_1225b.py`).

## Running

From the repository root, with the shared pipeline (`negconj/`):

```sh
.venv/bin/pytest barbosa/tests                              # queries, dependency query, regression
source scripts/modal_env.sh
.venv/bin/python scripts/launch.py --run 1225b --study 1225b --release 119-121 \
    --target-chars 500000 --gpu-budget-seconds 7200        # extract, plan, parse, classify, report
scripts/watch_run.sh 1225b
scripts/pull_results.sh 1225b barbosa/results               # checksums verified
.venv/bin/python -m barbosa.build_dashboard --results barbosa/results --out site/1225b
.venv/bin/python scripts/run_local.py --study 1225b --titles 29 --root data/local_1225b  # CPU
```

`barbosa/results/` (not committed) holds `parses.parquet` (CoNLL-U per sentence),
`sentences_classified.parquet` (every parsed sentence, the queries it matches, its best
candidate's conditions), `candidates.parquet` (every candidate), `matches.csv`/`.parquet`,
`summary.md`, `failures.parquet`, the manifest and checksums. `RUNLOG.md` records the run.

| file | what it is |
|---|---|
| `study.py` | the RA's queries as regexes; the study's classify and report stages |
| `depquery.py` | CoNLL-U reading, the five conditions, candidate and sentence tables |
| `build_dashboard.py`, `dashboard_template.html` | the static dashboard |
| `tests/` | tests; `fixtures/s1225b2.json` is 1225(b)(2)(A)–(C) as tokenized and parsed by the pipeline |

## Results (release point 119-121)

See `RUNLOG.md`.

## Limitations

- Recall is bounded by the nine linear queries: *in the case of any alien*, *the alien*, *where an
  alien* … are never parsed.
- Each condition rests on one best parse; attachment of the phrase and of the *if*-clause is the
  weakest point on long condensed-chapeau sentences, so `same_governor` near misses are worth a look.
- Repetition is by head lemma (*an alien … an alien*), not by meaning (*an individual … a person*).
- The match is structural. Whether the two noun phrases pick out the same individuals is the
  interpretive question the dashboard is for.
