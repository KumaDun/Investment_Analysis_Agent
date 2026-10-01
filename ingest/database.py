import os
from typing import LiteralString

import psycopg
from dotenv import load_dotenv

from directories import get_root_directory

from ingest.models import Filing, FilingManifest, DownloadJob, FilingDocument


def get_connection() -> psycopg.Connection:
    env_path = get_root_directory() / ".env"
    load_dotenv(dotenv_path=env_path)

    return psycopg.connect(
        host="localhost",
        port=5432,
        dbname=os.environ["INVEST_POSTGRES_DB"],
        user=os.environ["INVEST_POSTGRES_USER"],
        password=os.environ["INVEST_POSTGRES_PASSWORD"],
        connect_timeout=5,
    )

DISPATCH_RETRY_SECONDS = 300


# Filing Table methods
def upsert_filing_manifest(manifest: FilingManifest, connection: psycopg.Connection | None = None) -> None:
    filing_query: LiteralString = """
        INSERT INTO filings (
        accession_number, cik, ticker, form, filing_date, report_date, primary_document
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (accession_number)
        DO UPDATE SET
            cik = EXCLUDED.cik,
            ticker = EXCLUDED.ticker,
            form = EXCLUDED.form,
            filing_date = EXCLUDED.filing_date,
            report_date = EXCLUDED.report_date,
            primary_document = EXCLUDED.primary_document;
    """

    document_query: LiteralString = """
        INSERT INTO filing_documents (
            accession_number, filename, document_type, source_url, document_sequence,
            download_status, storage_key, downloaded_at, content_type, size_bytes, 
            sha256, last_failed_attempt, last_error
        )
        VALUES(
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s, %s
        )
        ON CONFLICT (accession_number, filename)
        DO UPDATE SET
            document_type = EXCLUDED.document_type,
            source_url = EXCLUDED.source_url,
            document_sequence = EXCLUDED.document_sequence
    """

    filing: Filing = manifest.filing

    filing_value = (
        filing.accession_number,
        filing.cik,
        filing.ticker,
        filing.form,
        filing.filing_date,
        filing.report_date or None,
        filing.primary_document,
    )

    document_values = [
        (
            filing.accession_number,
            document.filename,
            document.document_type,
            document.source_url,
            document.document_sequence,
            document.download_status,
            document.storage_key,
            document.downloaded_at or None,
            document.content_type,
            document.size_bytes,
            document.sha256,
            document.last_failed_attempt or None,
            document.last_error,
        ) for document in manifest.documents
    ]
    if connection is None:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(filing_query, filing_value)
                cursor.executemany(document_query, document_values)
    else:
        with connection.cursor() as cursor:
            cursor.execute(filing_query, filing_value)
            cursor.executemany(document_query, document_values)

# filing_documents table methods
def mark_document_downloading(accession_number: str, filename: str) -> None:
    query: LiteralString = """
        UPDATE filing_documents
        SET
            download_status = 'downloading',
            storage_key = NULL,
            downloaded_at = NULL,
            content_type = NULL,
            size_bytes = NULL,
            sha256 = NULL,
            last_error = NULL
        WHERE
            accession_number = %s AND filename = %s;
    """

    with get_connection() as downloading_connection:
        with downloading_connection.cursor() as downloading_cursor:
            downloading_cursor.execute(query, (accession_number, filename))
            if downloading_cursor.rowcount != 1:
                raise ValueError(
                    "Expected exactly one document row for "
                    f"{accession_number}/{filename}, "
                    f"but updated {downloading_cursor.rowcount}"
                )

def mark_document_downloaded(accession_number: str, filename: str, storage_key: str, downloaded_at: str, content_type: str,
                             size_bytes: int, sha256: str) -> None:
    query: LiteralString = """
        UPDATE filing_documents
        SET
            download_status = 'downloaded',
            storage_key = %s,
            downloaded_at = %s,
            content_type = %s,
            size_bytes = %s,
            sha256 = %s,
            last_error = NULL
        WHERE
            accession_number = %s
            AND filename = %s
            AND download_status = 'downloading'
    """

    values = (
        storage_key,
        downloaded_at,
        content_type,
        size_bytes,
        sha256,
        accession_number,
        filename,
    )

    with get_connection() as downloaded_connection:
        with downloaded_connection.cursor() as downloaded_cursor:
            downloaded_cursor.execute(query, values)

            if downloaded_cursor.rowcount != 1:
                raise ValueError(
                    "Expected exactly one downloading document for "
                    f"{accession_number}/{filename}, "
                    f"but updated {downloaded_cursor.rowcount}"
                )

