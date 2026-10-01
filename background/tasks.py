from background.celery_app import app
from ingest.scanner import scan_filings_by_tickers
from ingest.database import get_download_job, get_download_jobs_to_dispatch, mark_download_job_queued
from ingest.download_jobs import process_download_job
from directories import HEADERS as SCAN_HEADERS

@app.task(name="background.ping")
def ping() -> str:
    return "pong"

@app.task(name="background.scan_filings", ignore_result = True)
def scan_filings(tickers: list[str], limit: int = 4) -> None:
    scan_filings_by_tickers(tickers, SCAN_HEADERS, limit)

@app.task(name="background.download_job", ignore_result = True)
def download_job(job_id: int) -> None:
    job = get_download_job(job_id)
    if job is None:
        raise ValueError(f"Download job {job_id} not found")

    process_download_job(job)

@app.task(name="background.publish_download_jobs", ignore_result = True)
def publish_download_jobs(limit: int = 100) -> None:
    for job_id in get_download_jobs_to_dispatch(limit):
        if mark_download_job_queued(job_id):  # commits before returning
            download_job.delay(job_id)