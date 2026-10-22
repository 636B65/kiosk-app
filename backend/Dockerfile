FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Release info shown on the admin System page (same build args as the frontend).
ARG APP_VERSION=dev
ARG GIT_COMMIT=
ENV APP_VERSION=${APP_VERSION} GIT_COMMIT=${GIT_COMMIT}

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
