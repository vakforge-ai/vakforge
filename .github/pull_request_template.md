## What

<!-- One or two sentences: what this pull request changes. -->

## Why

<!-- The problem it fixes or the need it meets. Link the issue if there is one (Fixes #123). -->

## How to check

<!-- What you ran and what a reviewer can run or look at: commands, tests added, pages to open. -->

## Checklist

- [ ] `uv run pytest` passes on CPU with no downloads
- [ ] `uv run ruff check . && uv run ruff format --check .` is clean
- [ ] Commits are small and logical, one concern each
- [ ] Docs updated (`docs/*.md`, `README.md`) and `docs/ROADMAP.md` checkboxes ticked
- [ ] No audio binaries, checkpoints, or real customer data in the diff
- [ ] Upstream APIs verified against installed source or a pinned commit (say where)
- [ ] No language-specific logic in core; PII and consent checks not weakened silently
