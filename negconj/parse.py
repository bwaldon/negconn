"""Stanza parsing of pretokenized sentences: constituency trees or UD dependencies (§5.4.6).

One best parse per sentence. Sentences are sorted by length and parsed in
sub-batches; on GPU out-of-memory (or any other error) the sub-batch is
retried one sentence at a time, then each failing sentence on a CPU pipeline.
A sentence that still fails is returned as a failure, never dropped.

A parser's output columns depend on its kind:
  constituency  tree (bracketed string), xpos (one tag per token)
  dependency    conllu (the sentence in CoNLL-U: one line per word, a range
                line before a multi-word token's words; no comment lines)
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from nltk.tree import Tree

# Name -> kind and processor -> Stanza package. Only the listed processors are loaded.
# "electra" is Stanza's default_accurate pairing for pos + constituency, "charlm" Stanza's
# default; "electra-dep" is default_accurate for pos, lemma and depparse. The tokenizer is
# unused (input is pretokenized) and kept equal to segment.py's.
PARSER_CONFIGS = {
    "electra": {"kind": "constituency", "processors": {
        "tokenize": "combined_nocharlm", "mwt": "combined",
        "pos": "combined_electra-large", "constituency": "ptb3-revised_electra-large"}},
    "charlm": {"kind": "constituency", "processors": {
        "tokenize": "combined_nocharlm", "mwt": "combined",
        "pos": "combined_charlm", "constituency": "ptb3-revised_charlm"}},
    "electra-dep": {"kind": "dependency", "processors": {
        "tokenize": "combined_nocharlm", "mwt": "combined", "pos": "combined_electra-large",
        "lemma": "combined_charlm", "depparse": "combined_electra-large"}},
}
DEFAULT_PARSER = "electra"
OUTPUT_COLUMNS = {"constituency": ("tree", "xpos"), "dependency": ("conllu",)}


def build_pipeline(use_gpu: bool, config: str = DEFAULT_PARSER):
    import stanza
    # package=None: without it Stanza also loads (and runs) every other processor of its
    # default package (lemma, depparse, ner, sentiment, ...).
    return stanza.Pipeline("en", processors=PARSER_CONFIGS[config]["processors"], package=None,
                           tokenize_pretokenized=True, use_gpu=use_gpu, logging_level="WARN",
                           download_method=None)


def _transformer(proc) -> str | None:
    trainer = getattr(proc, "_trainer", None)
    for obj in (getattr(proc, "_model", None), trainer, getattr(trainer, "model", None)):
        args = getattr(obj, "args", None)
        if isinstance(args, dict) and args.get("bert_model"):
            return args["bert_model"]
    return None


def model_package(nlp, config: str = DEFAULT_PARSER) -> str:
    """e.g. 'tokenize=combined_nocharlm;mwt=combined;pos=combined_electra-large;
    constituency=ptb3-revised_electra-large;transformer=google/electra-large-discriminator'.
    The transformer is the one the last processor (the parser) uses."""
    parts = []
    names = list(PARSER_CONFIGS[config]["processors"])
    for name in names:
        proc = nlp.processors.get(name)
        if proc is not None:
            parts.append(f"{name}={Path(proc.config['model_path']).stem}")
    bert = _transformer(nlp.processors[names[-1]])
    if bert:
        parts.append(f"transformer={bert}")
    return ";".join(parts)


def _constituency(s) -> tuple[str, list[str]]:
    tree = "{}".format(s.constituency)
    n_leaves = len(Tree.fromstring(tree).leaves())
    if n_leaves != len(s.words):
        raise ValueError(f"tree has {n_leaves} leaves for {len(s.words)} words")
    return tree, [w.xpos for w in s.words]


def _field(v) -> str:
    return "_" if v is None or v == "" else str(v)


def _dependency(s) -> tuple[str]:
    lines = []
    for tok in s.tokens:
        if len(tok.words) > 1:
            lines.append(f"{tok.id[0]}-{tok.id[-1]}\t{tok.text}" + "\t_" * 8)
        for w in tok.words:
            lines.append("\t".join([str(w.id), w.text, _field(w.lemma), _field(w.upos),
                                    _field(w.xpos), _field(w.feats), str(w.head),
                                    _field(w.deprel), "_", "_"]))
    if sum(1 for w in s.words if w.head == 0) != 1:
        raise ValueError("dependency parse without exactly one root")
    return ("\n".join(lines),)


_OUTPUT = {"constituency": _constituency, "dependency": _dependency}


def _is_oom(e: BaseException) -> bool:
    return "out of memory" in str(e).lower() or type(e).__name__ == "OutOfMemoryError"


def _free_gpu() -> None:
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass


class Parser:
    def __init__(self, use_gpu: bool, sub_batch_tokens: int = 6000, config: str = DEFAULT_PARSER):
        import stanza
        self.use_gpu = use_gpu
        self.config = config
        self.kind = PARSER_CONFIGS[config]["kind"]
        self.columns = OUTPUT_COLUMNS[self.kind]
        self.nlp = build_pipeline(use_gpu, config)
        self._cpu = None if use_gpu else self.nlp
        self.sub_batch_tokens = sub_batch_tokens
        self.stanza_version = stanza.__version__
        self.model_package = model_package(self.nlp, config)
        self.events: dict[str, int] = {"oom_batches": 0, "single_retries": 0, "cpu_fallbacks": 0}

    @property
    def cpu(self):
        if self._cpu is None:
            self._cpu = build_pipeline(False, self.config)
        return self._cpu

    def _run(self, nlp, token_lists: Sequence[Sequence[str]]) -> list[tuple]:
        doc = nlp([list(t) for t in token_lists])
        out = []
        for toks, s in zip(token_lists, doc.sentences):
            if len(s.tokens) != len(toks):
                raise ValueError(f"{len(s.tokens)} tokens out for {len(toks)} in")
            out.append(_OUTPUT[self.kind](s))
        if len(out) != len(token_lists):
            raise ValueError("sentence count mismatch")
        return out

    def _one(self, toks) -> tuple[tuple | None, str | None]:
        self.events["single_retries"] += 1
        err = None
        if self.use_gpu:
            try:
                return self._run(self.nlp, [toks])[0], None
            except Exception as e:  # noqa: BLE001
                err = f"gpu: {type(e).__name__}: {e}"
                _free_gpu()
            self.events["cpu_fallbacks"] += 1
        try:
            return self._run(self.cpu, [toks])[0], None
        except Exception as e:  # noqa: BLE001
            return None, f"{err + '; ' if err else ''}cpu: {type(e).__name__}: {e}"

    def parse(self, token_lists: Sequence[Sequence[str]]):
        """Parse sentences. Returns (results, errors), both indexed like the input:
        results[i] = a tuple of values for self.columns, or None; errors[i] = message or None."""
        n = len(token_lists)
        results: list = [None] * n
        errors: list = [None] * n
        order = sorted(range(n), key=lambda i: len(token_lists[i]))
        batch: list[int] = []
        size = 0

        def flush(idx: list[int]) -> None:
            if not idx:
                return
            try:
                for i, r in zip(idx, self._run(self.nlp, [token_lists[i] for i in idx])):
                    results[i] = r
                return
            except Exception as e:  # noqa: BLE001
                if _is_oom(e):
                    self.events["oom_batches"] += 1
                    _free_gpu()
            for i in idx:
                results[i], errors[i] = self._one(token_lists[i])

        for i in order:
            L = len(token_lists[i])
            if batch and size + L > self.sub_batch_tokens:
                flush(batch)
                batch, size = [], 0
            batch.append(i)
            size += L
        flush(batch)
        return results, errors

