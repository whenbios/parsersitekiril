import os

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import Response
from dotenv import load_dotenv

from app.schemas import (
    CollectedVacancy,
    CollectorResultsResponse,
    CollectorStatusResponse,
    CompanyEnrichRequest,
    EnrichedRow,
    JobResultsResponse,
    JobStartRequest,
    JobStartResponse,
    JobStatusResponse,
    WorkuaCollectRequest,
)
from app.services.enrichment import EnrichmentService
from app.services.exports import (
    build_collect_csv_export,
    build_collect_xlsx_export,
    build_csv_export,
    build_xlsx_export,
)
from app.services.uploads import parse_upload_bytes
from app.services.workua_collector import WorkuaCollectorService
from app.storage import JobStore
from app.ui_assets import APP_JS, INDEX_HTML, STYLES_CSS
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
    collector_service = WorkuaCollectorService(zyte_client=client, store=store)

    app = FastAPI(title="Work.ua Contact Enrichment MVP")

    @app.get("/")
    def index() -> Response:
        return Response(content=INDEX_HTML, media_type="text/html; charset=utf-8")

    @app.get("/app.js", include_in_schema=False)
    def app_js() -> Response:
        return Response(content=APP_JS, media_type="application/javascript")

    @app.get("/styles.css", include_in_schema=False)
    def styles_css() -> Response:
        return Response(content=STYLES_CSS, media_type="text/css")

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

    @app.post("/collectors/workua/start", response_model=JobStartResponse)
    def start_collect_job(payload: WorkuaCollectRequest) -> JobStartResponse:
        job_id = collector_service.start_job(payload.filter_url)
        return JobStartResponse(job_id=job_id)

    @app.get("/collectors/workua/{job_id}/status", response_model=CollectorStatusResponse)
    def get_collect_job_status(job_id: int) -> CollectorStatusResponse:
        status = store.get_collector_job_status(job_id)
        if status is None:
            raise HTTPException(status_code=404, detail="Collector job not found")
        return status

    @app.get("/collectors/workua/{job_id}/results", response_model=CollectorResultsResponse)
    def get_collect_job_results(job_id: int) -> CollectorResultsResponse:
        items = store.get_collector_job_results(job_id)
        if items is None:
            raise HTTPException(status_code=404, detail="Collector job not found")
        return CollectorResultsResponse(job_id=job_id, items=items)

    @app.get("/collectors/workua/{job_id}/export.csv")
    def export_collect_csv(job_id: int) -> Response:
        items = store.get_collector_job_results(job_id)
        if items is None:
            raise HTTPException(status_code=404, detail="Collector job not found")
        return Response(
            content=build_collect_csv_export(items),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="collector-{job_id}-vacancies.csv"'},
        )

    @app.get("/collectors/workua/{job_id}/export.xlsx")
    def export_collect_xlsx(job_id: int) -> Response:
        items = store.get_collector_job_results(job_id)
        if items is None:
            raise HTTPException(status_code=404, detail="Collector job not found")
        return Response(
            content=build_collect_xlsx_export(items),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="collector-{job_id}-vacancies.xlsx"'},
        )

    @app.post("/collectors/workua/{job_id}/start-enrichment", response_model=JobStartResponse)
    def start_collect_enrichment(job_id: int) -> JobStartResponse:
        try:
            items = collector_service.start_enrichment(job_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        enrich_job_id = service.start_job(items)
        return JobStartResponse(job_id=enrich_job_id)

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
