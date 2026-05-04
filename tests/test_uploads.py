from io import BytesIO

import openpyxl

from app.services.uploads import parse_upload_bytes


def test_parse_upload_bytes_reads_xlsx_with_workua_export_headers():
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(["strong-600 2", "my-0 href"])
    sheet.append(["Green Country", "https://www.work.ua/jobs/7622518/"])
    sheet.append(["Grand Car", "https://www.work.ua/jobs/7249660/"])
    buffer = BytesIO()
    workbook.save(buffer)

    items = parse_upload_bytes("work.xlsx", buffer.getvalue())

    assert len(items) == 2
    assert items[0].row_index == 2
    assert items[0].company_name == "Green Country"
    assert items[0].workua_url == "https://www.work.ua/jobs/7622518/"
    assert items[1].company_name == "Grand Car"


def test_parse_upload_bytes_reads_csv_with_product_headers():
    payload = (
        "company_name,workua_url\n"
        "Example Co,https://www.work.ua/jobs/1/\n"
        "Another Co,https://www.work.ua/jobs/2/\n"
    ).encode("utf-8")

    items = parse_upload_bytes("work.csv", payload)

    assert len(items) == 2
    assert items[0].company_name == "Example Co"
    assert items[1].workua_url == "https://www.work.ua/jobs/2/"
