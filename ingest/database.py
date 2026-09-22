import os
from typing import LiteralString

import psycopg
from dotenv import load_dotenv

from directories import get_root_directory

from ingest.models import Filing, FilingManifest

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

def upsert_filing_manifest(manifest: FilingManifest) -> None:
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

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(filing_query, filing_value)
            cursor.executemany(document_query, document_values)

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

def create_download_job(accession_number: str, manifest_key: str) -> int:
    query: LiteralString = """
        INSERT INTO download_jobs (
            accession_number, manifest_key
        )
        VALUES(%s, %s)
        ON CONFLICT (accession_number)
        DO UPDATE SET
            manifest_key = EXCLUDED.manifest_key,
            updated_at = CURRENT_TIMESTAMP
        RETURNING job_id
    """

    with get_connection() as job_connection:
        with job_connection.cursor() as job_cursor:
            job_cursor.execute(query, (accession_number, manifest_key))
            job_result = job_cursor.fetchone()

            if job_result is None:
                raise RuntimeError(
                    "PostgreSQL did not return a download job ID"
                )
            return int(job_result[0])


if __name__ == "__main__":
    with get_connection() as db_connection:
        with db_connection.cursor() as db_cursor:
            db_cursor.execute("SELECT current_database(), current_user")
            result = db_cursor.fetchone()
            print(result)
