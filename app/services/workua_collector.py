from __future__ import annotations

import threading
from urllib.parse import urlparse

from app.action_log import log_action
from app.schemas import CollectedVacancy, JobItemRequest
from app.services.workua import extract_workua_listing_page
from app.storage import JobStore
from app.zyte import ZyteClientProtocol


class WorkuaCollectorService:
    def __init__(self, *, zyte_client: ZyteClientProtocol, store: JobStore) -> None:
        self.zyte_client = zyte_client
        self.store = store

    def start_job(self, filter_url: str) -> int:
        job_id = self.store.create_collector_job(filter_url=filter_url)
        self._safe_log("collector_job_started", job_id=job_id, filter_url=filter_url)
        worker = threading.Thread(target=self._run_job, args=(job_id, filter_url), daemon=True)
        worker.start()
        return job_id

    def start_enrichment(self, collector_job_id: int) -> list[JobItemRequest]:
        items = self.store.get_collector_job_results(collector_job_id)
        if items is None:
            raise ValueError("Collector job not found")
        self._safe_log("collector_enrichment_started", collector_job_id=collector_job_id, total_items=len(items))
        return [
            JobItemRequest(
                row_index=item.row_index,
                company_name=item.company_name,
                workua_url=item.workua_url,
            )
            for item in items
        ]

    def _run_job(self, job_id: int, filter_url: str) -> None:
        self.store.update_collector_job(job_id, status="processing")
        current_url: str | None = filter_url
        seen_pages: set[str] = set()
        seen_vacancies: set[str] = set()
        page_number = 1
        total_pages = 1
        results: list[CollectedVacancy] = []
        try:
            while current_url and current_url not in seen_pages:
                seen_pages.add(current_url)
                html = self.zyte_client.fetch(current_url, browser=False)
                page_items, next_url, detected_total_pages = extract_workua_listing_page(
                    html,
                    current_url,
                    page_number=page_number,
                )
                total_pages = max(total_pages, detected_total_pages)
                for item in page_items:
                    if item.workua_url in seen_vacancies:
                        continue
                    seen_vacancies.add(item.workua_url)
                    item.row_index = len(results) + 2
                    item.company_name = self._normalize_company_name(item)
                    results.append(item)
                    self.store.save_collector_result(job_id, item)
                self.store.update_collector_job(
                    job_id,
                    status="processing",
                    total_pages=total_pages,
                    processed_pages=page_number,
                    found_items=len(results),
                )
                current_url = next_url
                page_number += 1
            self.store.update_collector_job(
                job_id,
                status="completed",
                total_pages=max(total_pages, len(seen_pages)),
                processed_pages=len(seen_pages),
                found_items=len(results),
                error="",
            )
            self._safe_log(
                "collector_job_completed",
                job_id=job_id,
                filter_url=filter_url,
                processed_pages=len(seen_pages),
                found_items=len(results),
            )
        except Exception as exc:
            self.store.update_collector_job(
                job_id,
                status="failed",
                total_pages=max(total_pages, len(seen_pages)),
                processed_pages=len(seen_pages),
                found_items=len(results),
                error=str(exc),
            )
            self._safe_log(
                "collector_job_failed",
                job_id=job_id,
                filter_url=filter_url,
                processed_pages=len(seen_pages),
                found_items=len(results),
                error=str(exc),
            )

    def _normalize_company_name(self, item: CollectedVacancy) -> str:
        name = " ".join(item.company_name.split())
        if name and not name.lower().startswith("vacancy "):
            return name
        parsed = urlparse(item.workua_url)
        return parsed.path.rstrip("/").split("/")[-1] or f"Vacancy {item.row_index - 1}"

    def _safe_log(self, action: str, **payload: object) -> None:
        try:
            log_action(action, **payload)
        except OSError:
            pass
        except PermissionError:
            pass
