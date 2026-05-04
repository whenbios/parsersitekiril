from __future__ import annotations

import csv
from io import BytesIO, StringIO

import openpyxl

from app.schemas import EnrichedRow


EXPORT_COLUMNS = [
    "company_name",
    "workua_url",
    "website",
    "best_channel",
    "best_contact",
    "backup_contact",
    "workua_fallback",
    "email_outreach",
    "email_secondary",
    "manager_email",
    "marketing_email",
    "telegram_1",
    "whatsapp",
    "phone_direct",
    "phone_public",
    "workua_email",
    "workua_telegram",
    "workua_phone",
    "status",
    "notes",
    "error",
    "last_checked",
]


def build_csv_export(rows: list[EnrichedRow]) -> bytes:
    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=EXPORT_COLUMNS)
    writer.writeheader()
    for row in rows:
        payload = row.model_dump()
        writer.writerow({column: payload.get(column, "") for column in EXPORT_COLUMNS})
    return buffer.getvalue().encode("utf-8-sig")


def build_xlsx_export(rows: list[EnrichedRow]) -> bytes:
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "results"
    sheet.append(EXPORT_COLUMNS)
    for row in rows:
        payload = row.model_dump()
        sheet.append([payload.get(column, "") for column in EXPORT_COLUMNS])
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()
