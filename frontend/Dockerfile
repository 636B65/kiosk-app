FROM nginx:alpine

# openssl is needed to generate the self-signed TLS certificate on first start.
RUN apk add --no-cache openssl

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY docker-entrypoint.d/ /docker-entrypoint.d/
COPY index.html /usr/share/nginx/html/index.html
COPY css/ /usr/share/nginx/html/css/
COPY js/ /usr/share/nginx/html/js/

# Release info for the footer. CHANGELOG.md lives in the repo root, so it comes
# from the named build context "repo" (compose: additional_contexts, buildx:
# --build-context repo=.). APP_VERSION / GIT_COMMIT are passed as build args by
# the release workflow, compose.sh and build-offline.sh; plain builds say "dev".
COPY --from=repo CHANGELOG.md /usr/share/nginx/html/CHANGELOG.md
ARG APP_VERSION=dev
ARG GIT_COMMIT=
RUN version="$(printf %s "$APP_VERSION" | tr -cd 'A-Za-z0-9._+-')" \
    && commit="$(printf %s "$GIT_COMMIT" | tr -cd '0-9a-fA-F')" \
    && printf '{"version": "%s", "commit": "%s"}\n' "${version:-dev}" "$commit" \
       > /usr/share/nginx/html/version.json

EXPOSE 80 443

CMD ["nginx", "-g", "daemon off;"]