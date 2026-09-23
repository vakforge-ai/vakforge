# Contributing to vakforge

## Ground rules

- We ship recipes we have actually run. A PR adding a model that "should work" is not mergeable; a PR adding a model with a committed `report.json` on the demo dataset is.
- Core stays dependency-light. If your change makes `import vakforge.schema` pull in torch, it will be rejected.
- Language- or market-specific logic goes in a locale pack (`docs/LOCALE_PACKS.md`). A PR that adds `if lang == "..."` to core will be asked to move it.
- Upstream APIs are verified against source, and the version is pinned. Say where you verified it in the PR description.
- Data safety code paths (redaction, consent) cannot be bypassed silently. Any new flag that weakens them must log a warning.

## Setup

```bash
git clone https://github.com/vakforge-ai/vakforge && cd vakforge
uv sync --group dev
uvx pre-commit install   # runs ruff and file checks on every commit
uv run pytest            # must pass on CPU with no downloads
uv run ruff check . && uv run ruff format --check .
```

Recipe work. The extras are declared but still empty — each one gets its pins when that recipe is
actually built, so these commands work today and install nothing extra:

```bash
uv sync --group dev --extra lfm25      # or --extra moshi / --extra qwen / --extra cascade
uv run pytest -m model                 # opt-in, downloads models
uv run pytest -m gpu                   # opt-in, needs CUDA
```

Docs site (`site/docs/` is generated and committed, so rebuild before you push):

```bash
uv run --group docs python scripts/build_docs.py
```

## What CI checks

`lint`, `test-linux` (3.11/3.12/3.13), `test-windows`, `docs` (the generated site must match
`docs/`), `package` (build, `twine check`, install the wheel into a clean environment, run the
CLI from it), `coverage` (branch coverage, 90% floor) and `dependency-audit` (`pip-audit` over
the locked runtime set).

Every action is pinned to a commit SHA — a moving tag like `v7` can be repointed at any commit
by whoever owns the action. Dependabot updates the SHAs; keep the trailing `# v7` comment so the
release is still readable.

## Branches and commits

- **Features and anything substantial** go on a branch from `main` (`feat/<area>-<short>`, `ci/…`, `docs/…`) and land through a pull request. Merge only when CI is green.
- **Small fixes** (typos, one-line corrections, copy tweaks) may go straight to `main`.
- `main` has no branch protection while the repository is private on the free plan, so these rules are enforced by review, not by GitHub. Do not force-push `main`.
- Commits are small and logical: one concern per commit, several commits per branch. A branch that adds a CLI command, its tests and its docs is three commits, not one.
- Conventional commit messages: `feat(prepare): roman-hindi language tagging`.
- One logical change per PR. Large recipes land as a sequence: adapter → train wrapper → eval → serve.

## Releases

1. Bump `version` in `pyproject.toml` and `__version__` in `vakforge/__init__.py`, run `uv lock`, commit as `chore(release): X.Y.Z`.
2. Push a matching tag: `git tag -a vX.Y.Z -m "vX.Y.Z" && git push origin vX.Y.Z`.
3. The `release` workflow checks the tag against the version, runs tests, builds, publishes to PyPI through trusted publishing (no token is involved), and then creates the GitHub Release with generated notes and the same wheel and sdist attached.

PyPI never lets a published version change, so check the README renders (images must use public URLs) before tagging.

## Security

Report vulnerabilities privately as described in [`SECURITY.md`](SECURITY.md), never in a public issue.

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
