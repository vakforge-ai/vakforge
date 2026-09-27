"""One self-contained HTML page from `inspect.json` and, optionally, `recommend.json`.

The JSON is for scripts and the agent skill. This page is for the people who decide: who
funds a fine-tune, who checks what personal data a folder holds. Its styles and logo are
embedded and it fetches nothing, so it opens offline, travels as one file, and prints to
PDF from any browser.
"""

from __future__ import annotations

import base64
import math
import re
from datetime import date
from html import escape
from importlib.resources import files
from pathlib import PurePosixPath
from typing import Any

from vakforge import GLOSSARY_URL, __version__
from vakforge.inspect.report import is_sampled
from vakforge.recommend.rules import RECIPES, VERDICT_LABELS, fmt_kinds, fmt_number

VERDICT_TONE = {"candidate": "good", "baseline_first": "warn", "blocked": "bad"}
SUPPORT_TONE = {"native": "good", "understand_only": "warn", "cascade": "warn"}
_ICON = {
    "good": '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
    "warn": '<path d="M12 6.5v7M12 17.5v.01"/>',
    "bad": '<path d="M7 7l10 10M17 7 7 17"/>',
}
_LOCALE_TAG = re.compile(r"[a-z]{2,3}(-([A-Z][a-z]{3}|[A-Z]{2}|\d{3}))+")
# A count inside a sentence, but not the digits of an arXiv id such as 2305.11206.
_LONG_NUMBER = re.compile(r"(?<![\d.])\d{5,}(?![\d.])")


def _n(value: float) -> str:
    """A count grouped in threes by thin spaces, the ISO 80000 style that reads the same in
    every locale. Commas would be wrong for en-IN, which writes 2002646 as 20,02,646."""
    if float(value).is_integer():
        return f"{int(value):,}".replace(",", "\u202f")
    return fmt_number(value)


def _cap(text: str) -> str:
    """Text as a sentence: first letter up. Not when it opens with a name that is spelled
    the way it is, a recipe (`lfm25-audio`, `cascade`) or a locale tag (`en-US`)."""
    first = text.split(" ", 1)[0].rstrip(":,;")
    if not text[:1].islower() or first in RECIPES or _LOCALE_TAG.fullmatch(first):
        return text
    return text[0].upper() + text[1:]


def _t(text: str) -> str:
    """Prose from a report, ready for the page: a sentence, counts grouped, escaped."""
    return escape(_LONG_NUMBER.sub(lambda m: _n(int(m.group())), _cap(text)))


def _duration(seconds: float) -> str:
    if seconds < 90:
        return f"{seconds:.3g} s"
    if seconds < 5400:
        return f"{seconds / 60:.1f} min"
    return f"{seconds / 3600:.1f} h"


def _badge(text: str, tone: str) -> str:
    return f'<span class="badge {tone}">{_t(text)}</span>'


def _section(title: str, body: str, note: str = "") -> str:
    note = f'<p class="note">{note}</p>' if note else ""
    return f"<section><h2>{escape(title)}</h2>{note}{body}</section>"


def _overview(s: dict[str, Any]) -> str:
    found, read = sum(s["counts"].values()), sum(s["profiled"].values())
    files_sub = f"{_n(read)} read" + (f", {_n(s['unreadable'])} skipped" if s["unreadable"] else "")
    if s["truncated"]:
        files_sub += f", {_n(s['truncated'])} read in part"
    n_audio = s["profiled"]["audio"]

    def within(kind: str) -> str:
        return (
            f"In {fmt_kinds({kind: s['profiled'][kind]})}" if s["profiled"][kind] else "None read"
        )

    stats = [
        ("Files", _n(found), files_sub),
        ("Document words", _n(s["document_words"]), within("document")),
        ("Chat messages", _n(s["chat_messages"]), within("chat")),
        (
            "Audio",
            _duration(s["audio_hours"] * 3600) if n_audio else "None",
            f"In {_n(n_audio)} file{'s' if n_audio != 1 else ''}, "
            f"{_n(s['two_channel_audio_files'])} with two channels"
            if n_audio
            else "None read",
        ),
    ]
    cards = "".join(
        f'<div class="stat"><div class="k">{k}</div><div class="v">{v}</div>'
        f'<div class="s">{sub}</div></div>'
        for k, v, sub in stats
    )
    return _section("At a glance", f'<div class="stats">{cards}</div>')


