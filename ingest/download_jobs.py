from datetime import datetime, timezone

from directories import get_job_filing_directory, HEADERS
from ingest.database import (
    get_filing_manifest, mark_download_job_completed, mark_download_job_failed,
    mark_document_downloading, mark_document_downloaded, mark_document_failed,
    claim_download_job_processing
)

from ingest.downloader import download_document, is_document_file_valid

from ingest.models import DownloadJob


def process_download_job(job: DownloadJob) -> None:
    if not claim_download_job_processing(job.job_id):
        return  # duplicate delivery or job already finished
    try:
        manifest = get_filing_manifest(job.accession_number)
        if manifest is None:
            raise ValueError(f"No manifest found for accession number {job.accession_number}")

        if not manifest.documents:
            raise ValueError(
                f"No documents found for accession number "
                f"{job.accession_number}"
            )
        filing_directory = get_job_filing_directory(job.manifest_key)
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
                mark_document_downloaded(job.accession_number, document.filename,
                                         result.storage_key,result.downloaded_at,
                                         result.content_type, result.size_bytes, result.sha256)

        if failed_filenames:
            raise RuntimeError(f"Failed to download {', '.join(failed_filenames)}")

        mark_download_job_completed(job.job_id)

    except Exception as error:
        error_message = f"{type(error).__name__}: {error}"
        mark_download_job_failed(job.job_id, error_message)
        raise