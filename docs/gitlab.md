# GitLab mirror and CI (gitlab.com, Free tier)

GitHub stays the source of truth. A GitHub Actions workflow
(`.github/workflows/mirror-gitlab.yml`) pushes **every branch and tag** to a GitLab
project, where `.gitlab-ci.yml` runs the same checks as GitHub and publishes its own
release images, GitLab Releases and a GitLab Pages demo.

Everything here works on the **Free** tier of gitlab.com. Two Free-tier limits shape
the design:

- **Pull mirroring is not included in Free**, so GitLab cannot fetch from GitHub
  itself. GitHub pushes instead.
- **Project access tokens are not included in Free** on gitlab.com, so the push uses an
  SSH **deploy key** with write access. It only works for this one project.

## What runs where

| GitHub (source) | GitLab (mirror) | When |
|---|---|---|
| `ci.yml`: backend, e2e, Docker + TLS smoke | `backend`, `e2e`, `docker-tls-smoke` | every push to `main`, and release tags |
| CodeQL | SAST + secret detection (GitLab templates) | every push to `main` |
| `release.yml` creates the `vX.Y.Z` tag | nothing: the tag arrives through the mirror | |
| `publish-images.yml`: GHCR images + GitHub Release | `images` + `release-notes` + `release`: GitLab Container Registry + GitLab Release | each `vX.Y.Z` tag |
| `pages.yml`: GitHub Pages demo | `pages`: GitLab Pages demo (`demo.js` is active on `*.gitlab.io`) | pushes to `main` that change `frontend/` or `CHANGELOG.md` |
| Dependabot | nothing needed: its updates arrive through GitHub | |

GitLab never creates tags itself. If it did, they could clash with the tags
mirrored from GitHub.

Other branches are mirrored but **not tested** on GitLab, because GitHub already tests
pull requests. This keeps the pipeline within the Free tier's compute minutes (400 per
month). A push to `main` uses about 10 minutes and a release about 5 more. To save
minutes, remove the two `include:` templates (SAST and secret detection); GitHub's
CodeQL already scans the code.

## One-time setup

### 1. GitLab account and project

1. Sign up at <https://gitlab.com>. To use the shared CI runners, new accounts must be
   **verified** (phone number or credit card; nothing is charged on Free).
2. **New project → Create blank project**, for example `kiosk-app`. Visibility:
   **Public**, so the images and the Pages demo can be used without logging in.
   **Untick** "Initialize repository with a README", because the mirror must push into
   an empty project.
3. Note the project path, for example `your-name/kiosk-app`.

### 2. Deploy key (lets GitHub push to GitLab)

On your own computer:

```bash
ssh-keygen -t ed25519 -N "" -C "github-to-gitlab mirror" -f gitlab_mirror
```

This creates `gitlab_mirror` (private key) and `gitlab_mirror.pub` (public key).

- **GitLab:** project → **Settings → Repository → Deploy keys → Add new key**. Paste
  `gitlab_mirror.pub` as the key and tick **Grant write permissions to this key**.
- **GitLab:** **Settings → Repository → Protected branches**. For `main`, add the
  deploy key under **Allowed to push and merge** and turn on **Allowed to force push**.
  The mirror overwrites GitLab's `main` so that it always matches GitHub. Nobody should
  commit on GitLab directly.

### 3. GitHub settings (switches the mirror on)

In the GitHub repository → **Settings → Secrets and variables → Actions**:

- **Secrets → New repository secret:** `GITLAB_DEPLOY_KEY` = the full contents of the
  private key file `gitlab_mirror`. Then delete the key file from your computer.
- **Variables → New repository variable:** `GITLAB_REPO` = the project path, for example
  `your-name/kiosk-app`.

Until `GITLAB_REPO` is set, the mirror workflow does nothing.

### 4. First mirror

GitHub → **Actions → Mirror to GitLab → Run workflow** (on `main`). It pushes all
branches and tags. GitLab then starts a pipeline for `main`, and one for each release
tag that is new to GitLab. All existing tags arrive at once, so the first run releases
every old version. To skip that, cancel those tag pipelines in GitLab → **Build →
Pipelines**.

After this, every push to GitHub (and every release made by `release.yml`) is mirrored
automatically.

### 5. Results on GitLab

- **Pipelines:** project → **Build → Pipelines**.
- **Images:** `registry.gitlab.com/<your-name>/kiosk-app/backend` and `.../frontend`,
  tagged `X.Y.Z` and `latest`. With a public project they can be pulled without
  logging in.
- **Releases:** project → **Deploy → Releases**, with the CHANGELOG notes.
- **Demo:** project → **Deploy → Pages** shows the URL, usually
  `https://<your-name>.gitlab.io/kiosk-app/`.

## Notes

- `docker-tls-smoke` and `images` use Docker-in-Docker (`docker:dind`), which
  gitlab.com's shared runners support. The compose stack then runs inside the `docker`
  service, so the checks call `https://docker` instead of `https://localhost`. The
  browser smoke test (`tests/e2e/https-smoke.js`, host taken from `SMOKE_HOST`) runs in
  Playwright's image on that Docker host. Keep its tag (`v1.64.1`) equal to the
  `playwright` version in `tests/e2e/package-lock.json` when Dependabot updates it.
- Release notes come from `scripts/release-notes.sh`, which GitHub's
  `publish-images.yml` uses too.
- Free-tier storage is 10 GiB per project, and the container images count toward it.
  Old image tags can be cleaned up under **Settings → Packages and registries →
  Cleanup policies**.
