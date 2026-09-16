# Contributing to vakforge

## Ground rules

- We ship recipes we have actually run. A PR adding a model that "should work" is not mergeable; a PR adding a model with a committed `report.json` on the demo dataset is.
- Core stays dependency-light. If your change makes `import vakforge.schema` pull in torch, it will be rejected.
- Language- or market-specific logic goes in a locale pack (`docs/LOCALE_PACKS.md`). A PR that adds `if lang == "..."` to core will be asked to move it.
- Upstream APIs are verified against source, and the version is pinned. Say where you verified it in the PR description.
- Data safety code paths (redaction, consent) cannot be bypassed silently. Any new flag that weakens them must log a warning.

## Setup

```bash
git clone <repo> && cd vakforge
uv sync --extra dev
uv run pytest            # must pass on CPU with no downloads
uv run ruff check . && uv run ruff format --check .
```

Recipe work:

```bash
uv sync --extra dev --extra lfm25      # or --extra moshi / --extra qwen / --extra cascade
uv run pytest -m model                 # opt-in, downloads models
uv run pytest -m gpu                   # opt-in, needs CUDA
```

## Branches and commits

- Branch from `main`: `feat/<area>-<short>`, `fix/…`, `docs/…`.
- Conventional commits: `feat(prepare): roman-hindi language tagging`.
- One logical change per PR. Large recipes land as a sequence: adapter → train wrapper → eval → serve.

## Pull request checklist

- [ ] Tests added/updated; CPU suite green
- [ ] `ruff` clean
- [ ] Docs updated (`docs/*.md`, `README.md` recipe table if applicable)
- [ ] `docs/ROADMAP.md` checkbox ticked
- [ ] For upstream integrations: version pinned, verification noted, `UPSTREAM_NOTES.md` updated
- [ ] For recipes: `LICENSE_NOTES.md` present; per-locale support declared in launch packs
- [ ] For locale packs: golden tests for normalizer, `detect_lang`, and every PII pattern; `privacy_notes` sourced
- [ ] No audio binaries, checkpoints, or real customer data in the diff

## Reporting model or data issues

Open an issue with: recipe, config hash, manifest hash, `versions.txt`, and the relevant slice of `report.json`. Do not attach real customer audio to issues.

## Code style

Python 3.11+, type hints, docstrings on public functions, `pydantic` for anything that crosses a boundary, `rich` for user-facing output, no print debugging left behind.

## Licence

By contributing you agree your code is released under Apache-2.0. Model weights and datasets keep their own licences.
