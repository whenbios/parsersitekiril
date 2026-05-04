from dataclasses import dataclass

from app.services.contacts import ContactSet


@dataclass
class ContactSummary:
    best_channel: str = ""
    best_contact: str = ""
    backup_contact: str = ""
    workua_fallback: str = ""
    workua_email: str = ""
    workua_telegram: str = ""
    workua_phone: str = ""
    email_outreach: str = ""
    email_secondary: str = ""
    phone_direct: str = ""
    phone_public: str = ""
    notes: str = ""


def summarize_contacts(*, site_contacts: ContactSet, workua_contacts: ContactSet) -> ContactSummary:
    summary = ContactSummary()
    summary.workua_email = (
        workua_contacts.general_email
        or (workua_contacts.emails[0] if workua_contacts.emails else "")
    )
    summary.workua_telegram = workua_contacts.telegrams[0] if workua_contacts.telegrams else ""
    summary.workua_phone = workua_contacts.main_phone or (workua_contacts.phones[0] if workua_contacts.phones else "")

    summary.email_outreach = (
        site_contacts.manager_email
        or site_contacts.marketing_email
        or site_contacts.general_email
        or (site_contacts.emails[0] if site_contacts.emails else "")
    )
    if site_contacts.emails:
        for email in site_contacts.emails:
            if email != summary.email_outreach:
                summary.email_secondary = email
                break

    summary.phone_public = _first_public_phone(site_contacts)
    summary.phone_direct = _first_direct_phone(site_contacts, exclude=summary.phone_public)

    primary_candidates = _site_contact_candidates(site_contacts, summary)
    workua_candidates = _workua_contact_candidates(summary)
    all_candidates = primary_candidates or workua_candidates

    if all_candidates:
        summary.best_channel, summary.best_contact = all_candidates[0]
    if len(all_candidates) > 1:
        summary.backup_contact = all_candidates[1][1]
    if workua_candidates:
        summary.workua_fallback = workua_candidates[0][1]

    notes: list[str] = []
    if summary.best_contact and primary_candidates:
        notes.append("site contacts prioritized")
    elif summary.best_contact:
        notes.append("using Work.ua fallback")
    if summary.phone_public:
        notes.append("public phone kept separate")
    summary.notes = "; ".join(notes)
    return summary


def _site_contact_candidates(site_contacts: ContactSet, summary: ContactSummary) -> list[tuple[str, str]]:
    candidates: list[tuple[str, str]] = []
    seen: set[str] = set()
    ordered = [
        ("telegram", site_contacts.telegrams[0] if site_contacts.telegrams else ""),
        ("whatsapp", site_contacts.whatsapp or ""),
        ("manager_email", site_contacts.manager_email or ""),
        ("marketing_email", site_contacts.marketing_email or ""),
        ("email", summary.email_outreach),
        ("phone_direct", summary.phone_direct),
        ("phone_public", summary.phone_public),
    ]
    for channel, value in ordered:
        if value and value not in seen:
            candidates.append((channel, value))
            seen.add(value)
    return candidates


def _workua_contact_candidates(summary: ContactSummary) -> list[tuple[str, str]]:
    candidates: list[tuple[str, str]] = []
    for channel, value in (
        ("workua_telegram", summary.workua_telegram),
        ("workua_email", summary.workua_email),
        ("workua_phone", summary.workua_phone),
    ):
        if value:
            candidates.append((channel, value))
    return candidates


def _first_public_phone(contacts: ContactSet) -> str:
    for phone in contacts.phones:
        if phone.startswith("+0800") or phone.startswith("+800"):
            return phone
    if contacts.main_phone and (contacts.main_phone.startswith("+0800") or contacts.main_phone.startswith("+800")):
        return contacts.main_phone
    return ""


def _first_direct_phone(contacts: ContactSet, *, exclude: str) -> str:
    for phone in contacts.phones:
        if phone != exclude:
            return phone
    if contacts.main_phone and contacts.main_phone != exclude:
        return contacts.main_phone
    return ""
