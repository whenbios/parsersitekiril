import re
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup


EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_RE = re.compile(r"\+?[\d\s().-]{8,}\d")
TELEGRAM_HANDLE_RE = re.compile(r"(?<!\w)@([A-Za-z0-9_]{5,})")


def _dedupe_append(target: list[str], value: str) -> None:
    if value and value not in target:
        target.append(value)


def normalize_url(value: str) -> str:
    parsed = urlparse(value.strip())
    if not parsed.scheme:
        value = f"https://{value.strip()}"
        parsed = urlparse(value)
    path = "/" if parsed.path == "/" else parsed.path
    normalized = parsed._replace(
        scheme=parsed.scheme.lower(),
        netloc=parsed.netloc.lower(),
        path=path,
        params="",
        fragment="",
    )
    return normalized.geturl()


def normalize_email(value: str) -> str:
    return value.strip().lower()


def normalize_phone(value: str) -> str:
    digits = re.sub(r"\D", "", value)
    if not digits:
        return ""
    if value.strip().startswith("+"):
        return f"+{digits}"
    if digits.startswith("00"):
        return f"+{digits[2:]}"
    if digits.startswith("380"):
        return f"+{digits}"
    return f"+{digits}"


def _classify_email(context: str, email: str) -> str:
    context_lower = context.lower()
    local_part = email.split("@", 1)[0].lower()
    if any(token in local_part for token in ("marketing", "market", "promo", "pr")):
        return "marketing"
    if any(token in local_part for token in ("school", "info", "contact", "hello", "office", "sales", "hr")):
        return "general"
    if any(token in context_lower for token in ("керівник", "директор", "owner", "ceo", "особисто", "manager")):
        return "manager"
    if any(token in context_lower for token in ("marketing", "маркет", "promo", "pr")) or "marketing" in local_part:
        return "marketing"
    return "general"


PUBLIC_EMAIL_DOMAINS = {
    "gmail.com",
    "outlook.com",
    "hotmail.com",
    "ukr.net",
    "i.ua",
    "meta.ua",
}


def _looks_like_main_phone(phone: str) -> bool:
    digits = re.sub(r"\D", "", phone)
    return digits.startswith("0800") or digits.startswith("800")