def _readiness(d: dict[str, Any]) -> str:
    """The goal's data against its minimum and target, on a log scale.

    A linear bar drew 16 turns and 2,002,646 turns against a 600-turn target as the same
    full bar or an invisible sliver; on a log scale both land where they belong. A report
    from 0.2.0 has no `floor`, and then only the target is marked.
    """
    have, floor, target = d["have"], d.get("floor") or 0, d["need"]
    if not floor and target is None:
        return ""  # volume is not the question for this goal (knowledge)
    top = max(have, target or floor) * 1.6

    def at(x: float) -> float:
        return 100 * math.log10(x + 1) / math.log10(top + 1)

    def mark(value: float, text: str, side: str) -> str:
        pos = at(value)
        edge = " l" if pos < 12 else " r" if pos > 88 else ""
        return f'<i class="mark {side}{edge}" style="left:{pos:.1f}%"><span>{text}</span></i>'

    tone = "bad" if have < floor else "warn" if target is not None and have < target else "good"
    marks = mark(floor, f"Minimum {_n(floor)}", "lo") if floor else ""
    if target is not None:
        marks += mark(target, f"Target ~{_n(target)}", "hi")
    return (
        f'<div class="row"><span class="label">Data</span><div><div class="ready {tone}">'
        f'<span class="fill" style="width:{max(at(have), 1.5):.1f}%"></span>{marks}</div>'
        f'<p class="have"><span><b>{_n(have)}</b> {escape(d["unit"])}, counted from '
        f'{_t(d["have_from"])}</span><span class="scale">Log scale</span></p></div></div>'
    )


def _goal(d: dict[str, Any]) -> str:
    rows = [f"<p>{_t(d['reason'])}</p>", _readiness(d)]
    for label, tone, items in (
        ("Not counted", "warn", d["uncounted"]),
        ("Blocked on", "bad", d["blockers"]),
    ):
        rows += [
            f'<div class="row {tone}"><span class="label">{label}</span><div>{_t(item)}</div></div>'
            for item in items
        ]
    support = d.get("recipe_support")
    level = _badge(support.replace("_", " "), SUPPORT_TONE.get(support, "bad")) if support else ""
    rows.append(
        f'<div class="row"><span class="label">Recipe</span><div><code>'
        f"{escape(d['recipe'] or 'none')}</code> {level}"
        f"<small>{_t(d['recipe_reason'])}</small></div></div>"
    )
    if d.get("recipe_method"):
        # The recipes are researched, not built: the method is their plan, not a result.
        rows.append(
            f'<div class="row"><span class="label">Method</span><div>'
            f"{_badge('planned', 'muted')} {_t(d['recipe_method'])}</div></div>"
        )
    rows.append(
        f'<div class="row"><span class="label">Evidence</span><div>'
        f"{_badge(d['confidence'], 'muted')} {_t(d['evidence'])}</div></div>"
    )
    tone = VERDICT_TONE[d["eligibility"]]
    return (
        f'<article class="card goal {tone}"><header><h3>{_t(d["goal"])}</h3>'
        f"{_badge(VERDICT_LABELS[d['eligibility']], tone)}</header>{''.join(rows)}</article>"
    )


def _source_detail(source: str, s: dict[str, Any]) -> str:
    """How much of `source` the folder holds, for the routing diagram."""
    detail = {
        "documents": f"{_n(s['document_words'])} words",
        "tables": fmt_kinds({"table": s["profiled"]["table"]}),
        "chats": f"{_n(s['chat_messages'])} messages",
        "audio": _duration(s["audio_hours"] * 3600),
        "two-channel audio": f"{_n(s['two_channel_audio_files'])} files",
        "languages": ", ".join(list(s["languages"])[:3]),
        "labelled texts": fmt_kinds({"table": s.get("labelled_text_tables", 0)}),
    }.get(source, "")
    return escape(detail)


