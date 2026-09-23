from datetime import datetime, timezone
from pathlib import Path

from pyexpat.errors import messages
from redis import Redis

from directories import get_filing_directory
from ingest.database import (
    get_download_job, get_filing_manifest, mark_document_downloaded,
    mark_document_downloading, mark_document_failed, mark_download_job_completed,
    mark_download_job_failed, mark_download_job_processing,
)
from ingest.downloader import HEADERS, download_document, is_document_file_valid
from ingest.download_queue import (
    acknowledge_download_message,
    get_redis_client,
    initialize_download_queue,
    read_new_download_message,
)
from ingest.models import DownloadQueueMessage

CONSUMER_NAME = "worker-1"

def get_job_filing_directory(manifest_key: str) -> Path:
    storage_root = get_filing_directory().resolve()
    manifest_path = (storage_root / manifest_key).resolve()

    if not manifest_path.is_relative_to(storage_root):
        raise ValueError(
            f"Manifest key escapes the filing directory: {manifest_key}")
    if manifest_path.name != "filing.json":
        raise ValueError(
            f"Unexpected manifest filename: {manifest_key}")
    return manifest_path.parent

def process_message(redis_client: Redis, message: DownloadQueueMessage) -> None:
    job = get_download_job(message.job_id)
    if job is None:
        raise ValueError(f"Download job {message.job_id} not found")
    if job.accession_number != message.accession_number:
        raise ValueError(
            f"Download job {message.job_id} has accession number {job.accession_number}, "
            f"but message has accession number {message.accession_number}"
        )
    if job.manifest_key != message.manifest_key:
        raise ValueError(
            f"Download job {message.job_id} has manifest key {job.manifest_key}, "
            f"but message has manifest key {message.manifest_key}"
        )

    # set redis appendfsync everysec
    # So the job may already have completed before a Redis acknowledgement failed
    # A redelivered message can therefore be safely acknowledged

    if job.status == "completed":
        acknowledge_download_message(redis_client, message.message_id)
        return

    if job.status != "queued":
        raise ValueError(f"Job {job.job_id} cannot be processed from status {job.status!r}")

    manifest = get_filing_manifest(job.accession_number)

    if manifest is None:
        raise ValueError(f"No manifest found for accession number {job.accession_number}")

    filing_directory = get_job_filing_directory(job.manifest_key)
    mark_download_job_processing(job.job_id)

    try:
        failed_filenames: list[str] = []

        for document in manifest.documents:
            if is_document_file_valid(document, filing_directory):
                continue

            mark_document_downloading(manifest.filing.accession_number, document.filename)
            try:
                result = download_document(document, filing_directory, HEADERS,)
            except (OSError, ValueError, EOFError) as error:
                failed_at = datetime.now(timezone.utc).isoformat()
                error_message = f"{type(error).__name__}: {error}"

                mark_document_failed(manifest.filing.accession_number, document.filename, failed_at, error_message)
                failed_filenames.append(document.filename)
            else:
                mark_document_downloaded(
                    manifest.filing.accession_number, document.filename, result.storage_key,
                    result.downloaded_at, result.content_type, result.size_bytes, result.sha256)
    except Exception as error:
        error_message = f"{type(error).__name__}: {error}"
        mark_download_job_failed(job.job_id, error_message)
        raise

    acknowledge_download_message(redis_client, message.message_id)

def main() -> None:
    redis_client = get_redis_client()
    initialize_download_queue(redis_client)

    message = read_new_download_message(redis_client, CONSUMER_NAME, count=1, block_ms=5_000)

    if not message:
        print("No download message available")
    for message in messages:
        process_message(redis_client, message)
        print(f"Completed downlaod job {message.job_id}")

if __name__ == "__main__":
    main()
