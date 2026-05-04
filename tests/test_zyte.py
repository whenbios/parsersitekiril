import httpx

from app.zyte import HttpZyteClient


def test_zyte_client_uses_direct_http_when_api_key_missing():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        return httpx.Response(200, text="<html>ok</html>")

    client = HttpZyteClient(http_client=httpx.Client(transport=httpx.MockTransport(handler)))

    response = client.fetch("https://example.com")

    assert response == "<html>ok</html>"
    assert captured["method"] == "GET"
    assert captured["url"] == "https://example.com"


def test_zyte_client_calls_zyte_api_when_api_key_is_configured():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["json"] = request.read().decode("utf-8")
        return httpx.Response(200, json={"browserHtml": "<html>zyte</html>"})

    client = HttpZyteClient(
        api_key="secret",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    response = client.fetch("https://example.com/contact", browser=True)

    assert response == "<html>zyte</html>"
    assert captured["method"] == "POST"
    assert captured["url"] == "https://api.zyte.com/v1/extract"
    assert '"url":"https://example.com/contact"' in captured["json"]
    assert '"browserHtml":true' in captured["json"]
