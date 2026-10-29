"""Small helpers shared by every stage and study: atomic writes, JSONL, checksums, ordering."""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

import pandas as pd


def title_sort_key(title: str) -> tuple[int, str]:
    """Numeric title order: 1, 2, …, 5, 5a, …, 54."""
    m = re.match(r"(\d+)(.*)", title)
    return (int(m.group(1)), m.group(2)) if m else (10**6, title)


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    with open(tmp, "wb") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def atomic_write_parquet(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    df.to_parquet(tmp, index=False)
    os.replace(tmp, path)


def atomic_write_csv(df: pd.DataFrame, path: Path) -> None:
    tmp = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    df.to_csv(tmp, index=False)
    os.replace(tmp, path)


def append_jsonl(path: Path, records: list[dict]) -> None:
    prev = path.read_bytes() if path.exists() else b""
    atomic_write_bytes(path, prev + "".join(json.dumps(r) + "\n" for r in records).encode())


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text().splitlines() if l] if path.exists() else []


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_checksums(res: Path) -> Path:
    lines = []
    for p in sorted(res.rglob("*")):
        if p.is_file() and p.name != "CHECKSUMS.sha256" and not p.name.startswith("."):
            lines.append(f"{sha256_file(p)}  {p.relative_to(res).as_posix()}")
    out = res / "CHECKSUMS.sha256"
    out.write_text("\n".join(lines) + "\n")
    return out


def md_table(df: pd.DataFrame) -> str:
    cols = [str(c) for c in df.columns]
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for row in df.itertuples(index=False):
        lines.append("| " + " | ".join(str(v) for v in row) + " |")
    return "\n".join(lines)
