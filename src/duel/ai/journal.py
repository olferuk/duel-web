"""Experiment journal: JSONL entries + HTML report generation (Russian)."""

import html
import json
import time
from pathlib import Path

LAB = Path(__file__).resolve().parents[3] / "analysis" / "lab"
JOURNAL = LAB / "journal.jsonl"
REPORT = LAB / "report.html"


def log_entry(kind: str, **fields) -> None:
    LAB.mkdir(parents=True, exist_ok=True)
    entry = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "kind": kind, **fields}
    with JOURNAL.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    render_report()


def read_journal() -> list[dict]:
    if not JOURNAL.exists():
        return []
    return [json.loads(line) for line in JOURNAL.read_text(encoding="utf-8").splitlines() if line]


_CSS = """
body { font-family: Georgia, serif; background: #241c12; color: #e8dcc0;
       max-width: 1000px; margin: 0 auto; padding: 24px; }
h1 { color: #d4a017; border-bottom: 2px solid #6a5230; padding-bottom: 8px; }
h2 { color: #c9a84c; margin-top: 28px; }
.entry { background: rgba(232,220,192,0.07); border-left: 3px solid #6a5230;
         border-radius: 6px; padding: 10px 14px; margin: 10px 0; }
.entry.win { border-left-color: #7ec97e; }
.entry.fail { border-left-color: #c97e7e; }
.ts { color: #8a7a5c; font-size: 12px; }
table { border-collapse: collapse; margin: 12px 0; width: 100%; }
th, td { border: 1px solid #4a3820; padding: 6px 10px; text-align: left; font-size: 14px; }
th { background: #3a2c18; color: #d4a017; }
tr:nth-child(even) { background: rgba(232,220,192,0.04); }
.elo { font-weight: bold; color: #d4a017; }
code { background: rgba(0,0,0,0.35); padding: 1px 5px; border-radius: 4px; font-size: 13px; }
.big { font-size: 17px; }
"""


def render_report() -> None:
    entries = read_journal()
    parts = [
        "<!doctype html><html lang='ru'><head><meta charset='utf-8'>",
        "<title>Лаборатория: Дуэль за Средиземье</title>",
        f"<style>{_CSS}</style></head><body>",
        "<h1>🧪 Лаборатория ботов — Дуэль за Средиземье</h1>",
        "<p>Хроника ночных экспериментов: гипотезы, матчи, ELO, обучение.</p>",
    ]
    # latest ELO table first, if any
    last_elo = next((e for e in reversed(entries) if e["kind"] == "elo"), None)
    if last_elo:
        parts.append("<h2>🏆 Текущая таблица ELO</h2>")
        parts.append(_elo_table(last_elo))
        chart = _elo_chart(entries)
        if chart:
            parts.append("<h2>📈 Динамика ELO</h2>")
            parts.append(chart)
    parts.append("<h2>📜 Хроника</h2>")
    for e in reversed(entries):
        parts.append(_render_entry(e))
    parts.append("</body></html>")
    REPORT.write_text("\n".join(parts), encoding="utf-8")


_CHART_COLORS = [
    "#d4a017",
    "#7ec97e",
    "#7eaec9",
    "#c97e7e",
    "#b07ec9",
    "#c9b27e",
    "#7ec9b2",
    "#c97eae",
    "#9ac97e",
    "#8a94c9",
]


