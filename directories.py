from pathlib import Path

HEADERS = {
    "User-Agent": "InvestAnalysis/0.1 xuyun.lake@gmail.com",
    "Accept-Encoding": "gzip",
}

def get_root_directory():
    return Path(__file__).resolve().parent

def get_filing_directory():
    return Path(__file__).resolve().parent/"filings"/"sec"

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