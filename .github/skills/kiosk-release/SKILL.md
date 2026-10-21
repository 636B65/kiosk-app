---
name: kiosk-release
description: Validate, commit, push, release, and publish container images for kiosk-app changes; wait for GitHub CI and release workflows to finish successfully.
---

# Kiosk App release workflow

Use this skill for changes to this repository. Unless the user explicitly opts out of a
release step, finish changes by validating them, recording them in the changelog, committing
and pushing the code, tagging, and confirming the GitHub Release and backend and frontend
container images were published. Do not report completion while required CI or publishing workflows are
still running or failing.

## Before committing

1. Read `AGENTS.md` and follow its repository-specific conventions.
2. Review the worktree and preserve unrelated user changes. Do not commit generated files,
   SQLite databases, TLS certificates, or `node_modules`.
3. Update `CHANGELOG.md` with the next version and current date. Update the test-count line
   to reflect checks actually run.
4. Run the required checks:
   - `cd backend && pytest tests -v`
   - `cd backend && ruff check . && mypy`
   - `node --check frontend/js/*.js`
   - Run the end-to-end suite for behavior or UI changes:
     `cd tests/e2e && CHROMIUM_PATH=/usr/bin/chromium E2E_PYTHON=python3.12 npm test`
   - Run additional focused checks required by the change.
5. Fix failures caused by the change and rerun the relevant checks. Report environmental
   blockers honestly; never treat a skipped or failed check as passing.

## Commit, CI, and release

1. Confirm the target branch and latest version tag. Do not overwrite or amend existing
   commits. Commit the intended changes with a concise message and end it with the
   co-author trailer for the agent doing the work (for example
   `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>` for GitHub
   Copilot), unless the user or agent instructions specify otherwise.
2. Push the commit to `main` (or follow the user's requested branch/PR workflow).
3. Monitor the CI workflow for that exact commit. Wait until the backend API tests,
   end-to-end browser tests, and Docker + TLS smoke test all pass.
   If CI fails, diagnose and fix the issue, push the fix, and wait for CI again.
4. Do not tag by hand. Once main CI succeeds, the `Release` workflow tags the tested commit
   with the newest CHANGELOG.md version (if that tag does not exist yet) and calls
   `Publish container images`. Use the repository's next-version convention in
   CHANGELOG.md and never reuse a version.
5. Wait for the `Release` workflow run to succeed: its tag job, both image builds, and the
   `release` job that creates the GitHub Release from the tag's CHANGELOG.md section. Do
   not create the release by hand or attach source assets unless requested; if a job fails,
   fix the cause (usually a missing changelog section) and re-run it. The expected GHCR
   images are:
   - `ghcr.io/636b65/kiosk/backend:<version>` and `:latest`
   - `ghcr.io/636b65/kiosk/frontend:<version>` and `:latest`
6. Report the commit, tag/release, CI result, and image-publishing result. Clearly state
   anything that remains pending or blocked.

## Operational notes

- The release process is documented in `AGENTS.md`; keep this skill consistent with it.
- GHCR packages may be private. Do not change package visibility or expose credentials.
- Do not claim CI or image publication succeeded based only on local tests or an accepted
  workflow run; inspect the completed workflow conclusions.
