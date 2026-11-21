# Offline continuous integration

`workflows/ci.yml` runs on pull requests, pushes to `main`, and manual dispatch.
It uses Python 3.12, a read-only GitHub token, and no application secrets.
Dependencies are installed from the package index; the test suite uses local
fixtures rather than live Gmail, AI, Supabase, or GitHub integrations.

Checks include Ruff's core syntax/import/error rules across `backend/` and
`tests/`, the full offline pytest suite, and regeneration of the synthetic
snapshot followed by a diff against the committed Markdown. Existing context
tests validate expected record/source IDs, status separation, conflict handling,
and common sensitive-value redaction. This is not live integration validation
or a general-purpose secret scanner.

From the repository root, reproduce the checks with:

```sh
python -m pip install -r .github/ci/requirements.txt
python -m ruff check --config .github/ci/ruff.toml backend tests
python -m pytest tests -q -p no:cacheprovider
python -m backend.services.context_generator --input sample-data/project-state.json --output context/CURRENT_STATE.md --fixture
git diff --exit-code -- context/CURRENT_STATE.md
```

The final command compares against the committed baseline. When intentionally
changing the generator or fixture, review and commit the regenerated snapshot
with that change. Do not hand-edit generated facts to satisfy the check.

Runtime dependencies remain owned by Person A in `backend/requirements.txt`.
CI-only dependencies and Ruff settings live here to avoid edits to that file.
The CI dependency file includes Person A's file rather than duplicating it.
New live integration tests must use mocks for this offline job.

After these files are pushed, inspect the repository's Actions tab or the PR
checks for the actual hosted result. Passing locally does not prove that a
GitHub-hosted run has succeeded. Branch protection is a separate repository
setting; a maintainer can require `Lint, tests, and fixture snapshot` before merge.

Workflow setup follows the official
[GitHub Python guide](https://docs.github.com/en/actions/tutorials/build-and-test-code/python)
and [Ruff configuration reference](https://docs.astral.sh/ruff/configuration/).
