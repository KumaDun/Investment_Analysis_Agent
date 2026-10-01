from dataclasses import dataclass

@dataclass
class Filing:
    cik: str
    ticker: str
    form: str
    filing_date: str
    report_date: str | None
    accession_number: str
    primary_document: str

@dataclass
class FilingDocument:
    filename: str
    document_type: str
    source_url: str
    document_sequence: int | None = None
    download_status: str = "pending"
    storage_key: str | None = None
    downloaded_at: str | None = None
    content_type: str | None = None
    size_bytes: int | None = None
    sha256: str | None = None
    last_failed_attempt: str | None = None
    last_error: str | None = None

@dataclass
class FilingManifest:
    filing: Filing
    documents: list[FilingDocument]

@dataclass(frozen=True)
class DownloadJob:
    job_id: int
    accession_number: str
    manifest_key: str
    status: str
    attempt_count: int

@dataclass(frozen=True)
class DocumentDownloadResult:
    storage_key: str
    downloaded_at: str
    content_type: str
    size_bytes: int
    sha256: str
