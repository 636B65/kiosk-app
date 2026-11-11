"""Synchronous HTTP client for calls between services."""

from typing import Any

import httpx

from kiosk_common.internal import INTERNAL_HEADER


class UpstreamError(Exception):
    """Another service answered with an error (or did not answer at all).

    4xx answers are passed through to the caller unchanged (same status and
    detail), so e.g. a wrong PIN reported by the customer service reaches the
    kiosk exactly as before. Unreachable services and 5xx become a 502.
    """

    def __init__(self, service: str, status: int, detail: Any, unreachable: bool = False):
        super().__init__(f"{service}: {status} {detail}")
        self.service = service
        self.status = status
        self.detail = detail
        self.unreachable = unreachable


class ServiceClient:
    def __init__(
        self,
        name: str,
        base_url: str,
        internal_token: str,
        timeout: float = 5.0,
        transport: httpx.BaseTransport | None = None,
    ):
        self.name = name
        self.base_url = base_url
        self.internal_token = internal_token
        self.timeout = timeout
        self._client = self._build(transport)

    def _build(self, transport: httpx.BaseTransport | None) -> httpx.Client:
        return httpx.Client(
            base_url=self.base_url,
            timeout=self.timeout,
            transport=transport,
            headers={INTERNAL_HEADER: self.internal_token},
        )

    def set_transport(self, transport: httpx.BaseTransport | None) -> None:
        """Tests route calls to an in-process app instead of the network."""
        self._client.close()
        self._client = self._build(transport)

    def request(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        params: dict | None = None,
        headers: dict | None = None,
    ) -> Any:
        try:
            response = self._client.request(method, path, json=json, params=params, headers=headers)
        except httpx.HTTPError as exc:
            raise UpstreamError(self.name, 503, f"{self.name} unavailable", unreachable=True) from exc
        if response.status_code >= 400:
            try:
                detail = response.json().get("detail")
            except (ValueError, AttributeError):
                detail = response.text
            raise UpstreamError(self.name, response.status_code, detail)
        if response.status_code == 204 or not response.content:
            return None
        return response.json()

    def get(self, path: str, params: dict | None = None, headers: dict | None = None) -> Any:
        return self.request("GET", path, params=params, headers=headers)

    def post(self, path: str, json: Any = None, params: dict | None = None, headers: dict | None = None) -> Any:
        return self.request("POST", path, json=json, params=params, headers=headers)

    def patch(self, path: str, json: Any = None, params: dict | None = None) -> Any:
        return self.request("PATCH", path, json=json, params=params)

    def delete(self, path: str, params: dict | None = None) -> Any:
        return self.request("DELETE", path, params=params)

    def close(self) -> None:
        self._client.close()
