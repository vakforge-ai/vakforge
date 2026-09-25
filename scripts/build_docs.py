"""Build the documentation site: docs/*.md (plus README, CONTRIBUTING, the skill) -> site/docs/.

Run `uv run --group docs python scripts/build_docs.py`. The output is plain HTML that
Cloudflare Pages serves as-is next to the landing page; nothing runs at request time.
Each page gets the shared shell (sidebar, on-page contents, search, theme), and links
between markdown files become links between pages. Links to anything else in the repo
point at GitHub.
"""

from __future__ import annotations

import html
import json
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from markdown_it import MarkdownIt
from markdown_it.token import Token
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name
from pygments.util import ClassNotFound

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "site" / "docs"
DIAGRAMS = Path(__file__).resolve().parent / "diagrams"
MISSING: list[str] = []  # mermaid blocks with no drawn counterpart, reported at the end
REPO = "https://github.com/vakforge-ai/vakforge"


@dataclass
class Page:
    slug: str  # output file name without .html; "index" for the overview
    title: str
    source: Path  # markdown file, relative to ROOT
    group: str
    blurb: str = ""
    headings: list[tuple[int, str, str]] = field(default_factory=list)  # level, text, id
    body: str = ""
    search: list[dict] = field(default_factory=list)


PAGES = [
    Page(
        "index",
        "Overview",
        Path("README.md"),
        "Start",
        "What vakforge is and how the decision is made",
    ),
    Page(
        "decision-guide",
        "Decision guide",
        Path("docs/DECISION_GUIDE.md"),
        "Start",
        "What needs customizing, and when not to fine-tune",
    ),
    Page(
        "agent-skill",
        "Agent skill",
        Path("skill/vakforge/SKILL.md"),
        "Start",
        "The workflow a coding agent follows for your project",
    ),
    Page(
        "data-format",
        "Data format",
        Path("docs/DATA_FORMAT.md"),
        "Reference",
        "The canonical vakforge.jsonl record and its rules",
    ),
    Page(
        "locale-packs",
        "Locale packs",
        Path("docs/LOCALE_PACKS.md"),
        "Reference",
        "What a pack contains and how to add one",
    ),
    Page(
        "architecture",
        "Architecture",
        Path("docs/ARCHITECTURE.md"),
        "Reference",
        "How the code fits together",
    ),
    Page(
        "recipes",
        "Recipes",
        Path("docs/RECIPES.md"),
        "Reference",
        "Per-model training recipes and their status",
    ),
    Page(
        "evaluation",
        "Evaluation",
        Path("docs/EVALUATION.md"),
        "Reference",
        "Metrics, the report, per-locale benchmarks",
    ),
    Page(
        "data-ethics",
        "Data ethics",
        Path("docs/DATA_ETHICS.md"),
        "Project",
        "Consent, personal data, licences, privacy law",
    ),
    Page(
        "research",
        "Research",
        Path("docs/RESEARCH.md"),
        "Project",
        "The evidence behind every threshold",
    ),
    Page(
        "roadmap",
        "Roadmap",
        Path("docs/ROADMAP.md"),
        "Project",
        "What works today and what is next",
    ),
    Page(
        "contributing",
        "Contributing",
        Path("CONTRIBUTING.md"),
        "Project",
        "How to work on vakforge",
    ),
]
GROUPS = ["Start", "Reference", "Project"]
BY_SOURCE = {str(p.source).replace("\\", "/"): p for p in PAGES}

_slug_strip = re.compile(r"[^\w\s-]")


def slugify(text: str) -> str:
    return re.sub(r"[\s_]+", "-", _slug_strip.sub("", text.lower())).strip("-") or "section"


def rewrite_href(href: str, page: Page) -> str:
    """Markdown-to-markdown links become page links; other repo paths go to GitHub."""
    if re.match(r"^(https?:|mailto:|#)", href):
        return href
    target, _, anchor = href.partition("#")
    anchor = f"#{anchor}" if anchor else ""
    src_dir = page.source.parent
    resolved = (src_dir / target).as_posix() if target else ""
    resolved = re.sub(r"^(\./)+", "", resolved)
    while "../" in resolved:
        resolved = (
            re.sub(r"[^/]+/\.\./", "", resolved, count=1)
            if re.search(r"[^/]+/\.\./", resolved)
            else resolved.replace("../", "", 1)
        )
    if resolved in BY_SOURCE:
        p = BY_SOURCE[resolved]
        return ("./" if p.slug == "index" else f"{p.slug}.html") + anchor
    if not target:
        return anchor
    kind = "tree" if not Path(resolved).suffix else "blob"
    return f"{REPO}/{kind}/main/{resolved}{anchor}"


