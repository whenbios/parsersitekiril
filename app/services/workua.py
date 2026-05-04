from dataclasses import dataclass
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from app.services.contacts import ContactSet, extract_contacts, normalize_url


@dataclass
class WorkuaDetails:
    website: str | None
    contacts: ContactSet


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
