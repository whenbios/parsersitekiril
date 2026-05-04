from datetime import datetime, timezone
import os
import threading
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from urllib.parse import urljoin, urlparse

from app.schemas import EnrichedRow, JobItemRequest
from app.services.contacts import ContactSet, discover_relevant_pages, extract_contacts, flatten_contacts_for_sheet, normalize_url
from app.services.presentation import summarize_contacts
from app.services.workua import extract_workua_company_details
from app.storage import JobStore
from app.zyte import ZyteClientProtocol

DEFAULT_SITE_PATHS = (
    "/contacts",
    "/contact",
    "/about",
    "/jobs",
    "/vacancies",
    "/career",
)


class EnrichmentService:
    def __init__(self, *, zyte_client: ZyteClientProtocol, store: JobStore) -> None:
        self.zyte_client = zyte_client
        self.store = store
        self.max_concurrency = int(os.getenv("JOB_CONCURRENCY", "4"))
        self.company_timeout_seconds = float(os.getenv("JOB_COMPANY_TIMEOUT_SECONDS", "90"))

    def enrich_company(
        self,
        *,
        company_name: str,
        workua_url: str,
        row_index: int | None = None,
    ) -> EnrichedRow:
        website, workua_contacts = self._resolve_workua_details(workua_url)
        site_contacts = self._collect_site_contacts(website) if website else ContactSet()
        status, error = self._resolve_status_and_error(website, site_contacts, workua_contacts)
        return self._build_enriched_row(
            company_name=company_name,
            workua_url=workua_url,
            row_index=row_index,
            website=website,
            site_contacts=site_contacts,
            workua_contacts=workua_contacts,
            status=status,
            error=error,
        )

    def _resolve_workua_details(self, workua_url: str) -> tuple[str, ContactSet]:
        workua_html = self.zyte_client.fetch(workua_url, browser=False)
        details = extract_workua_company_details(workua_html, workua_url)
        workua_contacts = ContactSet()
        workua_contacts.merge(details.contacts)
        self._remove_workua_noise(workua_contacts)
        return details.website or "", workua_contacts

    def _collect_site_contacts(self, website: str) -> ContactSet:
        site_contacts = ContactSet()
        home_html = self._fetch_with_fallback(website)
        site_contacts.merge(extract_contacts(home_html, website))
        contact_pages, about_pages, extra_pages = self._build_candidate_pages(home_html, website)
        self._crawl_stage_pages(site_contacts, contact_pages)
        if not self._has_useful_contacts(site_contacts):
            self._crawl_stage_pages(site_contacts, about_pages)
        if not self._has_useful_contacts(site_contacts):
            self._crawl_stage_pages(site_contacts, extra_pages)
        return site_contacts

    def _resolve_status_and_error(
        self,
        website: str,
        site_contacts: ContactSet,
        workua_contacts: ContactSet,
    ) -> tuple[str, str]:
        if website and (site_contacts.emails or site_contacts.telegrams or site_contacts.phones or site_contacts.whatsapp):
            return "done", ""
        if website:
            return "partial", ""
        if self._has_useful_contacts(workua_contacts):
            return "partial", ""
        return "failed", "Official website not found on Work.ua page"

    def _build_enriched_row(
        self,
        *,
        company_name: str,
        workua_url: str,
        row_index: int | None,
        website: str,
        site_contacts: ContactSet,
        workua_contacts: ContactSet,
        status: str,
        error: str,
    ) -> EnrichedRow:
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        payload = flatten_contacts_for_sheet(
            contacts=site_contacts,
            website=website,
            status=status,
            error=error,
            last_checked=now,
            company_name=company_name,
            workua_url=workua_url,
            row_index=row_index,
        )
        summary = summarize_contacts(site_contacts=site_contacts, workua_contacts=workua_contacts)
        payload.update(
            {
                "email_outreach": summary.email_outreach,
                "email_secondary": summary.email_secondary,
                "phone_direct": summary.phone_direct,
                "phone_public": summary.phone_public,
                "best_channel": summary.best_channel,
                "best_contact": summary.best_contact,
                "backup_contact": summary.backup_contact,
                "workua_fallback": summary.workua_fallback,
                "workua_email": summary.workua_email,
                "workua_telegram": summary.workua_telegram,
                "workua_phone": summary.workua_phone,
                "notes": summary.notes,
            }
        )
        return EnrichedRow.model_validate(payload)

    def _fetch_with_fallback(self, url: str, *, prefer_browser: bool = False) -> str:
        if prefer_browser:
            try:
                return self.zyte_client.fetch(url, browser=True)
            except Exception:
                return self.zyte_client.fetch(url, browser=False)
        try:
            return self.zyte_client.fetch(url, browser=False)
        except Exception:
            return self.zyte_client.fetch(url, browser=True)

    def _build_candidate_pages(self, home_html: str, website: str) -> tuple[list[str], list[str], list[str]]:
        candidates: list[str] = []
        for discovered in discover_relevant_pages(home_html, website):
            if discovered not in candidates:
                candidates.append(discovered)
        for path in DEFAULT_SITE_PATHS:
            seeded = normalize_url(urljoin(website.rstrip("/") + "/", path.lstrip("/")))
            if seeded not in candidates and seeded != normalize_url(website):
                candidates.append(seeded)
        contact_pages: list[str] = []
        about_pages: list[str] = []
        extra_pages: list[str] = []
        for candidate in candidates:
            lower = candidate.lower()
            if "/contact" in lower or "/contacts" in lower:
                contact_pages.append(candidate)
            elif "/about" in lower:
                about_pages.append(candidate)
            else:
                extra_pages.append(candidate)
        return contact_pages[:4], about_pages[:2], extra_pages[:4]

    def _should_prefer_browser(self, url: str) -> bool:
        lower_url = url.lower()
        return "/contact" in lower_url or "/contacts" in lower_url

    def _crawl_stage_pages(self, contacts: ContactSet, pages: list[str]) -> None:
        for page_url in pages:
            try:
                page_html = self._fetch_with_fallback(
                    page_url,
                    prefer_browser=self._should_prefer_browser(page_url),
                )
            except Exception:
                continue
            contacts.merge(extract_contacts(page_html, page_url))

    def _has_useful_contacts(self, contacts: ContactSet) -> bool:
        return any(
            (
                contacts.general_email,
                contacts.marketing_email,
                contacts.manager_email,
                contacts.telegrams,
                contacts.whatsapp,
                contacts.viber,
                contacts.main_phone,
                contacts.phones,
            )
        )

    def _remove_workua_noise(self, contacts: ContactSet) -> None:
        def is_workua_url(value: str | None) -> bool:
            if not value:
                return False
            lowered = value.lower()
            host = urlparse(value).netloc.lower()
            return (
                host.endswith("work.ua")
                or "work.ua" in host
                or "work.ua" in lowered
                or "facebook.com/dialog/share" in lowered
                or "facebook.com/sharer" in lowered
                or "linkedin.com/company/work-ua" in lowered
            )

        if is_workua_url(contacts.instagram):
            contacts.instagram = None
        if is_workua_url(contacts.facebook):
            contacts.facebook = None
        if is_workua_url(contacts.linkedin):
            contacts.linkedin = None
        contacts.other_links = [link for link in contacts.other_links if not is_workua_url(link)]

    def start_job(self, items: list[JobItemRequest]) -> int:
        job_id = self.store.create_job(total_items=len(items))
        for item in items:
            self.store.add_job_item(job_id, item.row_index, item.company_name, item.workua_url, "queued")
        worker = threading.Thread(target=self._run_job, args=(job_id, items), daemon=True)
        worker.start()
        return job_id

    def _run_job(self, job_id: int, items: list[JobItemRequest]) -> None:
        self.store.set_job_status(job_id, "processing")
        groups = self._group_items_by_company(items)
        results_by_row: dict[int, EnrichedRow] = {}
        domain_cache: dict[str, ContactSet] = {}
        domain_cache_lock = threading.Lock()
        executor = ThreadPoolExecutor(max_workers=max(1, self.max_concurrency))
        try:
            pending = {
                executor.submit(
                    self._process_company_group_with_tracker,
                    tracker,
                    job_id,
                    group_items,
                    domain_cache,
                    domain_cache_lock,
                ): {
                    "group_items": group_items,
                    "tracker": tracker,
                }
                for group_items in groups
                for tracker in [{"started_at": None}]
            }
            while pending:
                done_futures, _ = wait(pending.keys(), timeout=0.5, return_when=FIRST_COMPLETED)
                for future in done_futures:
                    metadata = pending.pop(future)
                    try:
                        group_results = future.result()
                    except Exception as exc:
                        group_results = self._build_group_timeout_results(
                            metadata["group_items"],
                            error=str(exc) or "Company processing failed",
                        )
                    for item, result in group_results:
                        results_by_row[item.row_index] = result
                        self.store.save_job_result(job_id, result)
                        self.store.update_job_item_status(job_id, item.row_index, result.status)

                now = datetime.now(timezone.utc)
                timed_out = [
                    future
                    for future, metadata in pending.items()
                    if metadata["tracker"]["started_at"] is not None
                    and (now - metadata["tracker"]["started_at"]).total_seconds() >= self.company_timeout_seconds
                ]
                for future in timed_out:
                    metadata = pending.pop(future)
                    future.cancel()
                    group_results = self._build_group_timeout_results(
                        metadata["group_items"],
                        error=f"Company processing timed out after {int(self.company_timeout_seconds)}s",
                    )
                    for item, result in group_results:
                        results_by_row[item.row_index] = result
                        self.store.save_job_result(job_id, result)
                        self.store.update_job_item_status(job_id, item.row_index, result.status)
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

        failed_items = sum(1 for result in results_by_row.values() if result.status == "failed")
        done_items = sum(1 for result in results_by_row.values() if result.status != "failed")
        final_status = "failed" if failed_items == len(items) and items else "completed"
        self.store.finalize_job(job_id, final_status, done_items, failed_items)

    def _group_items_by_company(self, items: list[JobItemRequest]) -> list[list[JobItemRequest]]:
        groups: dict[str, list[JobItemRequest]] = {}
        for item in items:
            groups.setdefault(self._company_key(item.company_name), []).append(item)
        return list(groups.values())

    def _process_company_group(
        self,
        job_id: int,
        group_items: list[JobItemRequest],
        domain_cache: dict[str, ContactSet],
        domain_cache_lock: threading.Lock,
    ) -> list[tuple[JobItemRequest, EnrichedRow]]:
        row_indices = [item.row_index for item in group_items]
        self.store.update_job_items_status(job_id, row_indices, "processing")

        best_result: EnrichedRow | None = None
        for item in group_items:
            if best_result and self._has_useful_row(best_result):
                break
            try:
                website, workua_contacts = self._resolve_workua_details(item.workua_url)
                site_contacts = ContactSet()
                domain_key = self._website_key(website)
                if domain_key:
                    with domain_cache_lock:
                        cached_contacts = domain_cache.get(domain_key)
                    if cached_contacts is not None:
                        site_contacts = self._clone_contact_set(cached_contacts)
                    else:
                        site_contacts = self._collect_site_contacts(website)
                        with domain_cache_lock:
                            domain_cache.setdefault(domain_key, self._clone_contact_set(site_contacts))
                status, error = self._resolve_status_and_error(website, site_contacts, workua_contacts)
                result = self._build_enriched_row(
                    company_name=item.company_name,
                    workua_url=item.workua_url,
                    row_index=item.row_index,
                    website=website,
                    site_contacts=site_contacts,
                    workua_contacts=workua_contacts,
                    status=status,
                    error=error,
                )
            except Exception as exc:
                result = self._build_enriched_row(
                    company_name=item.company_name,
                    workua_url=item.workua_url,
                    row_index=item.row_index,
                    website="",
                    site_contacts=ContactSet(),
                    workua_contacts=ContactSet(),
                    status="failed",
                    error=str(exc),
                )
            if not best_result or self._result_score(result) > self._result_score(best_result):
                best_result = result

        if best_result is None:
            best_result = EnrichedRow(
                row_index=group_items[0].row_index,
                company_name=group_items[0].company_name,
                workua_url=group_items[0].workua_url,
                status="failed",
                error="No result produced",
            )

        return [
            (item, self._clone_result_for_item(best_result, item))
            for item in group_items
        ]

    def _process_company_group_with_tracker(
        self,
        tracker: dict[str, datetime | None],
        job_id: int,
        group_items: list[JobItemRequest],
        domain_cache: dict[str, ContactSet],
        domain_cache_lock: threading.Lock,
    ) -> list[tuple[JobItemRequest, EnrichedRow]]:
        tracker["started_at"] = datetime.now(timezone.utc)
        return self._process_company_group(job_id, group_items, domain_cache, domain_cache_lock)

    def _build_group_timeout_results(
        self,
        group_items: list[JobItemRequest],
        *,
        error: str,
    ) -> list[tuple[JobItemRequest, EnrichedRow]]:
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        return [
            (
                item,
                EnrichedRow(
                    row_index=item.row_index,
                    company_name=item.company_name,
                    workua_url=item.workua_url,
                    status="failed",
                    error=error,
                    last_checked=now,
                ),
            )
            for item in group_items
        ]

    def _company_key(self, company_name: str) -> str:
        return " ".join(company_name.lower().split())

    def _website_key(self, website: str) -> str:
        if not website:
            return ""
        host = urlparse(website).netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        return host

    def _clone_contact_set(self, contacts: ContactSet) -> ContactSet:
        cloned = ContactSet()
        cloned.merge(contacts)
        return cloned

    def _has_useful_row(self, result: EnrichedRow) -> bool:
        return self._result_score(result) > 0

    def _result_score(self, result: EnrichedRow) -> int:
        return sum(
            1
            for value in (
                result.general_email,
                result.marketing_email,
                result.manager_email,
                result.telegram_1,
                result.telegram_2,
                result.telegram_3,
                result.whatsapp,
                result.viber,
                result.main_phone,
                result.phone_1,
                result.phone_2,
                result.phone_3,
            )
            if value
        )

    def _clone_result_for_item(self, result: EnrichedRow, item: JobItemRequest) -> EnrichedRow:
        payload = result.model_dump()
        payload["row_index"] = item.row_index
        payload["company_name"] = item.company_name
        payload["workua_url"] = item.workua_url
        return EnrichedRow.model_validate(payload)
