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

if __name__ == "__main__":
    with get_connection() as db_connection:
        with db_connection.cursor() as db_cursor:
            db_cursor.execute("SELECT current_database(), current_user")
            result = db_cursor.fetchone()
            print(result)
