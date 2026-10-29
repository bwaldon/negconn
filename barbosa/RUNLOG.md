# RUNLOG: 1225b

Decisions, counts and anomalies for the study of sentences shaped like 8 U.S.C. § 1225(b)(2)(A)
(see `README.md`). The shared-pipeline refactor it needed is logged in the top-level `RUNLOG.md`.

## Setup (2026-10-29)
- Candidates: the RA's nine Westlaw queries (screenshot of 2026-10-28) transcribed as regexes in
  `study.QUERIES`; a sentence is parsed when any query matches it.
- Local sizing on the full run's units (release 119-121): 2,714 units pass the unit-level regex
  (9.12 M chars); segmentation gives 1,992 matching sentences, 496 k tokens (median 132, 5 over
  4,000). ELECTRA depparse on CPU: ≈ 180 tok/s, ≈ 5.6 GiB for a 2,092-token sentence.
- Parser: Stanza 1.15.0, `electra-dep` (pos `combined_electra-large`, lemma `combined_charlm`,
  depparse `combined_electra-large`, transformer `google/electra-large-discriminator`), Stanza's
  default_accurate for these processors. One CoNLL-U parse per sentence.
- Local end-to-end check (Title 29, CPU, `scripts/run_local.py --study 1225b`): 125 units,
  92 matches, 92 parsed, all report checks OK.
- User decision: run on Modal.

## Modal runs (run `1225b`, `/data/1225b`)
| call | commit | what happened |
|---|---|---|
| fc-01M64EP6QW3P038GHN5PB7WR0B | 88eb5d9 | failed in `download`: no `--release`, OLRC lists 119-136, its all-titles zip 404s |
| fc-01M64EX0GFMWANM9R7SMZM205Z | 88eb5d9 | `--release 119-121`; extracted and planned, then ~20 min with all 10 shard calls queued and no L4; cancelled, app stopped |
| fc-01M64GC6ETDF08SGM9XRSS3HXK | 298b127 | GPU list L4 → A10G → L40S: 10 containers within 33 s; all 55 shards; first classification |
| fc-01M64HDPN1RZBH0YWD916QNM93 | 4126d1e | merge/classify/report only: match tiers, modifiers compared in order |
| fc-01M64JHB0Q5ENQ2TCN6E1MSDY9 | c6e163f | merge/classify/report only: N2 may not be introduced by a query phrase (**final**) |

- Extraction: 56 titles, 266,232 units (same as the negconn runs); prefilter 2,714 units,
  1,906 sections, 9,121,822 chars; 55 shards (target 500,000 chars).
- Shards ran on NVIDIA A10/A10G (52) and L40S (3); no L4 was free. Reported GPU time 4,475 s.
- Merge: 21,205 raw splits, 1,628 re-merged, 19,577 sentences; **1,992 matches, 1,987 parsed,
  5 not parsed** (over 4,000 tokens: the same sentences the negconn runs could not parse,
  in 42 U.S.C. 1396a, 34 U.S.C. 11133, 42 U.S.C. 671, 1395l and 654). 0 duplicate rows.
  4,242 (phrase, if) candidates. Report checks all OK; 121 checksums verified after
  `scripts/pull_results.sh 1225b barbosa/results`.
- The app was stopped after each run (user request); 0 containers left.

## The dependency query, as reviewed on the results
First version (run 3): all five conditions required. 59 matches. Review of matches and near
misses led to three changes:
1. **Tiers.** The stated properties do not ask that the phrase and the if-clause modify the same
   head; that condition (`same_governor`) was mine. A match is now the four conditions encoding the
   two properties; `same_governor` makes it a strict match. Most `same_governor` failures were
   long chapeaus where the two attach to different verbs, by parse error or by structure.
2. **Modifier text in sentence order.** 12 U.S.C. § 5531(f) counted as "different modifiers" only
   because *of credit* and *secured by …* were one modifier under N2 and two under N1.
3. **N2 not itself framed.** 30 matches (13 strict) existed only because the parser stretched the
   if-clause over a parallel provision, so N2 was the N1 of the next *in the case of* (5 U.S.C.
   § 5542(h)(2), 20 U.S.C. § 1070a(b)(1), 8 U.S.C. § 1231(a)(4)(B), …). Excluded.

## Results (c6e163f; superseded below)
132 matches without `same_governor`, 45 with it ("strict"), 87 near misses.

## Same head required again (user decision)
The user is not interested in sentences where the phrase and the if-clause modify different heads,
so `same_governor` is a condition of a match again and the strict tier is gone. Order of the
conditions: frame_np, if_outside, same_governor, repeated_np, different_mods. Near misses: best
candidate meets `same_governor` and four of the five conditions (in practice: a repeated noun
whose modifiers are the same or missing). The two later refinements (modifiers compared in
order, N2 not itself framed) stay.

## Results (final)
| sentences with a candidate where … | sentences |
|---|---|
| matches a linear query (parsed) | 1,987 |
| + the phrase introduces an indefinite noun phrase (N1) | 1,987 |
| + an if-clause after it, outside the phrase | 1,854 |
| + the phrase and the if-clause modify the same head | 804 |
| + the if-clause has an indefinite NP with N1's head noun (N2) | 68 |
| + N1 and N2 both modified, differently = **match** | **45** |

- The 45 are exactly the earlier strict matches. Near misses: 23, all with the same or no
  modifiers on one side.
- By linear query (sentences it finds: parsed / matches): *in the case of* 1,154 / 36; *with
  respect to* 793 / 10; *respecting* 11 / 1; *in the event that* 11 / 1; the other five 0.
  (A sentence can match more than one query.)
- **8 U.S.C. § 1225(b)(2)(A) matches** (regression test on the results). Matches in Title 8 also
  include § 1229b(a) (cancellation of removal: *an alien who is inadmissible or deportable* …
  *an alien lawfully admitted for permanent residence*) and § 1151(f)(2), (3). 18 U.S.C.
  § 3553(f) (Pulsifer) matches too.

## Dashboard
- `python -m barbosa.build_dashboard --results barbosa/results --out site/1225b`: 1,987 rows,
  `data/index.js` 2.9 MB, `data/parses-{title}.js` 26.6 MB in total. Published as
  <https://bwaldon.github.io/negconn/1225b/> (`1225b/` on `gh-pages`, next to the negconn site).
