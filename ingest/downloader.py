import hashlib
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from directories import get_filing_directory
from ingest.models import (
    DocumentDownloadResult,
    FilingDocument,
)
from ingest.sec_client import fetch_url

def write_file_atomically(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None

    try:
        with tempfile.NamedTemporaryFile(
            dir=path.parent,
            prefix=".ingest-",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            temporary_file.write(content)

        temporary_path.replace(path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def resolve_document_location(filing_directory: Path, filename: str,) -> tuple[Path, str]:
    storage_root = get_filing_directory().resolve()
    resolved_filing_directory = filing_directory.resolve()

    if not resolved_filing_directory.is_relative_to(storage_root):
        raise ValueError(
            f"Filing directory {resolved_filing_directory} "
            f"is outside storage root {storage_root}"
        )

    document_path = (resolved_filing_directory / filename).resolve()

    if (document_path == resolved_filing_directory or
            not document_path.is_relative_to(resolved_filing_directory)):
        raise ValueError(
            f"Document path {document_path} "
            f"is outside filing directory "
            f"{resolved_filing_directory}"
        )

    manifest_path = (resolved_filing_directory / "filing.json").resolve()

    if document_path == manifest_path:
        raise ValueError(
            "Document cannot overwrite filing.json"
        )

    storage_key = document_path.relative_to(storage_root).as_posix()

    return document_path, storage_key


def calculate_file_sha256(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)

    return digest.hexdigest()


def is_document_file_valid(document: FilingDocument, filing_directory: Path,) -> bool:
    if document.download_status != "downloaded":
        return False

    document_path, storage_key = resolve_document_location(filing_directory, document.filename,)

    if not document_path.is_file():
        return False
    if document.storage_key != storage_key:
        return False
    if document.size_bytes is None:
        return False
    if document_path.stat().st_size != document.size_bytes:
        return False
    if document.sha256 is None:
        return False

    return calculate_file_sha256(document_path) == document.sha256


def download_document(document: FilingDocument, filing_directory: Path, headers: dict[str, str],) -> DocumentDownloadResult:
    document_path, storage_key = resolve_document_location(filing_directory, document.filename,)

    time.sleep(0.5)
    content, content_type = fetch_url(document.source_url, headers,)

    if document_path.suffix.lower() in {".htm", ".html"}:
        if "html" not in content_type.lower():
            raise ValueError(
                f"Expected HTML but received {content_type}"
            )

    write_file_atomically(document_path, content)

    return DocumentDownloadResult(
        storage_key=storage_key,
        downloaded_at=datetime.now(
            timezone.utc
        ).isoformat(),
        content_type=content_type,
        size_bytes=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
    )
