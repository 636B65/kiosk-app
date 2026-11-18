# Security policy

## Supported versions

Only the latest release of Kiosk App (the newest `vX.Y.Z` tag and the
`latest` images on GHCR) receives security fixes. The microservice edition,
[kiosk-app-ms](https://github.com/636B65/kiosk-app-ms), follows these releases.

## Reporting a vulnerability

Please **do not open a public issue** for a security problem.

Report it privately through GitHub:
[Security > Report a vulnerability](https://github.com/636B65/kiosk-app/security/advisories/new).
Include what is affected (endpoint, page, version or image digest), how to
reproduce it and the impact you expect.

You can expect an acknowledgement within 7 days and an assessment within
14 days. Confirmed issues are fixed in a new release, published as a GitHub
security advisory, and credited to the reporter unless you prefer otherwise.

## Scope

In scope: the backend, the frontend (including the GitHub Pages demo), the
Docker images, the compose files and the workflows in this repository. Deployment-specific settings (your
secrets, ingress, TLS certificates) and third-party components are out of
scope, but tell us if a default here makes them unsafe.

## Supply chain

- Every image is built in GitHub Actions and has a signed build provenance
  attestation: `gh attestation verify oci://ghcr.io/636b65/kiosk/<backend|frontend>:<version> -R 636B65/kiosk-app`.
- Releases from 1.5.1 on carry a provenance file (`*.intoto.jsonl`) for the published image digests.
- Actions are pinned to commit SHAs, base images to digests, and Python
  dependencies to hashes; Dependabot keeps them current.
- OpenSSF Scorecard, CodeQL and ClusterFuzzLite (fuzzers in `tests/fuzz/`) run on the repository.