def mark_document_failed(accession_number: str, filename: str, last_failed_attempt: str,
                         last_error: str,) -> None:
    query: LiteralString = """
        UPDATE filing_documents
        SET
            download_status = 'failed',
            storage_key = NULL,
            downloaded_at = NULL,
            content_type = NULL,
            size_bytes = NULL,
            sha256 = NULL,
            last_failed_attempt = %s,
            last_error = %s
        WHERE
            accession_number = %s
            AND filename = %s
            AND download_status = 'downloading'
    """

    values = (
        last_failed_attempt,
        last_error,
        accession_number,
        filename,
    )

    with get_connection() as failed_connection:
        with failed_connection.cursor() as failed_cursor:
            failed_cursor.execute(query, values)

            if failed_cursor.rowcount != 1:
                raise ValueError(
                    "Expected exactly one downloading document for "
                    f"{accession_number}/{filename}, "
                    f"but updated {failed_cursor.rowcount}"
                )

# download_jobs table methods
def create_download_job(accession_number: str, manifest_key: str,
                        connection: psycopg.Connection) -> int:
    query: LiteralString = """
        INSERT INTO download_jobs (
            accession_number, manifest_key
        )
        VALUES(%s, %s)
        ON CONFLICT (accession_number)
        DO UPDATE SET
            updated_at = CURRENT_TIMESTAMP
        RETURNING job_id
    """

    reopen_query: LiteralString = """
            UPDATE download_jobs AS job
            SET status = 'pending',
                attempt_count = 0,
                queued_at = NULL,
                started_at = NULL,
                completed_at = NULL,
                last_failed_at = NULL,
                last_error = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE job.job_id = %s
              AND job.status = 'completed'
              AND EXISTS (
                  SELECT 1
                  FROM filing_documents AS document
                  WHERE document.accession_number = job.accession_number
                    AND document.download_status <> 'downloaded'
              )
        """

    with connection.cursor() as job_cursor:
        job_cursor.execute(query, (accession_number, manifest_key))
        row = job_cursor.fetchone()
        if row is None:
            raise RuntimeError("PostgreSQL did not return a download job ID")
        job_id = row[0]
        job_cursor.execute(reopen_query, (job_id,))
    return job_id


def mark_download_job_queued(job_id: int) -> bool:
    query: LiteralString = """
    UPDATE download_jobs
    SET
        status = 'queued',
        queued_at = CURRENT_TIMESTAMP,
        updated_at = CURRENT_TIMESTAMP
        WHERE job_id = %s
          AND (
              status = 'pending'
              OR (
                  status = 'queued'
                  AND queued_at <= CURRENT_TIMESTAMP
                      - (%s * INTERVAL '1 second')
              )
          )
        RETURNING job_id
    """

    with get_connection() as queued_connection:
        with queued_connection.cursor() as queued_cursor:
            queued_cursor.execute(
                query,
                (job_id, DISPATCH_RETRY_SECONDS),
            )
            return queued_cursor.fetchone() is not None

def get_download_job(job_id: int) -> DownloadJob | None:
    query: LiteralString = """
        SELECT
            job_id,
            accession_number,
            manifest_key,
            status,
            attempt_count
        FROM download_jobs
        WHERE job_id = %s
    """

    with get_connection() as job_connection:
        with job_connection.cursor() as job_cursor:
            job_cursor.execute(query, (job_id,))
            row = job_cursor.fetchone()

    if row is None:
        return None

    return DownloadJob(
        job_id=row[0],
        accession_number=row[1],
        manifest_key=row[2],
        status=row[3],
        attempt_count=row[4],
    )

def claim_download_job_processing(job_id: int) -> bool:
    query: LiteralString = """
        UPDATE download_jobs
        SET
            status = 'processing',
            attempt_count = attempt_count + 1,
            started_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP,
            completed_at = NULL,
            last_error = NULL
        WHERE
            job_id = %s
            AND status = 'queued'
    """

    with get_connection() as processing_connection:
        with processing_connection.cursor() as processing_cursor:
            processing_cursor.execute(query, (job_id,))
            return processing_cursor.rowcount == 1
            # if processing_cursor.rowcount != 1:
            #     raise ValueError(
            #         f"Expected one queued job with ID {job_id}, "
            #         f"but updated {processing_cursor.rowcount}"
            #     )