def _routing(routes: list[dict[str, Any]], s: dict[str, Any]) -> str:
    rows = "".join(
        f'<div class="route"><div class="node src"><b>{_t(r["source"])}</b>'
        f"<small>{_source_detail(r['source'], s)}</small></div>"
        '<span class="arrow" aria-hidden="true"></span>'
        f'<div class="node dst"><b>{_t(r["route"])}</b><small>{_t(r["why"])}</small></div></div>'
        for r in routes
    )
    return f'<h3 class="sub">What each source needs</h3><div class="flow">{rows}</div>'


def _recommendation(rec: dict[str, Any], s: dict[str, Any]) -> str:
    tone = VERDICT_TONE[rec["fine_tune"]]
    primary = rec["primary_problem"] or "none yet: no usable evidence"
    goals = ", ".join(_t(g) for g in rec["goals"]) or "-"
    head = (
        f'<div class="card verdict {tone}"><span class="vi"><svg viewBox="0 0 24 24" '
        f'aria-hidden="true">{_ICON[tone]}</svg></span><div><div class="vk">Fine-tune?</div>'
        f'<div class="vv">{_t(VERDICT_LABELS[rec["fine_tune"]])}</div>'
        f"<p>{_t(rec['fine_tune_reason'])}</p><dl>"
        f"<dt>Primary problem</dt><dd>{_t(primary)}</dd>"
        f"<dt>Goals</dt><dd>{goals}</dd></dl></div></div>"
    )
    parts = [head]
    if rec["routes"]:
        parts.append(_routing(rec["routes"], s))
    if rec["goal_decisions"]:
        goal_cards = "".join(_goal(d) for d in rec["goal_decisions"])
        parts.append(f'<h3 class="sub">Each goal</h3><div class="goals">{goal_cards}</div>')
    if rec["consent"]:
        items = "".join(f"<li>{_t(c)}</li>" for c in rec["consent"])
        parts.append(
            '<h3 class="sub">Consent and privacy <span class="aside">Not legal advice</span></h3>'
            f'<ul class="card notes">{items}</ul>'
        )
    if rec["next_steps"]:
        items = "".join(f"<li>{_t(step)}</li>" for step in rec["next_steps"])
        parts.append(f'<h3 class="sub">Next steps</h3><ol class="card steps">{items}</ol>')
    return _section("Recommendation", "".join(parts))


def _languages(s: dict[str, Any]) -> str:
    langs = s["languages"]
    if not langs:
        return ""
    total = sum(langs.values())
    rows = "".join(
        f'<div class="bar"><span class="bk">{escape(k)}</span><span class="track">'
        f'<i style="width:{100 * v / total:.1f}%"></i></span>'
        f'<span class="bv">{100 * v / total:.0f}%</span></div>'
        for k, v in langs.items()
    )
    return _section(
        "Languages",
        f'<div class="card bars">{rows}</div>',
        "Share of the paragraphs and messages checked: the first 200 of each file.",
    )


def _personal_data(report: dict[str, Any]) -> str:
    pii = report["summary"]["pii"]
    note = (
        "Found by the locale pack's patterns, and by column header for names, addresses "
        "and birth dates. Names written inside free text are not detected yet."
    )
    if is_sampled(report):
        note += " Large files were checked from their start, so these counts are not totals."
    if not pii:
        return _section(
            "Personal data",
            '<p class="card">None found by these checks, which does not show that the files '
            "hold no personal data.</p>",
            note,
        )
    chips = "".join(
        f'<span class="chip pii">{escape(k)} <b>{_n(v)}</b></span>' for k, v in pii.items()
    )
    rows = []
    for f in report["files"]:
        facts = f.get("facts", {})
        columns = [facts.get("pii_columns", {})]
        columns += [t.get("pii_columns", {}) for t in facts.get("tables", {}).values()]
        for by_column in columns:
            for column, counts in by_column.items():
                found = ", ".join(f"{escape(k)} {_n(v)}" for k, v in counts.items())
                rows.append(
                    f'<tr><td class="path">{escape(f["path"])}</td>'
                    f"<td><code>{escape(column)}</code></td><td>{found}</td></tr>"
                )
    table = (
        '<h3 class="sub">Columns holding it</h3><div class="table"><table>'
        f"<tr><th>File</th><th>Column</th><th>Found</th></tr>{''.join(rows)}</table></div>"
        if rows
        else ""
    )
    return _section("Personal data", f'<div class="chips">{chips}</div>{table}', note)


