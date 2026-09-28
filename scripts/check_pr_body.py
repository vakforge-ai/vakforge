"""Check a pull request description against .github/pull_request_template.md.

The description must keep the template's sections, in order, and fill in each one: What,
Why and How to check need text of their own (the template's `<!-- hints -->` do not
count), and the Checklist keeps its task list. Every problem is reported at once, as a
GitHub error annotation, so one edit can fix them all.

Run by the `pr-description` workflow with the description in PR_BODY and the author in
PR_AUTHOR. Bots write their own descriptions (Dependabot's is a changelog), so their pull
requests pass without a check.
"""

from __future__ import annotations

import os
import re
import sys

SECTIONS = ("What", "Why", "How to check", "Checklist")
PROSE = SECTIONS[:-1]
_COMMENT = re.compile(r"<!--.*?-->", re.S)
_HEADING = re.compile(r"^##[ \t]+(.+?)[ \t]*#*[ \t]*$", re.M)
_TASK = re.compile(r"^\s*[-*]\s+\[[ xX]\]\s+\S", re.M)


def problems(body: str) -> list[str]:
    """What is wrong with `body`, in words a contributor can act on; empty if nothing."""
    text = _COMMENT.sub("", body or "").replace("\r\n", "\n")
    found = [(m.group(1).strip(), m.start(), m.end()) for m in _HEADING.finditer(text)]
    names = [name.lower() for name, _, _ in found]
    out = [f"missing the `## {s}` section" for s in SECTIONS if s.lower() not in names]
    present = [s for s in SECTIONS if s.lower() in names]
    order = sorted(present, key=lambda s: names.index(s.lower()))
    if order != present:
        out.append(f"sections are out of order; keep them as {', '.join(SECTIONS)}")
    for i, (name, _, end) in enumerate(found):
        content = text[end : found[i + 1][1] if i + 1 < len(found) else len(text)].strip()
        if name.lower() in (s.lower() for s in PROSE) and not content:
            out.append(f"`## {name}` is empty; the template's hint does not count as text")
        if name.lower() == "checklist" and not _TASK.search(content):
            out.append("`## Checklist` has no `- [ ]` items; keep the template's list")
    return out


def main() -> int:
    author = os.environ.get("PR_AUTHOR", "")
    if author.endswith("[bot]"):
        print(f"{author} writes its own description; not checked")
        return 0
    found = problems(os.environ.get("PR_BODY", ""))
    for problem in found:
        print(f"::error title=Pull request description::{problem}")
    if found:
        print("Edit the description to follow .github/pull_request_template.md; this re-runs.")
        return 1
    print("The description follows the template.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