def make_renderer(page: Page) -> MarkdownIt:
    # html=False: raw HTML in a markdown file would otherwise render straight into the
    # published page, so a docs-only pull request — the kind least likely to get a security
    # read — could put a script tag on the site. Our markdown uses none, and the diagrams go
    # through the fence handler below rather than as raw HTML.
    # linkify off: bare URLs stay text, links are written explicitly.
    md = MarkdownIt("gfm-like", {"html": False}).disable("linkify")
    formatter = HtmlFormatter(nowrap=True)

    def fence(renderer, tokens, idx, options, env):
        tok = tokens[idx]
        lang = (tok.info or "").strip().split()[0] if tok.info else ""
        code = tok.content
        if lang == "mermaid":
            # GitHub renders the mermaid source; here we substitute the drawn version,
            # matched by the `%% diagram: <name>` marker inside the block.
            m = re.search(r"%%\s*diagram:\s*([\w-]+)", code)
            svg = DIAGRAMS / f"{m.group(1)}.svg" if m else None
            if svg and svg.exists():
                drawn = svg.read_text(encoding="utf-8").strip()
                return f'<figure class="diagram-figure">{drawn}</figure>\n'
            MISSING.append(m.group(1) if m else f"{page.source}: unmarked mermaid block")
            return (
                '<div class="code-block"><pre class="highlight">'
                f"<code>{html.escape(code)}</code></pre></div>\n"
            )
        try:
            body = (
                highlight(code, get_lexer_by_name(lang or "text"), formatter)
                if lang
                else html.escape(code)
            )
        except ClassNotFound:
            body = html.escape(code)
        label = f'<span class="code-lang">{html.escape(lang)}</span>' if lang else ""
        return (
            f'<div class="code-block">{label}'
            '<button class="code-copy" type="button" aria-label="Copy code">copy</button>'
            f'<pre class="highlight"><code>{body}</code></pre></div>\n'
        )

    def link_open(renderer, tokens, idx, options, env):
        tok = tokens[idx]
        href = tok.attrGet("href") or ""
        new = rewrite_href(href, page)
        tok.attrSet("href", new)
        if new.startswith("http"):
            tok.attrSet("target", "_blank")
            tok.attrSet("rel", "noopener")
        return renderer.renderToken(tokens, idx, options, env)

    md.add_render_rule("fence", fence)
    md.add_render_rule("link_open", link_open)
    return md


def inline_text(token: Token) -> str:
    return "".join(c.content for c in (token.children or []) if c.type in ("text", "code_inline"))


def render(page: Page, text: str) -> None:
    md = make_renderer(page)
    tokens = md.parse(text)
    seen: dict[str, int] = {}
    current: dict | None = None
    for i, tok in enumerate(tokens):
        if tok.type == "heading_open":
            level = int(tok.tag[1])
            title = inline_text(tokens[i + 1])
            hid = slugify(title)
            if hid in seen:
                seen[hid] += 1
                hid = f"{hid}-{seen[hid]}"
            else:
                seen[hid] = 0
            tok.attrSet("id", hid)
            if level == 1 and not page.headings and not any(h[0] == 1 for h in page.headings):
                pass
            page.headings.append((level, title, hid))
            current = {
                "page": page.slug,
                "title": page.title,
                "heading": title,
                "anchor": hid,
                "text": "",
            }
            page.search.append(current)
        elif (
            tok.type == "inline" and current is not None and tokens[i - 1].type == "paragraph_open"
        ):
            if len(current["text"]) < 320:
                current["text"] = (current["text"] + " " + inline_text(tok)).strip()[:320]
    body = md.renderer.render(tokens, md.options, {})
    # tables scroll instead of breaking the layout on narrow screens
    body = body.replace("<table>", '<div class="table-wrap"><table>').replace(
        "</table>", "</table></div>"
    )
    # GitHub task lists
    body = re.sub(
        r"<li>\[x\] ", '<li class="task done"><input type="checkbox" checked disabled> ', body
    )
    body = re.sub(r"<li>\[ \] ", '<li class="task"><input type="checkbox" disabled> ', body)
    page.body = body


# The README centres its images with HTML, which GitHub renders. The renderer escapes raw
# HTML, so those blocks were published as literal "<p align=...>" text; each one becomes a
# markdown image instead. The banner is dropped: the docs shell has its own header.
_CENTRED_IMG = re.compile(r'<p align="center">\s*<img\s+src="([^"]+)"\s+alt="([^"]*)"[^>]*>\s*</p>')


def _centred_image(m: re.Match[str]) -> str:
    src, alt = m.groups()
    # The README needs absolute URLs; the docs sit next to the same assets.
    src = src.replace("https://vakforge.pages.dev/", "../")
    return "" if "readme-banner" in src else f"![{alt}]({src})"


