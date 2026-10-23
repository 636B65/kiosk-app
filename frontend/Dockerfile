FROM nginx:alpine

# openssl is needed to generate the self-signed TLS certificate on first start.
RUN apk add --no-cache openssl

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