def _tools(s: dict[str, Any]) -> str:
    if not s["tool_candidates"]:
        return ""
    chips = "".join(f'<span class="chip">{escape(t)}</span>' for t in s["tool_candidates"])
    return _section(
        "Tool candidates",
        f'<div class="chips">{chips}</div>',
        "Lookups the assistant could call, made from a table and one of its ID columns. "
        "Tools answer questions about records without training anything.",
    )


def _contents(f: dict[str, Any]) -> str:
    """What one file holds, in words. Never speaker names: in a chat export they are
    people, and this page is made to be passed around."""
    facts = f["facts"]
    kind = f["kind"]
    if kind == "document":
        out = f"{_n(facts.get('words', 0))} words"
        if "faq_pairs" in facts:
            out += f", {_n(facts['faq_pairs'])} question and answer pairs"
        return out
    if kind == "table":
        tables = [
            f"{escape(name)}: "
            + (f"{_n(t['rows'])} rows" if t.get("rows") is not None else "schema only")
            + f", {len(t.get('columns', []))} columns"
            for name, t in facts.get("tables", {}).items()
        ]
        more = f"; {len(tables) - 3} more tables" if len(tables) > 3 else ""
        return "; ".join(tables[:3]) + more
    if kind == "chat":
        out = f"{_n(facts.get('messages', 0))} messages"
        columns = facts.get("pair") or facts.get("message_columns")
        if columns:
            return out + f" from columns {escape(', '.join(columns))}"
        return out + f" from {_n(len(facts.get('speakers', {})))} speakers"
    if kind == "audio":
        channels = facts["channels"]
        out = (
            f"{_duration(facts['duration_s'])}, {facts['sample_rate'] / 1000:g} kHz, "
            f"{_n(channels)} channel{'s' if channels != 1 else ''}"
        )
        return out + (", telephone band" if facts.get("narrowband") else "")
    return ""


def _status(f: dict[str, Any]) -> str:
    if not f["readable"]:
        why = f.get("error") or f.get("note") or "unsupported type"
        return f"{_badge('skipped', 'bad')}<small>{_t(why)}</small>"
    facts = f.get("facts")
    if facts is None:
        return _badge("not read", "muted")
    if facts.get("truncated"):
        why = "Too large to read whole; counts cover the start"
        return f"{_badge('partial', 'warn')}<small>{why}</small>"
    notes = []
    if facts.get("parse_errors"):
        notes.append(f"{_n(len(facts['parse_errors']))} unreadable lines left out")
    if "messages_scanned" in facts:
        notes.append(f"Checked from the first {_n(facts['messages_scanned'])} messages")
    scanned = [t for t in facts.get("tables", {}).values() if "rows_scanned" in t]
    if any(t["rows_scanned"] < t["rows"] for t in scanned):
        notes.append(f"Checked from the first {_n(min(t['rows_scanned'] for t in scanned))} rows")
    return _badge("read", "good") + "".join(f"<small>{n}</small>" for n in notes)


def _files(report: dict[str, Any]) -> str:
    rows = "".join(
        f'<tr><td class="path">{escape(f["path"])}</td><td>{_t(f["kind"])}</td>'
        f"<td>{_contents(f) if 'facts' in f else ''}</td><td>{_status(f)}</td></tr>"
        for f in report["files"]
    )
    if not rows:
        return _section("Files", '<p class="card">The folder is empty.</p>')
    return _section(
        "Files",
        '<div class="table"><table><tr><th>File</th><th>Kind</th><th>Contents</th>'
        f"<th>Status</th></tr>{rows}</table></div>",
    )


