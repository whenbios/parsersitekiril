from app.services.contacts import ContactSet
from app.services.presentation import summarize_contacts


def test_summarize_contacts_prefers_site_messenger_then_email_and_keeps_workua_fallback():
    site_contacts = ContactSet(
        emails=["hello@example.com", "backup@example.com"],
        telegrams=["https://t.me/example_team"],
        phones=["+380501112233", "+0800123456"],
        general_email="hello@example.com",
        marketing_email="marketing@example.com",
        manager_email="owner@gmail.com",
        whatsapp="https://api.whatsapp.com/send?phone=380501112233",
        main_phone="+0800123456",
    )
    workua_contacts = ContactSet(
        emails=["hr@workua.example"],
        telegrams=["https://t.me/workua_hr"],
        phones=["+380671234567"],
    )

    summary = summarize_contacts(site_contacts=site_contacts, workua_contacts=workua_contacts)

    assert summary.email_outreach == "owner@gmail.com"
    assert summary.phone_direct == "+380501112233"
    assert summary.phone_public == "+0800123456"
    assert summary.best_channel == "telegram"
    assert summary.best_contact == "https://t.me/example_team"
    assert summary.backup_contact == "https://api.whatsapp.com/send?phone=380501112233"
    assert summary.workua_email == "hr@workua.example"
    assert summary.workua_telegram == "https://t.me/workua_hr"
    assert summary.workua_phone == "+380671234567"
    assert summary.workua_fallback == "https://t.me/workua_hr"


def test_summarize_contacts_falls_back_to_workua_when_site_has_no_useful_contacts():
    site_contacts = ContactSet()
    workua_contacts = ContactSet(
        emails=["hr@company.test"],
        phones=["+380631110000"],
    )

    summary = summarize_contacts(site_contacts=site_contacts, workua_contacts=workua_contacts)

    assert summary.best_channel == "workua_email"
    assert summary.best_contact == "hr@company.test"
    assert summary.backup_contact == "+380631110000"
    assert summary.workua_fallback == "hr@company.test"
