from __future__ import annotations

import base64
from typing import Protocol

import httpx


class ZyteClientProtocol(Protocol):
    def fetch(self, url: str, browser: bool = False) -> str: ...


class HttpZyteClient:
    def __init__(
        self,
        *,
        timeout: float = 20.0,
        api_key: str | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.timeout = timeout
        self.api_key = api_key
        self.http_client = http_client or httpx.Client(timeout=timeout, follow_redirects=True)

    def fetch(self, url: str, browser: bool = False) -> str:
        if self.api_key:
            return self._fetch_via_zyte(url, browser=browser)
        response = self.http_client.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; WorkuaContactEnrichment/0.1)"},
        )
        response.raise_for_status()
        return response.text

    def _fetch_via_zyte(self, url: str, *, browser: bool) -> str:
        payload = {
            "url": url,
            "httpResponseBody": not browser,
            "browserHtml": browser,
        }
        auth_value = base64.b64encode(f"{self.api_key}:".encode("utf-8")).decode("ascii")
        response = self.http_client.post(
            "https://api.zyte.com/v1/extract",
            headers={
                "Authorization": f"Basic {auth_value}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        response.raise_for_status()
        data = response.json()
        if browser and "browserHtml" in data:
            return data["browserHtml"]
        if "httpResponseBody" in data:
            encoded = data["httpResponseBody"]
            return base64.b64decode(encoded).decode("utf-8", errors="replace")
        if "browserHtml" in data:
            return data["browserHtml"]
        raise ValueError("Unexpected Zyte API response")
