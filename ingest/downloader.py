import json
import time
import hashlib
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import asdict

from directories import get_filing_directory
from ingest.models import Filing, FilingManifest, FilingDocument
from ingest.sec_client import fetch_url

"""
Write new content to a temporary file and then rename it to the final destination.
Separate from scanner.py because scanner preserves the older existing file
"""

HEADERS = {
        "User-Agent": "InvestAnalysis/0.1 xuyun.lake@gmail.com",
        "Accept-Encoding": "gzip",
    }

def load_manifest(metadata_path: Path) -> FilingManifest:
    saved = json.loads(metadata_path.read_text(encoding="utf-8"))
    return FilingManifest(
        filing = Filing(**saved["filing"]),
        documents= [FilingDocument(**item) for item in saved["documents"]]
    )

def write_file_atomically(path: Path, content: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None

    try:
        with tempfile.NamedTemporaryFile(
            dir = path.parent,
            prefix=".ingest-",
            suffix = ".tmp",
            delete = False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            temporary_file.write(content)

        temporary_path.replace(path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)

def save_manifest(manifest: FilingManifest, metadata_path: Path) -> None:
    content = json.dumps(asdict(manifest), indent=2).encode("utf-8")
    write_file_atomically(metadata_path, content)

"""
Download
"""

def download_document(manifest: FilingManifest, document: FilingDocument, metadata_path: Path, headers: dict) -> None:
    storage_root = get_filing_directory().resolve()
    filing_directory = metadata_path.resolve().parent

    document_path = (filing_directory / document.filename).resolve()

    if not filing_directory.is_relative_to(storage_root):
        raise ValueError(f" Manifest's path is {filing_directory}. It is not within the storage root {storage_root}")

    if (document_path == filing_directory) or not document_path.is_relative_to(filing_directory):
        raise ValueError(f"Document path {document_path} is not within the filing directory {filing_directory}")

    if document_path == metadata_path.resolve():
        raise ValueError(
            "Document cannot overwrite its manifest"
        )

    storage_key = document_path.relative_to(storage_root).as_posix()

    # Skip a completed download only when its local file still matches.
    if (
            document.download_status == "downloaded"
            and document_path.is_file()
            and document.storage_key == storage_key
            and document_path.stat().st_size == document.size_bytes
    ):
        current_hash = hashlib.sha256(
            document_path.read_bytes()
        ).hexdigest()

        if current_hash == document.sha256:
            return

    document.download_status = "downloading"
    document.storage_key = None
    document.downloaded_at = None
    document.content_type = None
    document.size_bytes = None
    document.sha256 = None
    document.last_error = None

    save_manifest(manifest, metadata_path)

    try:
        time.sleep(0.5)
        content, content_type = fetch_url(document.source_url, headers)

        if document_path.suffix.lower() in {".htm", ".html"}:
            if "html" not in content_type.lower():
                raise ValueError(f"Expected HTML but received {content_type}")

        write_file_atomically(document_path, content)

    except (OSError, ValueError, EOFError) as error:
        document.download_status = "failed"
        document.last_failed_attempt = (
            datetime.now(timezone.utc).isoformat()
        )
        document.last_error = f"{type(error).__name__}:{error}"
        save_manifest(manifest, metadata_path)
        return

    document.download_status = "downloaded"
    document.storage_key = storage_key
    document.downloaded_at = datetime.now(timezone.utc).isoformat()
    document.content_type = content_type
    document.size_bytes = len(content)
    document.sha256 = hashlib.sha256(content).hexdigest()

    save_manifest(manifest, metadata_path)

def download_from_manifest(metadata_path: Path, headers: dict) -> FilingManifest:
    metadata_path = metadata_path.resolve()
    manifest = load_manifest(metadata_path)

    for document in manifest.documents:
        download_document(manifest, document, metadata_path, headers)
        print(
            document.filename,
            document.download_status,
            document.last_error or "",
        )

    return manifest

def main():
    metadata_path = (
        get_filing_directory()/"DIS"/"10-Q_0001744489-26-000057"/"filing.json"
    )
    download_from_manifest(metadata_path, headers = HEADERS)

if __name__ == "__main__":
    main()
