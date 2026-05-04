import os
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from dotenv import load_dotenv

from app.schemas import (
    CompanyEnrichRequest,
    EnrichedRow,
    JobResultsResponse,
    JobStartRequest,
    JobStartResponse,
    JobStatusResponse,
)
from app.services.enrichment import EnrichmentService
from app.services.exports import build_csv_export, build_xlsx_export
from app.services.uploads import parse_upload_bytes
from app.storage import JobStore
from app.zyte import HttpZyteClient, ZyteClientProtocol


load_dotenv(".env.local", override=False)


def create_app(
    *,
    zyte_client: ZyteClientProtocol | None = None,
    db_path: str = ":memory:",
) -> FastAPI:
    store = JobStore(db_path)
    client = zyte_client or HttpZyteClient(api_key=os.getenv("ZYTE_API_KEY"))
    service = EnrichmentService(zyte_client=client, store=store)

    app = FastAPI(title="Work.ua Contact Enrichment MVP")
    public_dir = Path(__file__).resolve().parent.parent / "public"

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(public_dir / "index.html")

    @app.get("/app.js", include_in_schema=False)
    def app_js() -> FileResponse:
        return FileResponse(public_dir / "app.js", media_type="application/javascript")

    @app.get("/styles.css", include_in_schema=False)
    def styles_css() -> FileResponse:
        return FileResponse(public_dir / "styles.css", media_type="text/css")

    @app.get("/health")
    def healthcheck() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/companies/enrich", response_model=EnrichedRow)
    def enrich_company(payload: CompanyEnrichRequest) -> EnrichedRow:
        return service.enrich_company(
            company_name=payload.company_name,
            workua_url=payload.workua_url,
            row_index=payload.row_index,
        )

    @app.post("/jobs/start", response_model=JobStartResponse)
    def start_job(payload: JobStartRequest) -> JobStartResponse:
        job_id = service.start_job(payload.items)
        return JobStartResponse(job_id=job_id)

    @app.post("/jobs/upload", response_model=JobStartResponse)
    async def upload_job(file: UploadFile = File(...)) -> JobStartResponse:
        content = await file.read()
        items = parse_upload_bytes(file.filename or "upload.xlsx", content)
        job_id = service.start_job(items)
        return JobStartResponse(job_id=job_id)

    @app.get("/jobs/{job_id}/status", response_model=JobStatusResponse)
    def get_job_status(job_id: int) -> JobStatusResponse:
        status = store.get_job_status(job_id)
        if status is None:
            raise HTTPException(status_code=404, detail="Job not found")
        return status

    @app.get("/jobs/{job_id}/results", response_model=JobResultsResponse)
    def get_job_results(job_id: int) -> JobResultsResponse:
        items = store.get_job_results(job_id)
        if items is None:
            raise HTTPException(status_code=404, detail="Job not found")
        return JobResultsResponse(job_id=job_id, items=items)

    @app.get("/jobs/{job_id}/export.csv")
    def export_csv(job_id: int) -> Response:
        items = store.get_job_results(job_id)
        if items is None:
            raise HTTPException(status_code=404, detail="Job not found")
        return Response(
            content=build_csv_export(items),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="job-{job_id}-results.csv"'},
        )

    @app.get("/jobs/{job_id}/export.xlsx")
    def export_xlsx(job_id: int) -> Response:
        items = store.get_job_results(job_id)
        if items is None:
            raise HTTPException(status_code=404, detail="Job not found")
        return Response(
            content=build_xlsx_export(items),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="job-{job_id}-results.xlsx"'},
        )

    return app


app = create_app(db_path=os.getenv("WORKUA_DB_PATH", ":memory:"))