def _is_reasonable_phone(phone: str) -> bool:
    digits = re.sub(r"\D", "", phone)
    if len(digits) < 10 or len(digits) > 13:
        return False
    if len(digits) > 10 and digits[: len(digits) // 2] == digits[len(digits) // 2 :]:
        return False
    return digits.startswith("380") or digits.startswith("0800") or digits.startswith("800")


@dataclass
class ContactSet:
    emails: list[str] = field(default_factory=list)
    telegrams: list[str] = field(default_factory=list)
    phones: list[str] = field(default_factory=list)
    instagram: str | None = None
    facebook: str | None = None
    linkedin: str | None = None
    whatsapp: str | None = None
    viber: str | None = None
    general_email: str | None = None
    marketing_email: str | None = None
    manager_email: str | None = None
    main_phone: str | None = None
    other_links: list[str] = field(default_factory=list)
    discovered_pages: list[str] = field(default_factory=list)

    def merge(self, other: "ContactSet") -> None:
        for email in other.emails:
            _dedupe_append(self.emails, email)
        for telegram in other.telegrams:
            _dedupe_append(self.telegrams, telegram)
        for phone in other.phones:
            _dedupe_append(self.phones, phone)
        if not self.instagram and other.instagram:
            self.instagram = other.instagram
        if not self.facebook and other.facebook:
            self.facebook = other.facebook
        if not self.linkedin and other.linkedin:
            self.linkedin = other.linkedin
        if not self.whatsapp and other.whatsapp:
            self.whatsapp = other.whatsapp
        if not self.viber and other.viber:
            self.viber = other.viber
        if not self.general_email and other.general_email:
            self.general_email = other.general_email
        if not self.marketing_email and other.marketing_email:
            self.marketing_email = other.marketing_email
        if not self.manager_email and other.manager_email:
            self.manager_email = other.manager_email
        if not self.main_phone and other.main_phone:
            self.main_phone = other.main_phone
        for link in other.other_links:
            _dedupe_append(self.other_links, link)
        for page in other.discovered_pages:
            _dedupe_append(self.discovered_pages, page)


def extract_contacts(html: str, page_url: str) -> ContactSet:
    soup = BeautifulSoup(html, "html.parser")
    result = ContactSet(discovered_pages=[normalize_url(page_url)])

    for anchor in soup.find_all("a", href=True):
        href = anchor["href"].strip()
        text = anchor.get_text(" ", strip=True)
        absolute = urljoin(page_url, href)
        href_lower = href.lower()
        absolute_lower = absolute.lower()

        if href_lower.startswith("mailto:"):
            email = normalize_email(href[7:])
            _dedupe_append(result.emails, email)
            context = anchor.parent.get_text(" ", strip=True) if anchor.parent else text
            classification = _classify_email(context, email)
            if classification == "manager" and not result.manager_email:
                result.manager_email = email
            elif classification == "marketing" and not result.marketing_email:
                result.marketing_email = email
            elif not result.general_email:
                result.general_email = email
            continue
        if href_lower.startswith("tel:"):
            phone = normalize_phone(href[4:])
            if phone and _is_reasonable_phone(phone):
                _dedupe_append(result.phones, phone)
                if not result.main_phone and _looks_like_main_phone(phone):
                    result.main_phone = phone
            continue
        if "t.me/" in absolute_lower or "telegram.me/" in absolute_lower:
            _dedupe_append(result.telegrams, normalize_url(absolute))
            continue
        if "instagram.com/" in absolute_lower and not result.instagram:
            result.instagram = normalize_url(absolute)
            continue
        if "facebook.com/" in absolute_lower and not result.facebook:
            result.facebook = normalize_url(absolute)
            continue
        if "linkedin.com/" in absolute_lower and not result.linkedin:
            result.linkedin = normalize_url(absolute)
            continue
        if absolute_lower.startswith("http") or absolute_lower.startswith("viber:"):
            if "api.whatsapp.com/" in absolute_lower or "wa.me/" in absolute_lower or "whatsapp" in absolute_lower:
                normalized = normalize_url(absolute) if absolute_lower.startswith("http") else absolute
                if not result.whatsapp:
                    result.whatsapp = normalized
                _dedupe_append(result.other_links, normalized)
            elif absolute_lower.startswith("viber:") or "viber.com/" in absolute_lower:
                normalized = absolute if absolute_lower.startswith("viber:") else normalize_url(absolute)
                if not result.viber:
                    result.viber = normalized
                _dedupe_append(result.other_links, normalized)

        for email in EMAIL_RE.findall(text):
            normalized = normalize_email(email)
            _dedupe_append(result.emails, normalized)
            if not result.general_email:
                result.general_email = normalized
        for handle in TELEGRAM_HANDLE_RE.findall(text):
            _dedupe_append(result.telegrams, f"https://t.me/{handle}")

    for chunk in soup.stripped_strings:
        text_chunk = chunk.strip()
        for email in EMAIL_RE.findall(text_chunk):
            normalized = normalize_email(email)
            _dedupe_append(result.emails, normalized)
        for raw_phone in PHONE_RE.findall(text_chunk):
            phone = normalize_phone(raw_phone)
            if phone and _is_reasonable_phone(phone):
                _dedupe_append(result.phones, phone)
                if not result.main_phone and _looks_like_main_phone(phone):
                    result.main_phone = phone
        for handle in TELEGRAM_HANDLE_RE.findall(text_chunk):
            _dedupe_append(result.telegrams, f"https://t.me/{handle}")

    if not result.general_email and result.emails:
        result.general_email = result.emails[0]
    if not result.manager_email and result.emails and (result.general_email or result.marketing_email):
        for email in result.emails:
            domain = email.split("@", 1)[1].lower()
            if email not in {result.general_email, result.marketing_email} and domain in PUBLIC_EMAIL_DOMAINS:
                result.manager_email = email
                break
    if not result.main_phone and result.phones:
        result.main_phone = result.phones[0]

    return result


def discover_relevant_pages(html: str, base_url: str, *, limit: int = 8) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    candidates: list[str] = []
    keywords = ("contact", "contacts", "about", "jobs", "vacancies", "career")
    base_host = urlparse(base_url).netloc.lower()

    for anchor in soup.find_all("a", href=True):
        href = anchor["href"].strip()
        text = anchor.get_text(" ", strip=True).lower()
        absolute = normalize_url(urljoin(base_url, href))
        parsed = urlparse(absolute)
        signal = f"{text} {parsed.path.lower()}"
        if parsed.netloc.lower() != base_host:
            continue
        if any(keyword in signal for keyword in keywords):
            _dedupe_append(candidates, absolute)
        if len(candidates) >= limit:
            break

    return candidates


def flatten_contacts_for_sheet(
    *,
    contacts: ContactSet,
    website: str,
    status: str,
    error: str,
    last_checked: str,
    company_name: str = "",
    workua_url: str = "",
    row_index: int | None = None,
) -> dict[str, str | int | None]:
    return {
        "row_index": row_index,
        "company_name": company_name,
        "workua_url": workua_url,
        "website": website,
        "email_1": contacts.emails[0] if len(contacts.emails) > 0 else "",
        "email_2": contacts.emails[1] if len(contacts.emails) > 1 else "",
        "email_3": contacts.emails[2] if len(contacts.emails) > 2 else "",
        "email_outreach": "",
        "email_secondary": "",
        "general_email": contacts.general_email or "",
        "marketing_email": contacts.marketing_email or "",
        "manager_email": contacts.manager_email or "",
        "telegram_1": contacts.telegrams[0] if len(contacts.telegrams) > 0 else "",
        "telegram_2": contacts.telegrams[1] if len(contacts.telegrams) > 1 else "",
        "telegram_3": contacts.telegrams[2] if len(contacts.telegrams) > 2 else "",
        "whatsapp": contacts.whatsapp or "",
        "viber": contacts.viber or "",
        "main_phone": contacts.main_phone or "",
        "phone_direct": "",
        "phone_public": "",
        "phone_1": contacts.phones[0] if len(contacts.phones) > 0 else "",
        "phone_2": contacts.phones[1] if len(contacts.phones) > 1 else "",
        "phone_3": contacts.phones[2] if len(contacts.phones) > 2 else "",
        "instagram": contacts.instagram or "",
        "facebook": contacts.facebook or "",
        "linkedin": contacts.linkedin or "",
        "best_channel": "",
        "best_contact": "",
        "backup_contact": "",
        "workua_fallback": "",
        "workua_email": "",
        "workua_telegram": "",
        "workua_phone": "",
        "other_links": "\n".join(contacts.other_links),
        "status": status,
        "notes": "",
        "error": error,
        "last_checked": last_checked,
    }
