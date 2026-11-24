# nginx 1.31.10 (mainline). 1.31.9 fixed CVE-2026-123007/-123633/-121810 (HTTP/2,
# HTTP/3), CVE-2026-125283 (try_files + alias) and more; 1.31.10 CVE-2026-132779.
FROM nginx:alpine@sha256:b50897d5c7b1aa08067c3d90c5e8b3e47ec4e3c91c91446f67820228f7b41e34

# Pick up Alpine security fixes released after the base image was built;
# openssl is needed to generate the self-signed TLS certificate on first start.
RUN apk upgrade --no-cache && apk add --no-cache openssl

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY docker-entrypoint.d/ /docker-entrypoint.d/
COPY index.html /usr/share/nginx/html/index.html
COPY css/ /usr/share/nginx/html/css/
COPY js/ /usr/share/nginx/html/js/

# Release info for the footer. CHANGELOG.md, scripts/release-info.sh and the
# checkout's .git/HEAD + refs come from the named build context "repo" (compose:
# additional_contexts, buildx: --build-context repo=.), mounted only for this
# step. APP_VERSION / GIT_COMMIT build args win when given (release workflow,
# compose.sh, build-offline.sh); otherwise the newest CHANGELOG.md version and
# the checked-out commit are used, so a plain `docker compose up --build` works.
ARG APP_VERSION=
ARG GIT_COMMIT=
RUN --mount=type=bind,from=repo,target=/tmp/repo \
    cp /tmp/repo/CHANGELOG.md /usr/share/nginx/html/CHANGELOG.md \
    && sh /tmp/repo/scripts/release-info.sh /tmp/repo "$APP_VERSION" "$GIT_COMMIT" \
       > /usr/share/nginx/html/version.json

EXPOSE 80 443

CMD ["nginx", "-g", "daemon off;"]