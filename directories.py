from pathlib import Path

def get_root_directory():
    return Path(__file__).resolve().parent

def get_filing_directory():
    return Path(__file__).resolve().parent/"filings"/"sec"