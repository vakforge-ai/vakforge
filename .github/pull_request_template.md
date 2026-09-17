## What and why

<!-- One or two sentences: what this changes and the reason. Link the issue if there is one. -->

## How to check

<!-- Commands a reviewer can run, or what to look at. -->

## Checklist

- [ ] `uv run pytest` passes on CPU with no downloads
- [ ] `uv run ruff check . && uv run ruff format --check .` is clean
- [ ] Commits are small and logical, one concern each
- [ ] Docs updated (`docs/*.md`, `README.md`) and `docs/ROADMAP.md` checkboxes ticked
- [ ] No audio binaries, checkpoints, or real customer data in the diff
- [ ] Upstream APIs verified against installed source or a pinned commit (say where)
- [ ] No language-specific logic in core; PII and consent checks not weakened silently
