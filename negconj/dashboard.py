"""Static dashboards: what every study's build script shares.

A page is a template with three placeholders: ``/*__DASHBOARD_CSS__*/`` and
``/*__DASHBOARD_JS__*/`` take the shared assets (negconj/assets), ``/*__DATASETS__*/[]`` the
page's dataset names. Data goes in plain script files that call a function of the page
(``write_call``), so a site works from GitHub Pages and opened from disk.
"""

from __future__ import annotations

import json
from pathlib import Path

ASSETS = Path(__file__).resolve().parent / "assets"
PLACEHOLDERS = ("/*__DASHBOARD_CSS__*/", "/*__DASHBOARD_JS__*/", "/*__DATASETS__*/[]")


def js(obj) -> str:
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False).replace("</", "<\\/")


def write_call(path: Path, fn: str, *args) -> None:
    """Write ``fn(arg, …);`` to path, each argument as JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{fn}({','.join(js(a) for a in args)});\n", encoding="utf-8")


def manifest_meta(results: Path) -> dict:
    """Run facts shown on a page, from results/RUN_MANIFEST.json."""
    mp = Path(results) / "RUN_MANIFEST.json"
    if not mp.exists():
        return {}
    m = json.loads(mp.read_text())
    out = {k: m.get(k) for k in ("release_point", "git_commit", "model_package", "gpu_type")}
    out["partial"] = m.get("PARTIAL")
    return out


def render_page(template: Path, out: Path, datasets: list) -> None:
    html = Path(template).read_text(encoding="utf-8")
    values = ((ASSETS / "dashboard.css").read_text(encoding="utf-8").rstrip("\n"),
              (ASSETS / "dashboard.js").read_text(encoding="utf-8").rstrip("\n"), js(datasets))
    for ph, v in zip(PLACEHOLDERS, values):
        if html.count(ph) != 1:
            raise ValueError(f"{template}: expected one {ph}")
        html = html.replace(ph, v)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