def mark_download_job_completed(job_id: int) -> None:
    lock_query: LiteralString = """
            SELECT accession_number
            FROM download_jobs
            WHERE job_id = %s
              AND status = 'processing'
            FOR UPDATE
        """
    unfinished_query: LiteralString = """
            SELECT EXISTS (
                SELECT 1
                FROM filing_documents
                WHERE accession_number = %s
                  AND download_status <> 'downloaded'
            )
        """

    query: LiteralString = """
        UPDATE download_jobs
        SET
            status = 'completed',
            completed_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP,
            last_error = NULL
        WHERE
            job_id = %s
            AND status = 'processing'
    """
    with get_connection() as completed_connection:
        with completed_connection.cursor() as completed_cursor:
            completed_cursor.execute(query, (job_id,))

            if completed_cursor.rowcount != 1:
                raise ValueError(
                    f"Expected one processing job with ID {job_id}, "
                    f"but updated {completed_cursor.rowcount}"
                )

def mark_download_job_failed(job_id: int, last_error: str) -> None:
    query: LiteralString = """
        UPDATE download_jobs
        SET
            status = 'failed',
            last_failed_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP,
            last_error = %s
        WHERE
            job_id= %s
            AND status = 'processing'
    """

    with get_connection() as failed_connection:
        with failed_connection.cursor() as failed_cursor:
            failed_cursor.execute(query, (last_error, job_id))
            if failed_cursor.rowcount != 1:
                raise ValueError(
                    f"Expected one processing job with ID {job_id}, "
                    f"but updated {failed_cursor.rowcount}"
                )

def get_filing_manifest(accession_number: str) -> FilingManifest | None:
    filing_query: LiteralString = """
        SELECT
            cik, ticker, form, filing_date, report_date, accession_number, primary_document
        FROM filings
        WHERE accession_number = %s
    """

    documents_query: LiteralString = """
        SELECT
            filename, document_type, source_url, document_sequence, 
            download_status, storage_key, downloaded_at, content_type, 
            size_bytes, sha256, last_failed_attempt, last_error
        FROM filing_documents
        WHERE accession_number = %s
        ORDER BY document_sequence NULLS LAST, filename
    """

    with get_connection() as manifest_connection:
        with manifest_connection.cursor() as manifest_cursor:
            manifest_cursor.execute(filing_query, (accession_number,))
            filing_row = manifest_cursor.fetchone()

            if filing_row is None:
                return None
            manifest_cursor.execute(documents_query, (accession_number,))
            document_rows = manifest_cursor.fetchall()

    filing = Filing(
        cik=filing_row[0], ticker=filing_row[1], form=filing_row[2], filing_date=filing_row[3].isoformat(),
        report_date=(
            filing_row[4].isoformat()
            if filing_row[4] is not None
            else None
        ),
        accession_number=filing_row[5], primary_document=filing_row[6],
    )

    documents = [
        FilingDocument(
            filename=row[0], document_type=row[1], source_url=row[2],
            document_sequence=row[3], download_status=row[4], storage_key=row[5],
            downloaded_at=(
                row[6].isoformat()
                if row[6] is not None
                else None
            ),
            content_type=row[7], size_bytes=row[8], sha256=row[9],
            last_failed_attempt=(
                row[10].isoformat()
                if row[10] is not None
                else None
            ),
            last_error=row[11],
        ) for row in document_rows
    ]
    return FilingManifest(filing=filing, documents=documents)

def get_download_jobs_to_dispatch(limit: int = 100) -> list[int]:
    if limit < 1:
        raise ValueError("limit must be greater than zero")
    query: LiteralString = """
        SELECT job_id
        FROM download_jobs
        WHERE status = 'pending'
            OR (
                status = 'queued'
                AND queued_at <= CURRENT_TIMESTAMP - (%s * INTERVAL '1 second')
            )
        ORDER BY created_at, job_id
        LIMIT %s
    """
    with get_connection() as dispatch_connection:
        with dispatch_connection.cursor() as dispatch_cursor:
            dispatch_cursor.execute(query, (DISPATCH_RETRY_SECONDS, limit))
            return [int(row[0]) for row in dispatch_cursor.fetchall()]

if __name__ == "__main__":
    with get_connection() as db_connection:
        with db_connection.cursor() as db_cursor:
            db_cursor.execute("SELECT current_database(), current_user")
            result = db_cursor.fetchone()
            print(result)