def render(report: dict[str, Any], rec: dict[str, Any] | None = None) -> str:
    """The page for one `inspect.json` report, with its recommendation if one is given.

    Every string from the reports is escaped: file and column names come from the user's
    folder, and the page is meant to be opened by other people.

    The folder is shown by its name only. `root` is the path as it was typed, and an
    absolute path can carry a person's or a client's name into a page meant to be shared.
    """
    s = report["summary"]
    folder = PurePosixPath(report["root"]).name or report["root"]
    mark = base64.b64encode(files("vakforge").joinpath("assets/mark.png").read_bytes()).decode()
    pills = "".join(
        f'<span class="pill"><span>{k}</span><b>{escape(v)}</b></span>'
        for k, v in (
            ("Locale", report["locale"]),
            ("Found", fmt_kinds(s["counts"]) or "no files"),
            ("Date", date.today().isoformat()),
            ("vakforge", __version__),
        )
    )
    body = [
        _overview(s),
        _recommendation(rec, s) if rec else "",
        _languages(s),
        _personal_data(report),
        _tools(s),
        _files(report),
    ]
    made_from = "the inspect report and its recommendation" if rec else "the inspect report"
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="generator" content="vakforge {escape(__version__)}">
<title>{escape(folder)} · vakforge report</title>
<script>try{{var t=localStorage.getItem("vakforge-theme");if(t==="light"||t==="dark")\
document.documentElement.dataset.theme=t}}catch(e){{}}</script>
<style>:root{{--mark:url(data:image/png;base64,{mark})}}{CSS}</style>
</head>
<body>
<div class="accent"></div>
<div class="wm" aria-hidden="true"></div>
<main class="wrap">
<header class="top">
<span class="brand"><i aria-hidden="true"></i>vakforge</span>
<button class="icon theme" type="button" aria-label="Switch light or dark theme" \
title="Switch theme"><svg class="moon" viewBox="0 0 24 24" aria-hidden="true"><path \
d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg><svg class="sun" viewBox="0 0 24 24" \
aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 \
4.9l1.4 1.4M17.7 17.7l1.4 1.4M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg></button>
<button class="print" type="button" onclick="print()"><svg viewBox="0 0 24 24" \
aria-hidden="true"><path d="M12 4v11M7 10l5 5 5-5M5 20h14"/></svg>Save as PDF</button>
</header>
<div class="hero">
<p class="eyebrow">Data report</p>
<h1>{escape(folder)}</h1>
<div class="pills">{pills}</div>
</div>
{"".join(body)}
<footer>
<span class="brand"><i aria-hidden="true"></i>vakforge</span>
<p>Made by vakforge {escape(__version__)} from {made_from}, on your own machine: nothing was
uploaded. Totals cover the files vakforge could read. The consent notes are a starting point,
not legal advice.</p>
<p>What the terms mean: <a href="{GLOSSARY_URL}">{GLOSSARY_URL.removeprefix("https://")}</a></p>
</footer>
</main>
<script>document.querySelector(".theme").onclick=function(){{var r=document.documentElement,\
d=r.dataset.theme?r.dataset.theme==="dark":matchMedia("(prefers-color-scheme: dark)").matches;\
r.dataset.theme=d?"light":"dark";try{{localStorage.setItem("vakforge-theme",r.dataset.theme)}}\
catch(e){{}}}}</script>
</body>
</html>
"""


# The site's two palettes. Printing always uses the light one: paper is white.
_LIGHT = """color-scheme:light;--bg:#F7FAFF;--panel:#fff;--panel-2:#f1f5fa;--line:#cfdae8;
--line-soft:#e2e9f2;--text:#0B1120;--muted:#3e4b62;--dim:#66748c;--cyan:#0b8482;
--cyan-dim:rgba(11,132,130,.12);--coral:#e0472f;--coral-dim:rgba(224,71,47,.12);--amber:#8a5a00;
--amber-dim:rgba(214,150,20,.18);--tile:transparent;--wm:.03;--sun:block;--moon:none;
--shadow:0 1px 2px rgba(20,35,60,.05),0 6px 20px rgba(20,35,60,.05)"""
_DARK = """color-scheme:dark;--bg:#0B1120;--panel:#101827;--panel-2:#141d30;--line:#273552;
--line-soft:#1a2540;--text:#F7FAFF;--muted:#C9D6E5;--dim:#8393ad;--cyan:#32D5D2;
--cyan-dim:rgba(50,213,210,.12);--coral:#FF5A4E;--coral-dim:rgba(255,90,78,.14);--amber:#f5b83d;
--amber-dim:rgba(245,184,61,.14);--tile:#E6EDF6;--wm:.045;--sun:none;--moon:block;
--shadow:0 1px 2px rgba(0,0,0,.35),0 6px 20px rgba(0,0,0,.2)"""
_BASE = """
:root{--display:"Space Grotesk","Segoe UI",system-ui,-apple-system,sans-serif;
--mono:"JetBrains Mono",ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
*{box-sizing:border-box}
html{-webkit-print-color-adjust:exact;print-color-adjust:exact}
body{margin:0;background:var(--bg);color:var(--text);font:16px/1.6 var(--display)}
.accent{height:4px;background:linear-gradient(90deg,var(--cyan),var(--coral))}
.wm{position:fixed;inset:0;background:var(--mark) center/min(60vmin,440px) no-repeat;
opacity:var(--wm);pointer-events:none;z-index:10}
.wrap{max-width:980px;margin:0 auto;padding:24px clamp(16px,4vw,40px) 48px}
.top{display:flex;align-items:center;gap:10px}
.brand{display:flex;align-items:center;gap:10px;font-weight:700;font-size:21px;letter-spacing:-.02em}
.brand i{width:34px;height:34px;border-radius:9px;
background:var(--mark) center/82% no-repeat,var(--tile)}
.top .brand{margin-right:auto}
button{font:600 14px var(--display);color:var(--text);background:var(--panel);
border:1px solid var(--line);border-radius:9px;height:38px;cursor:pointer}
button:hover{border-color:var(--cyan);color:var(--cyan)}
button svg{width:17px;height:17px;fill:none;stroke:currentColor;stroke-width:1.9;
stroke-linecap:round;stroke-linejoin:round}
.icon{width:38px;display:inline-grid;place-items:center;padding:0}
.theme .sun{display:var(--sun)}.theme .moon{display:var(--moon)}
.print{display:inline-flex;align-items:center;gap:8px;padding:0 14px}
.hero{margin-top:24px;padding:28px clamp(20px,4vw,34px);border:1px solid var(--line);
border-radius:18px;box-shadow:var(--shadow);
background:radial-gradient(520px 220px at 0 0,var(--cyan-dim),transparent 70%),
radial-gradient(480px 220px at 100% 100%,var(--coral-dim),transparent 70%),var(--panel)}
.eyebrow{margin:0;font-size:15px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;
color:var(--coral)}
h1{font-size:clamp(26px,4.5vw,36px);line-height:1.1;margin:6px 0 18px;letter-spacing:-.03em;
overflow-wrap:anywhere}
.pills{display:flex;flex-wrap:wrap;gap:8px}
.pill{display:inline-flex;align-items:center;gap:8px;font-size:14px;padding:4px 12px;
border:1px solid var(--line);border-radius:99px;background:var(--panel)}
.pill span{color:var(--dim)}.pill b{font-weight:600}
section{margin-top:44px}
h2{display:flex;align-items:center;gap:10px;font-size:14px;font-weight:700;text-transform:uppercase;
letter-spacing:.1em;color:var(--cyan);margin:0 0 16px}
h2::after{content:"";flex:1;height:1px;background:var(--line)}
h3.sub{font-size:18px;margin:30px 0 12px;letter-spacing:-.01em}
.aside{margin-left:8px;font-size:13px;font-weight:500;color:var(--dim)}
.note{color:var(--dim);font-size:14.5px;margin:-4px 0 16px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:18px 20px;
box-shadow:var(--shadow);margin:0}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:14px}
.stat{position:relative;overflow:hidden;background:var(--panel);border:1px solid var(--line);
border-radius:14px;padding:16px 18px;box-shadow:var(--shadow)}
.stat::before{content:"";position:absolute;inset:0 0 auto;height:3px;
background:linear-gradient(90deg,var(--cyan),transparent)}
.stat .k{font-size:14px;color:var(--muted);font-weight:500}
.stat .v{font-size:32px;font-weight:700;letter-spacing:-.03em;margin:4px 0 2px;
font-variant-numeric:tabular-nums}
.stat .s{font-size:14px;color:var(--dim)}
.good{--tone:var(--cyan);--tone-dim:var(--cyan-dim)}
.warn{--tone:var(--amber);--tone-dim:var(--amber-dim)}
.bad{--tone:var(--coral);--tone-dim:var(--coral-dim)}
.muted{--tone:var(--muted);--tone-dim:var(--panel-2)}
.badge{display:inline-block;font:600 13px/1.6 var(--display);border-radius:99px;padding:1px 11px;
white-space:nowrap;background:var(--tone-dim);color:var(--tone);vertical-align:1px}
.verdict{display:grid;grid-template-columns:auto 1fr;gap:20px;border-left:6px solid var(--tone);
padding:24px 26px}
.vi{width:52px;height:52px;border-radius:50%;display:grid;place-items:center;
background:var(--tone-dim);color:var(--tone)}
.vi svg{width:28px;height:28px;fill:none;stroke:currentColor;stroke-width:2.6;
stroke-linecap:round;stroke-linejoin:round}
.vk{font-size:15px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--muted)}
.vv{font-size:28px;font-weight:700;color:var(--tone);line-height:1.15;letter-spacing:-.02em;
margin:2px 0 8px}
.verdict p{margin:0;font-size:17px}
dl{display:grid;grid-template-columns:max-content 1fr;gap:6px 18px;margin:16px 0 0;
padding-top:14px;border-top:1px solid var(--line-soft);font-size:15px}
dt{color:var(--dim)}dd{margin:0;font-weight:600}
.goals{display:grid;gap:16px}
.goal{border-left:5px solid var(--tone)}
.goal header{display:flex;align-items:center;gap:12px;flex-wrap:wrap}
.goal h3{margin:0;font-size:21px;letter-spacing:-.01em}
.goal>p{margin:10px 0 4px}
.row{display:grid;grid-template-columns:110px 1fr;gap:14px;margin-top:14px;font-size:15px}
.label{font-size:13px;font-weight:700;color:var(--dim);text-transform:uppercase;letter-spacing:.08em;
padding-top:3px}
.row.warn .label,.row.bad .label{color:var(--tone)}
.row small,td small{display:block;color:var(--dim);font-size:14px;margin-top:4px}
.ready{position:relative;height:12px;margin:28px 0;border-radius:99px;background:var(--panel-2);
border:1px solid var(--line-soft)}
.ready .fill{position:absolute;inset:-1px auto -1px -1px;border-radius:99px;background:var(--tone)}
.mark{position:absolute;top:-8px;bottom:-8px;width:2px;margin-left:-1px;border-radius:2px;
background:var(--muted)}
.mark span{position:absolute;left:50%;transform:translateX(-50%);white-space:nowrap;font-size:13px;
font-weight:600;color:var(--muted);font-style:normal}
.mark.lo span{bottom:calc(100% + 3px)}.mark.hi span{top:calc(100% + 3px)}
.mark.l span{left:0;transform:none}.mark.r span{left:auto;right:0;transform:none}
.have{display:flex;justify-content:space-between;gap:12px;margin:0;font-size:14px;color:var(--dim)}
.have b{color:var(--text)}.scale{font-size:12px;white-space:nowrap}
.flow{display:grid;gap:12px}
.route{display:grid;grid-template-columns:minmax(150px,210px) 56px 1fr;align-items:center}
.node{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:12px 16px;
box-shadow:var(--shadow)}
.node b{display:block;font-size:16px}
.node small{display:block;color:var(--dim);font-size:14px;margin-top:2px}
.node.dst{border-color:color-mix(in srgb,var(--cyan) 40%,var(--line));
background:linear-gradient(90deg,var(--cyan-dim),transparent 65%),var(--panel)}
.node.dst b{color:var(--cyan)}
.arrow{position:relative;height:2px;background:linear-gradient(90deg,var(--line),var(--cyan))}
.arrow::after{content:"";position:absolute;right:-1px;top:-5px;border:6px solid transparent;
border-left:8px solid var(--cyan);border-right:0}
.track{display:block;height:10px;background:var(--panel-2);border:1px solid var(--line-soft);
border-radius:99px;overflow:hidden}
.track i{display:block;height:100%;border-radius:99px;background:var(--cyan)}
.bars{display:grid;gap:12px}
.bar{display:grid;grid-template-columns:minmax(76px,max-content) 1fr 52px;gap:14px;
align-items:center;font-size:15px}
.bk,.chip,code{font-family:var(--mono)}
.bv{text-align:right;color:var(--muted);font-variant-numeric:tabular-nums;font-weight:600}
.chips{display:flex;flex-wrap:wrap;gap:10px}
.chip{font-size:14px;background:var(--panel);border:1px solid var(--line);border-radius:99px;
padding:4px 13px;overflow-wrap:anywhere}
.chip.pii{background:var(--coral-dim);
border-color:transparent;color:var(--coral)}
code{font-size:.88em;background:var(--panel-2);border:1px solid var(--line-soft);border-radius:6px;
padding:1px 7px;overflow-wrap:anywhere}
.table{overflow-x:auto;background:var(--panel);border:1px solid var(--line);border-radius:14px;
box-shadow:var(--shadow)}
table{width:100%;border-collapse:collapse;font-size:15px}
th{text-align:left;font-size:13px;font-weight:700;color:var(--dim);text-transform:uppercase;
letter-spacing:.08em;padding:12px 16px;border-bottom:1px solid var(--line);
background:var(--panel-2)}
td{padding:12px 16px;border-bottom:1px solid var(--line-soft);vertical-align:top}
tr:last-child td{border-bottom:0}
td.path{font-family:var(--mono);font-size:14px;overflow-wrap:anywhere;min-width:150px}
ul.notes,ol.steps{list-style:none;padding:8px 22px}
ul.notes li,ol.steps li{position:relative;padding:10px 0 10px 40px}
ul.notes li+li,ol.steps li+li{border-top:1px solid var(--line-soft)}
ul.notes li::before{content:"";position:absolute;left:9px;top:19px;width:9px;height:9px;
border-radius:50%;background:var(--coral)}
ol.steps{counter-reset:step}
ol.steps li{counter-increment:step}
ol.steps li::before{content:counter(step);position:absolute;left:0;top:9px;width:27px;height:27px;
border-radius:50%;display:grid;place-items:center;font-size:14px;font-weight:700;
background:var(--cyan-dim);color:var(--cyan)}
a{color:var(--cyan)}
footer{margin-top:56px;padding-top:20px;border-top:1px solid var(--line);color:var(--dim);
font-size:14px}
footer .brand{font-size:17px;color:var(--text)}
footer .brand i{width:26px;height:26px;border-radius:7px}
footer p{margin:8px 0}
@media (max-width:600px){.row{grid-template-columns:1fr;gap:2px}.route{grid-template-columns:1fr}
.arrow{width:2px;height:22px;margin-left:28px;background:linear-gradient(180deg,var(--line),var(--cyan))}
.arrow::after{right:auto;top:auto;bottom:-1px;left:-5px;border:6px solid transparent;
border-top:8px solid var(--cyan);border-bottom:0}
.stat .v{font-size:27px}.vv{font-size:24px}.verdict{grid-template-columns:1fr;gap:12px;padding:20px}
.vi{width:44px;height:44px}}
@page{size:A4;margin:14mm}
"""
_PRINT = """body{background:#fff}.wrap{max-width:none;padding:0}.top button{display:none}
.wm{background-size:110mm}.hero{margin-top:8px}.stats{grid-template-columns:repeat(4,1fr)}
.card,.stat,.table,.hero{box-shadow:none}
.stat,.card,.goal,.table,.route,tr,footer{break-inside:avoid}h2,h3{break-after:avoid}.table{overflow:visible}"""
CSS = (
    ":root{" + _LIGHT + "}"
    "@media (prefers-color-scheme:dark){:root:not([data-theme=light]){" + _DARK + "}}"
    ":root[data-theme=dark]{" + _DARK + "}" + _BASE + "@media print{"
    ":root,:root[data-theme],:root:not([data-theme=light]){" + _LIGHT + "}" + _PRINT + "}"
)
