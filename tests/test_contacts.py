from pathlib import Path

import pytest

from app.services.contacts import extract_contacts, flatten_contacts_for_sheet
from app.services.workua import extract_workua_company_details


FIXTURES = Path(__file__).parent / "fixtures"


def read_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_extract_contacts_collects_emails_telegrams_phones_socials_and_other_links():
    contacts = extract_contacts(
        read_fixture("company_home.html"),
        "https://acme.example.com/",
    )
    contacts.merge(
        extract_contacts(
            read_fixture("company_contacts.html"),
            "https://acme.example.com/contacts",
        )
    )
    contacts.merge(
        extract_contacts(
            read_fixture("company_about.html"),
            "https://acme.example.com/about",
        )
    )

    assert contacts.emails == [
        "hello@acme.example.com",
        "sales@acme.example.com",
        "hr@acme.example.com",
        "partnership@acme.example.com",
    ]
    assert contacts.telegrams == [
        "https://t.me/acme_team",
        "https://t.me/acme_hr",
    ]
    assert contacts.phones == [
        "+380501234567",
    ]
    assert contacts.instagram == "https://www.instagram.com/acme.example"
    assert contacts.facebook == "https://www.facebook.com/acme.example"
    assert contacts.linkedin == "https://www.linkedin.com/company/acme-example/"
    assert contacts.other_links == [
        "https://wa.me/380501010101",
    ]


def test_extract_workua_company_details_returns_site_and_inline_contacts():
    details = extract_workua_company_details(
        read_fixture("workua_company.html"),
        "https://www.work.ua/jobs/by-company/1/",
    )

    assert details.website == "https://acme.example.com"
    assert details.contacts.emails == ["jobs@workua.example.com"]
    assert details.contacts.phones == ["+380441112233"]


def test_extract_workua_company_details_prefers_company_site_over_share_links_and_workua_socials():
    details = extract_workua_company_details(
        read_fixture("workua_job_real_fragment.html"),
        "https://www.work.ua/jobs/7508011/",
    )

    assert details.website == "https://express-line.com.ua/uk/"


def test_flatten_contacts_for_sheet_places_values_into_fixed_columns():
    contacts = extract_contacts(
        read_fixture("company_contacts.html"),
        "https://acme.example.com/contacts",
    )

    row = flatten_contacts_for_sheet(
        contacts=contacts,
        website="https://acme.example.com",
        status="done",
        error="",
        last_checked="2026-05-02T10:30:00Z",
    )

    assert row["website"] == "https://acme.example.com"
    assert row["email_1"] == "sales@acme.example.com"
    assert row["email_2"] == "hr@acme.example.com"
    assert row["email_3"] == ""
    assert row["general_email"] == "sales@acme.example.com"
    assert row["main_phone"] == "+380501234567"
    assert row["telegram_1"] == "https://t.me/acme_hr"
    assert row["phone_1"] == "+380501234567"
    assert row["facebook"] == "https://www.facebook.com/acme.example"
    assert row["status"] == "done"
    assert row["last_checked"] == "2026-05-02T10:30:00Z"


def test_extract_contacts_returns_empty_values_for_pages_without_contacts():
    contacts = extract_contacts(
        read_fixture("company_empty.html"),
        "https://acme.example.com/empty",
    )

    assert contacts.emails == []
    assert contacts.telegrams == []
    assert contacts.phones == []
    assert contacts.instagram is None
    assert contacts.facebook is None
    assert contacts.linkedin is None
    assert contacts.other_links == []


def test_extract_contacts_classifies_general_marketing_manager_and_main_phone():
    contacts = extract_contacts(
        read_fixture("greencountry_contacts_snippet.html"),
        "https://greencountry.com.ua/contacts",
    )

    assert contacts.general_email == "school@greencountry.com.ua"
    assert contacts.marketing_email == "marketing@greencountry.com.ua"
    assert contacts.manager_email == "nmt.sweet.dreams@gmail.com"
    assert contacts.main_phone == "+0800758978"
    assert contacts.whatsapp == "https://api.whatsapp.com/send?phone=380969465392"
    assert contacts.viber == "viber://chat?number=%2B380969465392"
    assert "+1730629463825" not in contacts.phones


def test_extract_contacts_uses_personal_email_as_manager_when_business_emails_already_exist():
    html = """
    <html><body>
      <a href="mailto:school@example.com">school@example.com</a>
      <a href="mailto:marketing@example.com">marketing@example.com</a>
      <a href="mailto:personal.manager@gmail.com">personal.manager@gmail.com</a>
    </body></html>
    """

    contacts = extract_contacts(html, "https://example.com/contacts")

    assert contacts.general_email == "school@example.com"
    assert contacts.marketing_email == "marketing@example.com"
    assert contacts.manager_email == "personal.manager@gmail.com"


def test_extract_contacts_uses_public_mailbox_as_manager_when_other_business_emails_exist():
    html = """
    <html><body>
      <a href="mailto:school@example.com">school@example.com</a>
      <a href="mailto:marketing@example.com">marketing@example.com</a>
      <a href="mailto:nmt.sweet.dreams@gmail.com">nmt.sweet.dreams@gmail.com</a>
    </body></html>
    """

    contacts = extract_contacts(html, "https://example.com/contacts")

    assert contacts.manager_email == "nmt.sweet.dreams@gmail.com"


def test_extract_contacts_keeps_ukrainian_phone_formats_and_drops_timestamp_like_numbers():
    html = """
    <html><body>
      <a href="tel:+380639411973">063 941 1973</a>
      <div>0 800 758 978</div>
      <div>84 063 941 1973</div>
      <div>1730629463825</div>
    </body></html>
    """

    contacts = extract_contacts(html, "https://example.com")

    assert contacts.phones == ["+380639411973", "+0800758978"]
