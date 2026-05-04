from app.main import create_app
import time
from pathlib import Path


def wait_for_completed_job(client, job_id: int, timeout: float = 3.0) -> dict:
    deadline = time.time() + timeout
    final_status = None
    while time.time() < deadline:
        poll = client.get(f"/jobs/{job_id}/status")
        final_status = poll.json()
        if final_status["status"] == "completed":
            return final_status
        time.sleep(0.05)
    assert final_status is not None
    assert final_status["status"] == "completed"
    return final_status


def wait_for_completed_collect_job(client, job_id: int, timeout: float = 3.0) -> dict:
    deadline = time.time() + timeout
    final_status = None
    while time.time() < deadline:
        poll = client.get(f"/collectors/workua/{job_id}/status")
        final_status = poll.json()
        if final_status["status"] == "completed":
            return final_status
        time.sleep(0.05)
    assert final_status is not None
    assert final_status["status"] == "completed"
    return final_status


class FakeZyteClient:
    def fetch(self, url: str, browser: bool = False) -> str:
        pages = {
            "https://www.work.ua/jobs/by-company/1/": """
            <html><body><a href="https://acme.example.com">Official site</a></body></html>
            """,
            "https://acme.example.com": """
            <html><body>
              <a href="/contacts">Contacts</a>
              <a href="mailto:hello@acme.example.com">hello@acme.example.com</a>
            </body></html>
            """,
            "https://acme.example.com/contacts": """
            <html><body>
              <a href="mailto:sales@acme.example.com">sales@acme.example.com</a>
              <a href="https://t.me/acme_team">Telegram</a>
              <a href="tel:+380501234567">+380501234567</a>
            </body></html>
            """,
        }
        if url not in pages:
            raise AssertionError(f"unexpected url {url}")
        return pages[url]


class BrowserFallbackZyteClient:
    def __init__(self) -> None:
        self.calls = []

    def fetch(self, url: str, browser: bool = False) -> str:
        self.calls.append((url, browser))
        if url == "https://www.work.ua/jobs/by-company/1/":
            return '<html><body><a href="https://acme.example.com">Official site</a></body></html>'
        if url == "https://acme.example.com" and not browser:
            raise RuntimeError("blocked")
        if url == "https://acme.example.com" and browser:
            return """
            <html><body>
              <a href="mailto:hello@acme.example.com">hello@acme.example.com</a>
            </body></html>
            """
        raise AssertionError(f"unexpected url {url}")


class SeedPagesZyteClient:
    def fetch(self, url: str, browser: bool = False) -> str:
        pages = {
            "https://www.work.ua/jobs/by-company/2/": """
            <html><body><a href="https://seed.example.com">Official site</a></body></html>
            """,
            "https://seed.example.com": """
            <html><body><p>Welcome</p></body></html>
            """,
            "https://seed.example.com/contacts": """
            <html><body>
              <a href="mailto:school@seed.example.com">school@seed.example.com</a>
              <a href="mailto:marketing@seed.example.com">marketing@seed.example.com</a>
              <h2>Зв'язатися з керівником</h2>
              <a href="mailto:boss@gmail.com">boss@gmail.com</a>
              <a href="https://api.whatsapp.com/send?phone=380969465392">WhatsApp</a>
            </body></html>
            """,
        }
        if url in pages:
            return pages[url]
        raise AssertionError(f"unexpected url {url}")


class BrowserContactPagesZyteClient:
    def __init__(self) -> None:
        self.calls = []

    def fetch(self, url: str, browser: bool = False) -> str:
        self.calls.append((url, browser))
        pages = {
            ("https://www.work.ua/jobs/by-company/3/", False): """
            <html><body><a href="https://browser.example.com">Official site</a></body></html>
            """,
            ("https://browser.example.com", False): """
            <html><body><p>Home</p></body></html>
            """,
            ("https://browser.example.com/contacts", False): """
            <html><body><p>Rendered content hidden without browser mode</p></body></html>
            """,
            ("https://browser.example.com/contacts", True): """
            <html><body>
              <a href="mailto:school@browser.example.com">school@browser.example.com</a>
            </body></html>
            """,
        }
        key = (url, browser)
        if key in pages:
            return pages[key]
        raise AssertionError(f"unexpected url/browser combination {key}")


