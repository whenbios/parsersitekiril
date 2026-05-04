from datetime import datetime

from pydantic import BaseModel, Field


class CompanyEnrichRequest(BaseModel):
    company_name: str
    workua_url: str
    row_index: int | None = None


class JobItemRequest(BaseModel):
    row_index: int
    company_name: str
    workua_url: str


class JobStartRequest(BaseModel):
    items: list[JobItemRequest]


class JobStartResponse(BaseModel):
    job_id: int


class WorkuaCollectRequest(BaseModel):
    filter_url: str


class CollectedVacancy(BaseModel):
    row_index: int
    company_name: str
    workua_url: str
    page_number: int
    status: str = Field(default="collected")


class CollectorStatusResponse(BaseModel):
    job_id: int
    status: str
    filter_url: str
    total_pages: int
    processed_pages: int
    found_items: int
    error: str = ""


class CollectorResultsResponse(BaseModel):
    job_id: int
    items: list[CollectedVacancy]


class EnrichedRow(BaseModel):
    row_index: int | None = None
    company_name: str
    workua_url: str
    website: str = ""
    email_1: str = ""
    email_2: str = ""
    email_3: str = ""
    email_outreach: str = ""
    email_secondary: str = ""
    general_email: str = ""
    marketing_email: str = ""
    manager_email: str = ""
    telegram_1: str = ""
    telegram_2: str = ""
    telegram_3: str = ""
    whatsapp: str = ""
    viber: str = ""
    main_phone: str = ""
    phone_direct: str = ""
    phone_public: str = ""
    phone_1: str = ""
    phone_2: str = ""
    phone_3: str = ""
    instagram: str = ""
    facebook: str = ""
    linkedin: str = ""
    best_channel: str = ""
    best_contact: str = ""
    backup_contact: str = ""
    workua_fallback: str = ""
    workua_email: str = ""
    workua_telegram: str = ""
    workua_phone: str = ""
    other_links: str = ""
    status: str = Field(default="new")
    notes: str = ""
    error: str = ""
    last_checked: str = Field(
        default_factory=lambda: datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    )


class JobStatusResponse(BaseModel):
    job_id: int
    status: str
    total_items: int
    queued_items: int
    processing_items: int
    done_items: int
    failed_items: int


class JobResultsResponse(BaseModel):
    job_id: int
    items: list[EnrichedRow]
