FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Release info for the admin System page, written the same way as the
# frontend's version.json (see frontend/Dockerfile and scripts/release-info.sh).
ARG APP_VERSION=
ARG GIT_COMMIT=
RUN --mount=type=bind,from=repo,target=/tmp/repo \
    sh /tmp/repo/scripts/release-info.sh /tmp/repo "$APP_VERSION" "$GIT_COMMIT" \
       > /app/release.json

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