def test_companies_enrich_returns_flattened_contact_fields():
    from fastapi.testclient import TestClient

    app = create_app(zyte_client=FakeZyteClient())
    client = TestClient(app)

    response = client.post(
        "/companies/enrich",
        json={
            "company_name": "Acme",
            "workua_url": "https://www.work.ua/jobs/by-company/1/",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["website"] == "https://acme.example.com"
    assert data["email_1"] == "hello@acme.example.com"
    assert data["email_2"] == "sales@acme.example.com"
    assert data["general_email"] == "hello@acme.example.com"
    assert data["telegram_1"] == "https://t.me/acme_team"
    assert data["phone_1"] == "+380501234567"
    assert data["status"] == "done"


def test_jobs_flow_starts_tracks_status_and_returns_results():
    from fastapi.testclient import TestClient

    app = create_app(zyte_client=FakeZyteClient())
    client = TestClient(app)

    start_response = client.post(
        "/jobs/start",
        json={
            "items": [
                {
                    "row_index": 2,
                    "company_name": "Acme",
                    "workua_url": "https://www.work.ua/jobs/by-company/1/",
                }
            ]
        },
    )

    assert start_response.status_code == 200
    job_id = start_response.json()["job_id"]

    final_status = wait_for_completed_job(client, job_id)
    assert final_status["done_items"] == 1

    results_response = client.get(f"/jobs/{job_id}/results")
    assert results_response.status_code == 200
    results = results_response.json()["items"]
    assert len(results) == 1
    assert results[0]["row_index"] == 2
    assert results[0]["website"] == "https://acme.example.com"
    assert results[0]["email_1"] == "hello@acme.example.com"


def test_companies_enrich_falls_back_to_browser_fetch_for_company_site():
    from fastapi.testclient import TestClient

    zyte_client = BrowserFallbackZyteClient()
    app = create_app(zyte_client=zyte_client)
    client = TestClient(app)

    response = client.post(
        "/companies/enrich",
        json={
            "company_name": "Acme",
            "workua_url": "https://www.work.ua/jobs/by-company/1/",
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "done"
    assert response.json()["email_1"] == "hello@acme.example.com"
    assert ("https://acme.example.com", True) in zyte_client.calls


def test_companies_enrich_visits_seed_contact_pages_even_when_homepage_has_no_links():
    from fastapi.testclient import TestClient

    app = create_app(zyte_client=SeedPagesZyteClient())
    client = TestClient(app)

    response = client.post(
        "/companies/enrich",
        json={
            "company_name": "Seed",
            "workua_url": "https://www.work.ua/jobs/by-company/2/",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["website"] == "https://seed.example.com"
    assert data["general_email"] == "school@seed.example.com"
    assert data["marketing_email"] == "marketing@seed.example.com"
    assert data["manager_email"] == "boss@gmail.com"
    assert data["whatsapp"] == "https://api.whatsapp.com/send?phone=380969465392"


def test_companies_enrich_uses_browser_rendering_for_contact_pages():
    from fastapi.testclient import TestClient

    zyte_client = BrowserContactPagesZyteClient()
    app = create_app(zyte_client=zyte_client)
    client = TestClient(app)

    response = client.post(
        "/companies/enrich",
        json={
            "company_name": "Browser",
            "workua_url": "https://www.work.ua/jobs/by-company/3/",
        },
    )

    assert response.status_code == 200
    assert response.json()["general_email"] == "school@browser.example.com"
    assert ("https://browser.example.com/contacts", True) in zyte_client.calls


class WorkuaNoiseZyteClient:
    def fetch(self, url: str, browser: bool = False) -> str:
        pages = {
            "https://www.work.ua/jobs/by-company/4/": """
            <html><body>
              <a href="https://clean.example.com">Official site</a>
              <a href="https://www.instagram.com/work.ua">Instagram</a>
              <a href="https://www.linkedin.com/company/work-ua">LinkedIn</a>
              <a href="https://www.facebook.com/dialog/share?app_id=1">Facebook share</a>
            </body></html>
            """,
            "https://clean.example.com": """
            <html><body>
              <a href="/contacts">Contacts</a>
            </body></html>
            """,
            "https://clean.example.com/contacts": """
            <html><body>
              <h2>Зв'язатися з керівником</h2>
              <p>Пиши особисто</p>
              <a href="mailto:nmt.sweet.dreams@gmail.com">nmt.sweet.dreams@gmail.com</a>
            </body></html>
            """,
        }
        if url in pages:
            return pages[url]
        raise AssertionError(f"unexpected url {url}")


def test_companies_enrich_filters_workua_social_noise_and_sets_manager_email():
    from fastapi.testclient import TestClient

    app = create_app(zyte_client=WorkuaNoiseZyteClient())
    client = TestClient(app)

    response = client.post(
        "/companies/enrich",
        json={
            "company_name": "Clean",
            "workua_url": "https://www.work.ua/jobs/by-company/4/",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["manager_email"] == "nmt.sweet.dreams@gmail.com"
    assert data["instagram"] == ""
    assert data["facebook"] == ""
    assert data["linkedin"] == ""


class StagedCrawlZyteClient:
    def __init__(self) -> None:
        self.calls = []

    def fetch(self, url: str, browser: bool = False) -> str:
        self.calls.append((url, browser))
        pages = {
            ("https://www.work.ua/jobs/by-company/5/", False): """
            <html><body><a href="https://staged.example.com">Official site</a></body></html>
            """,
            ("https://staged.example.com", False): """
            <html><body><a href="/contacts">Contacts</a><a href="/about">About</a></body></html>
            """,
            ("https://staged.example.com/contacts", True): """
            <html><body><a href="mailto:contact@staged.example.com">contact@staged.example.com</a></body></html>
            """,
            ("https://staged.example.com/about", False): """
            <html><body><a href="mailto:about@staged.example.com">about@staged.example.com</a></body></html>
            """,
            ("https://staged.example.com/jobs", False): """
            <html><body><a href="mailto:jobs@staged.example.com">jobs@staged.example.com</a></body></html>
            """,
        }
        key = (url, browser)
        if key in pages:
            return pages[key]
        raise AssertionError(f"unexpected url/browser combination {key}")


class DuplicateCompanyZyteClient:
    def __init__(self) -> None:
        self.calls = []

    def fetch(self, url: str, browser: bool = False) -> str:
        self.calls.append((url, browser))
        pages = {
            ("https://www.work.ua/jobs/by-company/dup-1/", False): """
            <html><body><p>No official site here</p></body></html>
            """,
            ("https://www.work.ua/jobs/by-company/dup-2/", False): """
            <html><body><a href="https://dup.example.com">Official site</a></body></html>
            """,
            ("https://dup.example.com", False): """
            <html><body><p>Home without useful contacts</p></body></html>
            """,
            ("https://dup.example.com/contacts", True): """
            <html><body><p>No contacts here</p></body></html>
            """,
            ("https://dup.example.com/about", False): """
            <html><body><a href="mailto:team@dup.example.com">team@dup.example.com</a></body></html>
            """,
        }
        key = (url, browser)
        if key in pages:
            return pages[key]
        raise AssertionError(f"unexpected url/browser combination {key}")


class SlowZyteClient:
    def fetch(self, url: str, browser: bool = False) -> str:
        time.sleep(0.05)
        pages = {
            "https://www.work.ua/jobs/by-company/slow-1/": """
            <html><body><a href="https://slow-one.example.com">Official site</a></body></html>
            """,
            "https://slow-one.example.com": """
            <html><body><a href="mailto:one@slow.example.com">one@slow.example.com</a></body></html>
            """,
            "https://www.work.ua/jobs/by-company/slow-2/": """
            <html><body><a href="https://slow-two.example.com">Official site</a></body></html>
            """,
            "https://slow-two.example.com": """
            <html><body><a href="mailto:two@slow.example.com">two@slow.example.com</a></body></html>
            """,
        }
        if url in pages:
            return pages[url]
        raise AssertionError(f"unexpected url {url}")


class DomainDuplicateZyteClient:
    def __init__(self) -> None:
        self.calls = []

    def fetch(self, url: str, browser: bool = False) -> str:
        self.calls.append((url, browser))
        pages = {
            ("https://www.work.ua/jobs/by-company/domain-1/", False): """
            <html><body><a href="https://same.example.com">Official site</a></body></html>
            """,
            ("https://www.work.ua/jobs/by-company/domain-2/", False): """
            <html><body><a href="https://www.same.example.com">Official site</a></body></html>
            """,
            ("https://same.example.com", False): """
            <html><body><a href="/contacts">Contacts</a></body></html>
            """,
            ("https://same.example.com/contacts", True): """
            <html><body><a href="mailto:team@same.example.com">team@same.example.com</a></body></html>
            """,
        }
        key = (url, browser)
        if key in pages:
            return pages[key]
        raise AssertionError(f"unexpected url/browser combination {key}")


class WorkuaFilterZyteClient:
    def fetch(self, url: str, browser: bool = False) -> str:
        pages = {
            "https://www.work.ua/jobs-python/": """
            <html><body>
              <a href="/jobs/1111111/">Acme vacancy</a>
              <a href="/jobs/2222222/">Beta vacancy</a>
              <nav><a rel="next" href="/jobs-python/?page=2">Next</a></nav>
            </body></html>
            """,
            "https://www.work.ua/jobs-python/?page=2": """
            <html><body>
              <a href="/jobs/2222222/">Beta vacancy duplicate</a>
              <a href="/jobs/3333333/">Gamma vacancy</a>
            </body></html>
            """,
            "https://www.work.ua/jobs/1111111/": """
            <html><body><a href="https://acme.example.com">Official site</a></body></html>
            """,
            "https://acme.example.com": """
            <html><body><a href="mailto:hello@acme.example.com">hello@acme.example.com</a></body></html>
            """,
            "https://www.work.ua/jobs/2222222/": """
            <html><body><a href="https://beta.example.com">Official site</a></body></html>
            """,
            "https://beta.example.com": """
            <html><body><a href="mailto:team@beta.example.com">team@beta.example.com</a></body></html>
            """,
            "https://www.work.ua/jobs/3333333/": """
            <html><body><a href="https://gamma.example.com">Official site</a></body></html>
            """,
            "https://gamma.example.com": """
            <html><body><a href="mailto:contact@gamma.example.com">contact@gamma.example.com</a></body></html>
            """,
        }
        if url in pages:
            return pages[url]
        raise AssertionError(f"unexpected url {url}")


def test_companies_enrich_stops_after_contact_stage_when_useful_contacts_found():
    from fastapi.testclient import TestClient

    zyte_client = StagedCrawlZyteClient()
    app = create_app(zyte_client=zyte_client)
    client = TestClient(app)

    response = client.post(
        "/companies/enrich",
        json={
            "company_name": "Staged",
            "workua_url": "https://www.work.ua/jobs/by-company/5/",
        },
    )

    assert response.status_code == 200
    assert response.json()["general_email"] == "contact@staged.example.com"
    assert ("https://staged.example.com/contacts", True) in zyte_client.calls
    assert ("https://staged.example.com/about", False) not in zyte_client.calls
    assert ("https://staged.example.com/jobs", False) not in zyte_client.calls


def test_jobs_flow_reuses_better_duplicate_company_result_without_rescanning_later_duplicates():
    from fastapi.testclient import TestClient

    zyte_client = DuplicateCompanyZyteClient()
    app = create_app(zyte_client=zyte_client)
    client = TestClient(app)

    start_response = client.post(
        "/jobs/start",
        json={
            "items": [
                {
                    "row_index": 2,
                    "company_name": "Dup Co",
                    "workua_url": "https://www.work.ua/jobs/by-company/dup-1/",
                },
                {
                    "row_index": 3,
                    "company_name": "Dup Co",
                    "workua_url": "https://www.work.ua/jobs/by-company/dup-2/",
                },
                {
                    "row_index": 4,
                    "company_name": "Dup Co",
                    "workua_url": "https://www.work.ua/jobs/by-company/dup-2/",
                },
            ]
        },
    )

    assert start_response.status_code == 200
    job_id = start_response.json()["job_id"]
    wait_for_completed_job(client, job_id)

    results_response = client.get(f"/jobs/{job_id}/results")
    assert results_response.status_code == 200
    items = results_response.json()["items"]
    assert len(items) == 3
    assert items[0]["general_email"] == "team@dup.example.com"
    assert items[1]["general_email"] == "team@dup.example.com"
    assert items[2]["general_email"] == "team@dup.example.com"
    assert sum(1 for url, _ in zyte_client.calls if url == "https://www.work.ua/jobs/by-company/dup-2/") == 1


def test_jobs_flow_reuses_same_site_for_different_company_names():
    from fastapi.testclient import TestClient

    zyte_client = DomainDuplicateZyteClient()
    app = create_app(zyte_client=zyte_client)
    client = TestClient(app)

    start_response = client.post(
        "/jobs/start",
        json={
            "items": [
                {
                    "row_index": 2,
                    "company_name": "Brand One",
                    "workua_url": "https://www.work.ua/jobs/by-company/domain-1/",
                },
                {
                    "row_index": 3,
                    "company_name": "Brand Two",
                    "workua_url": "https://www.work.ua/jobs/by-company/domain-2/",
                },
            ]
        },
    )

    assert start_response.status_code == 200
    job_id = start_response.json()["job_id"]
    wait_for_completed_job(client, job_id)

    results_response = client.get(f"/jobs/{job_id}/results")
    items = results_response.json()["items"]
    assert len(items) == 2
    assert items[0]["general_email"] == "team@same.example.com"
    assert items[1]["general_email"] == "team@same.example.com"
    assert sum(1 for url, _ in zyte_client.calls if url == "https://same.example.com") == 1


def test_jobs_flow_runs_in_background_and_reports_progress():
    from fastapi.testclient import TestClient

    app = create_app(zyte_client=SlowZyteClient())
    client = TestClient(app)

    start_response = client.post(
        "/jobs/start",
        json={
            "items": [
                {
                    "row_index": 2,
                    "company_name": "Slow One",
                    "workua_url": "https://www.work.ua/jobs/by-company/slow-1/",
                },
                {
                    "row_index": 3,
                    "company_name": "Slow Two",
                    "workua_url": "https://www.work.ua/jobs/by-company/slow-2/",
                },
            ]
        },
    )

    assert start_response.status_code == 200
    job_id = start_response.json()["job_id"]

    status_response = client.get(f"/jobs/{job_id}/status")
    assert status_response.status_code == 200
    assert status_response.json()["total_items"] == 2
    assert status_response.json()["status"] in {"queued", "processing", "completed"}

    final_status = wait_for_completed_job(client, job_id)
    assert final_status["done_items"] == 2


def test_job_exports_return_csv_and_xlsx():
    from fastapi.testclient import TestClient

    app = create_app(zyte_client=FakeZyteClient())
    client = TestClient(app)

    start_response = client.post(
        "/jobs/start",
        json={
            "items": [
                {
                    "row_index": 2,
                    "company_name": "Acme",
                    "workua_url": "https://www.work.ua/jobs/by-company/1/",
                }
            ]
        },
    )

    job_id = start_response.json()["job_id"]
    wait_for_completed_job(client, job_id)

    csv_response = client.get(f"/jobs/{job_id}/export.csv")
    assert csv_response.status_code == 200
    assert "company_name" in csv_response.text
    assert "Acme" in csv_response.text

    xlsx_response = client.get(f"/jobs/{job_id}/export.xlsx")
    assert xlsx_response.status_code == 200
    assert xlsx_response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert len(xlsx_response.content) > 100


def test_collectors_workua_collects_unique_vacancy_links_and_exports():
    from fastapi.testclient import TestClient

    app = create_app(zyte_client=WorkuaFilterZyteClient())
    client = TestClient(app)

    start_response = client.post(
        "/collectors/workua/start",
        json={"filter_url": "https://www.work.ua/jobs-python/"},
    )

    assert start_response.status_code == 200
    job_id = start_response.json()["job_id"]

    final_status = wait_for_completed_collect_job(client, job_id)
    assert final_status["processed_pages"] == 2
    assert final_status["found_items"] == 3

    results_response = client.get(f"/collectors/workua/{job_id}/results")
    assert results_response.status_code == 200
    items = results_response.json()["items"]
    assert [item["workua_url"] for item in items] == [
        "https://www.work.ua/jobs/1111111/",
        "https://www.work.ua/jobs/2222222/",
        "https://www.work.ua/jobs/3333333/",
    ]

    csv_response = client.get(f"/collectors/workua/{job_id}/export.csv")
    assert csv_response.status_code == 200
    assert "workua_url" in csv_response.text
    assert "https://www.work.ua/jobs/3333333/" in csv_response.text


def test_collectors_workua_can_start_enrichment_from_collected_results():
    from fastapi.testclient import TestClient
    import os
    import time

    log_path = Path(f"data/test-actions-{int(time.time() * 1000)}.log")
    os.environ["ACTION_LOG_PATH"] = str(log_path)
    app = create_app(zyte_client=WorkuaFilterZyteClient())
    client = TestClient(app)

    collect_response = client.post(
        "/collectors/workua/start",
        json={"filter_url": "https://www.work.ua/jobs-python/"},
    )
    collect_job_id = collect_response.json()["job_id"]
    wait_for_completed_collect_job(client, collect_job_id)

    enrich_response = client.post(f"/collectors/workua/{collect_job_id}/start-enrichment")
    assert enrich_response.status_code == 200
    enrich_job_id = enrich_response.json()["job_id"]

    wait_for_completed_job(client, enrich_job_id)
    results_response = client.get(f"/jobs/{enrich_job_id}/results")
    items = results_response.json()["items"]
    assert len(items) == 3
    assert items[0]["general_email"] == "hello@acme.example.com"
    assert items[1]["general_email"] == "team@beta.example.com"
    assert items[2]["general_email"] == "contact@gamma.example.com"

    log_text = log_path.read_text(encoding="utf-8")
    assert "collector_job_started" in log_text
    assert "collector_job_completed" in log_text
    assert "collector_enrichment_started" in log_text
