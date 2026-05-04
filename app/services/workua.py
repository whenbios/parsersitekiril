import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urljoin, urlparse

from bs4 import BeautifulSoup

from app.schemas import CollectedVacancy
from app.services.contacts import ContactSet, extract_contacts, normalize_url


@dataclass
class WorkuaDetails:
    website: str | None
    contacts: ContactSet


WORKUA_JOB_PATH_RE = re.compile(r"^/jobs/\d+/?$")


def extract_workua_company_details(html: str, page_url: str) -> WorkuaDetails:
    soup = BeautifulSoup(html, "html.parser")
    contacts = extract_contacts(html, page_url)
    website: str | None = None

    company_site_link = soup.select_one(".website-company a[href]")
    if company_site_link is not None:
        href = company_site_link.get("href", "").strip()
        if href.startswith(("http://", "https://")):
            website = normalize_url(href)

    if website is None:
        website_label = soup.find(
            lambda tag: tag.name in {"span", "div", "li"}
            and "сайт" in tag.get_text(" ", strip=True).lower()
        )
        if website_label is not None:
            nearest_link = website_label.find_next("a", href=True)
            if nearest_link is not None:
                href = nearest_link.get("href", "").strip()
                if href.startswith(("http://", "https://")):
                    website = normalize_url(href)

    if website is not None:
        return WorkuaDetails(website=website, contacts=contacts)

    for anchor in soup.find_all("a", href=True):
        href = anchor["href"].strip()
        if not href.startswith(("http://", "https://")):
            continue
        parsed = urlparse(href)
        if "work.ua" in parsed.netloc.lower():
            continue
        if "facebook.com/dialog/share" in href.lower():
            continue
        if href.startswith(("mailto:", "tel:")):
            continue
        website = normalize_url(href)
        break

    return WorkuaDetails(website=website, contacts=contacts)


def extract_workua_listing_page(html: str, page_url: str, *, page_number: int) -> tuple[list[CollectedVacancy], str | None, int]:
    soup = BeautifulSoup(html, "html.parser")
    items: list[CollectedVacancy] = []
    seen_urls: set[str] = set()

    for anchor in soup.find_all("a", href=True):
        absolute_url = urljoin(page_url, anchor["href"].strip())
        parsed = urlparse(absolute_url)
        if "work.ua" not in parsed.netloc.lower():
            continue
        if not WORKUA_JOB_PATH_RE.match(parsed.path):
            continue
        normalized_url = normalize_url(absolute_url)
        if normalized_url in seen_urls:
            continue
        seen_urls.add(normalized_url)
        company_name = anchor.get_text(" ", strip=True) or f"Vacancy {len(items) + 1}"
        items.append(
            CollectedVacancy(
                row_index=len(items) + 2,
                company_name=company_name,
                workua_url=normalized_url,
                page_number=page_number,
            )
        )

    next_url = _find_next_page_url(soup, page_url, page_number)
    total_pages = _detect_total_pages(soup, page_url, page_number)
    return items, next_url, total_pages


def _find_next_page_url(soup: BeautifulSoup, page_url: str, page_number: int) -> str | None:
    next_link = soup.select_one("a[rel='next'][href]")
    if next_link is not None:
        return normalize_url(urljoin(page_url, next_link["href"].strip()))

    next_labels = {"next", "следующая", "далі", "дальше", "наступна", "вперед"}
    for anchor in soup.find_all("a", href=True):
        label = anchor.get_text(" ", strip=True).lower()
        if label in next_labels:
            return normalize_url(urljoin(page_url, anchor["href"].strip()))

        href = anchor["href"].strip()
        absolute_url = urljoin(page_url, href)
        parsed = urlparse(absolute_url)
        page_value = parse_qs(parsed.query).get("page", [None])[0]
        if page_value and page_value.isdigit() and int(page_value) == page_number + 1:
            return normalize_url(absolute_url)
    return None


def _detect_total_pages(soup: BeautifulSoup, page_url: str, page_number: int) -> int:
    pages = [page_number]
    for anchor in soup.find_all("a", href=True):
        absolute_url = urljoin(page_url, anchor["href"].strip())
        parsed = urlparse(absolute_url)
        page_value = parse_qs(parsed.query).get("page", [None])[0]
        if page_value and page_value.isdigit():
            pages.append(int(page_value))

        label = anchor.get_text(" ", strip=True)
        if label.isdigit():
            pages.append(int(label))
    return max(pages) if pages else page_number
