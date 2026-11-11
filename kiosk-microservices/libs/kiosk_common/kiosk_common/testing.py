"""Test helpers: run several services in one process and wire them together."""

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient


class InProcessTransport(httpx.BaseTransport):
    """httpx transport that hands requests to a FastAPI app via its TestClient."""

    def __init__(self, app: FastAPI):
        self.client = TestClient(app, raise_server_exceptions=False)

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        headers = {k: v for k, v in request.headers.items() if k.lower() not in ("host", "content-length")}
        response = self.client.request(
            request.method,
            request.url.raw_path.decode(),
            headers=headers,
            content=request.read(),
        )
        return httpx.Response(response.status_code, headers=response.headers, content=response.content)


def wire(app: FastAPI, targets: dict[str, FastAPI]) -> None:
    """Point ``app``'s service clients (``app.state.clients``) at in-process apps."""
    for name, target in targets.items():
        client = app.state.clients.get(name)
        if client is not None:
            client.set_transport(InProcessTransport(target))