def load_source(page: Page) -> str:
    text = _CENTRED_IMG.sub(_centred_image, (ROOT / page.source).read_text(encoding="utf-8"))
    if text.startswith("---"):  # skill frontmatter
        text = re.sub(r"^---\n.*?\n---\n", "", text, count=1, flags=re.S)
        preamble = (
            "# Agent skill\n\n"
            "The text below is `skill/vakforge/SKILL.md` verbatim: the instructions a coding "
            "agent follows when the vakforge skill is installed.\n\n"
        )
        text = preamble + text
    return text


def sidebar(current: Page) -> str:
    out = []
    for g in GROUPS:
        out.append(f'<div class="sb-group"><div class="sb-title">{g}</div><ul>')
        for p in PAGES:
            if p.group != g:
                continue
            href = "./" if p.slug == "index" else f"{p.slug}.html"
            cur = ' aria-current="page"' if p is current else ""
            out.append(f'<li><a href="{href}"{cur}>{p.title}</a></li>')
        out.append("</ul></div>")
    return "\n".join(out)


def toc(page: Page) -> str:
    items = [(lvl, t, i) for lvl, t, i in page.headings if lvl in (2, 3)]
    if not items:
        return ""
    lis = "".join(
        f'<li class="lvl{lvl}"><a href="#{i}">{html.escape(t)}</a></li>' for lvl, t, i in items
    )
    return (
        '<nav class="toc" aria-label="On this page">'
        f'<div class="toc-title">On this page</div><ul>{lis}</ul></nav>'
    )


def prev_next(page: Page) -> str:
    i = PAGES.index(page)
    parts = []
    if i > 0:
        p = PAGES[i - 1]
        href = "./" if p.slug == "index" else f"{p.slug}.html"
        parts.append(
            f'<a class="pn prev" href="{href}"><small>Previous</small><b>{p.title}</b></a>'
        )
    else:
        parts.append("<span></span>")
    if i < len(PAGES) - 1:
        p = PAGES[i + 1]
        parts.append(
            f'<a class="pn next" href="{p.slug}.html"><small>Next</small><b>{p.title}</b></a>'
        )
    return f'<div class="prev-next">{"".join(parts)}</div>'


# The page shell. Kept as HTML so it is editable as HTML; `{}` placeholders are filled
# by str.format, which is why the inline script doubles its braces.
TEMPLATE = (Path(__file__).resolve().parent / "docs_template.html").read_text(encoding="utf-8")


def version() -> str:
    m = re.search(
        r'^version\s*=\s*"([^"]+)"', (ROOT / "pyproject.toml").read_text(encoding="utf-8"), re.M
    )
    return m.group(1) if m else "dev"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.html"):
        old.unlink()
    index: list[dict] = []
    ver = version()
    for page in PAGES:
        render(page, load_source(page))
        index += page.search
    for page in PAGES:
        html_out = TEMPLATE.format(
            title=html.escape(page.title),
            blurb=html.escape(page.blurb),
            repo=REPO,
            source=page.source.as_posix(),
            version=ver,
            sidebar=sidebar(page),
            body=page.body,
            prev_next=prev_next(page),
            toc=toc(page),
        )
        (OUT / f"{page.slug}.html").write_text(html_out, encoding="utf-8", newline="\n")
    (OUT / "search.json").write_text(
        json.dumps(index, ensure_ascii=False), encoding="utf-8", newline="\n"
    )
    # pygments colours, both themes, appended to the hand-written stylesheet at build time
    css_src = (ROOT / "scripts" / "docs.css").read_text(encoding="utf-8")
    dark = HtmlFormatter(style="github-dark").get_style_defs(".highlight")
    light = HtmlFormatter(style="friendly").get_style_defs(".highlight")
    light_scoped = "\n".join(
        ":root[data-theme=light] " + line if line.startswith(".highlight") else line
        for line in light.splitlines()
    )
    light_media = (
        "@media (prefers-color-scheme: light) {\n"
        + "\n".join(
            ":root:not([data-theme=dark]) " + line if line.startswith(".highlight") else line
            for line in light.splitlines()
        )
        + "\n}"
    )
    (OUT / "docs.css").write_text(
        css_src + "\n/* pygments */\n" + dark + "\n" + light_scoped + "\n" + light_media + "\n",
        encoding="utf-8",
        newline="\n",
    )
    shutil.copyfile(ROOT / "scripts" / "docs.js", OUT / "docs.js")
    print(f"wrote {len(PAGES)} pages, {len(index)} search entries -> {OUT.relative_to(ROOT)}")
    for name in MISSING:
        print(f"  no diagram drawn for {name!r}; it fell back to a code block")


if __name__ == "__main__":
    main()