def _elo_chart(entries: list[dict]) -> str:
    """Inline SVG line chart of ratings across published ELO snapshots."""
    snaps = [e["ratings"] for e in entries if e["kind"] == "elo"]
    if len(snaps) < 2:
        return ""
    bots = sorted({b for s in snaps for b in s}, key=lambda b: -snaps[-1].get(b, 0))[:10]
    w, h, pad = 940, 300, 40
    all_vals = [v for s in snaps for v in s.values()]
    lo, hi = min(all_vals) - 30, max(all_vals) + 30
    n = len(snaps)

    def sx(i: int) -> float:
        return pad + i * (w - 2 * pad) / max(n - 1, 1)

    def sy(v: float) -> float:
        return h - pad - (v - lo) * (h - 2 * pad) / (hi - lo)

    lines = []
    legends = []
    for bi, bot in enumerate(bots):
        color = _CHART_COLORS[bi % len(_CHART_COLORS)]
        pts = [f"{sx(i):.0f},{sy(s[bot]):.0f}" for i, s in enumerate(snaps) if bot in s]
        if len(pts) < 2:
            continue
        lines.append(
            f'<polyline points="{" ".join(pts)}" fill="none" stroke="{color}" stroke-width="2"/>'
        )
        legends.append(
            f'<span style="color:{color}">■ {html.escape(bot)} ({snaps[-1].get(bot, 0):.0f})</span>'
        )
    axis = (
        f'<line x1="{pad}" y1="{h - pad}" x2="{w - pad}" y2="{h - pad}" stroke="#6a5230"/>'
        f'<line x1="{pad}" y1="{pad}" x2="{pad}" y2="{h - pad}" stroke="#6a5230"/>'
        f'<text x="{pad - 5}" y="{sy(lo + 30) + 4}" text-anchor="end" font-size="11" '
        f'fill="#8a7a5c">{lo + 30:.0f}</text>'
        f'<text x="{pad - 5}" y="{sy(hi - 30) + 4}" text-anchor="end" font-size="11" '
        f'fill="#8a7a5c">{hi - 30:.0f}</text>'
    )
    return (
        f'<svg width="{w}" height="{h}" style="background:rgba(232,220,192,0.05);'
        f'border-radius:8px">{axis}{"".join(lines)}</svg>'
        f'<div style="font-size:12px;margin-top:6px">{" &nbsp; ".join(legends)}</div>'
    )


def _elo_table(e: dict) -> str:
    rows = sorted(e["ratings"].items(), key=lambda kv: -kv[1])
    games = e.get("games", {})
    body = "".join(
        f"<tr><td>{i + 1}</td><td><code>{html.escape(n)}</code></td>"
        f"<td class='elo'>{r:.0f}</td><td>{games.get(n, '—')}</td></tr>"
        for i, (n, r) in enumerate(rows)
    )
    return "<table><tr><th>#</th><th>Бот</th><th>ELO</th><th>Партий</th></tr>" + body + "</table>"


def _render_entry(e: dict) -> str:
    ts = f"<span class='ts'>{e['ts']}</span>"
    kind = e["kind"]
    if kind == "note":
        cls = {"ok": "win", "fail": "fail"}.get(e.get("mood", ""), "")
        title = html.escape(e.get("title", ""))
        text = e.get("text", "")
        return (
            f"<div class='entry {cls}'>{ts}<br><b>{title}</b>"
            + (f"<br>{text}" if text else "")
            + "</div>"
        )
    if kind == "match":
        return (
            f"<div class='entry'>{ts}<br>⚔️ <code>{html.escape(e['a'])}</code> vs "
            f"<code>{html.escape(e['b'])}</code>: {e['wins_a']}–{e['wins_b']}"
            + (f" (ничьи: {e['draws']})" if e.get("draws") else "")
            + f" из {e['n']} партий · {e.get('secs', '?')} с</div>"
        )
    if kind == "elo":
        return f"<div class='entry'>{ts}<br>📊 Обновление рейтингов:{_elo_table(e)}</div>"
    if kind == "train":
        return (
            f"<div class='entry'>{ts}<br>🧠 Обучение <code>{html.escape(e['model'])}</code>: "
            f"{e.get('samples', '?')} примеров, loss {e.get('loss', '?')}, "
            f"{e.get('epochs', '?')} эпох, {e.get('secs', '?')} с</div>"
        )
    return f"<div class='entry'>{ts}<br>{html.escape(json.dumps(e, ensure_ascii=False))}</div>"
