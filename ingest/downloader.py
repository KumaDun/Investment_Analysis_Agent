import gzip
import json
import time
from urllib.request import Request, urlopen
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import asdict, dataclass
from directories import get_root_directory

@dataclass
class Filing:
    cik: str
    ticker: str
    form: str
    filing_date: str
    report_date: str
    accession_number: str
    primary_document: str

def fetch_url(url, headers):
    request = Request(url, headers = headers)
    with urlopen(request, timeout=30) as response:
        content = response.read()
        content_encoding = response.headers.get("Content-Encoding")

        if content_encoding == "gzip":
            content = gzip.decompress(content)
        content_type = response.headers.get("Content-Type", "")
    return content, content_type

def build_filing_url(filing: Filing) -> str:
    cik_for_url = str(int(filing.cik))
    accession_for_url = filing.accession_number.replace("-", "")
    document_name = filing.primary_document
    return (
        "https://www.sec.gov/Archives/edgar/data/"
        f"{cik_for_url}/{accession_for_url}/{document_name}"
    )

def download_filing(filing: Filing, headers: dict, filings_directory: Path):
    filing_url = build_filing_url(filing)
    content, content_type = fetch_url(filing_url, headers)

    if "html" not in content_type.lower():
        raise ValueError(f"Expected HTML but received {content_type}")

    # A slash in an amended form, such as 10-Q/A, must not create another folder.
    safe_form = filing.form.replace("/", "-")
    filing_directory = (
        filings_directory / filing.ticker
        / f"{safe_form}_{filing.accession_number}"
    )

    filing_directory.mkdir(parents=True, exist_ok=True)
    document_path = filing_directory / filing.primary_document

    document_path.write_bytes(content)

    # asdict converts the Filing object into values that JSON can serialize.
    metadata = {
        **asdict(filing),
        "source_url": filing_url,
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
        "content_type": content_type,
        "size_bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
    }
    metadata_path = filing_directory / "filing.json"
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata

def select_quarterly_filings(recent: dict, cik: str, ticker: str, num: int) -> list[Filing]:
    filings = []
    for index in range(len(recent["form"])):
        filing = Filing(
            cik=cik,
            ticker=ticker,
            form=recent["form"][index],
            filing_date=recent["filingDate"][index],
            report_date=recent["reportDate"][index],
            accession_number=recent["accessionNumber"][index],
            primary_document=recent["primaryDocument"][index],
        )
        if filing.form == "10-Q":
            filings.append(filing)

    filings.sort(
        key=lambda filing: (filing.report_date, filing.filing_date),
        reverse=True,
    )

    selected_filings = []
    seen_periods = set()
    for filing in filings:
        if not filing.report_date or filing.report_date in seen_periods:
            continue
        selected_filings.append(filing)
        seen_periods.add(filing.report_date)
        if len(selected_filings) == num:
            break

    if len(selected_filings) < num:
        print("The recent filing history contains fewer than four 10-Q periods.")
    return selected_filings


def download_filings_by_ticker(ticker: str, filings_directory: Path):
    """Download Disney's selected filings into the directory supplied by main.py."""
    headers = {
        "User-Agent": "InvestAnalysis/0.1 xuyun.lake@gmail.com",
        "Accept-Encoding": "gzip",
    }
    content, _ = fetch_url("https://www.sec.gov/files/company_tickers.json", headers)
    companies = json.loads(content)

    disney = None
    for company in companies.values():
        if company["ticker"] == ticker:
            disney = company
            break
    if disney is None:
        raise ValueError("Disney was not found in the SEC company directory.")

    cik = str(disney["cik_str"]).zfill(10)
    time.sleep(0.5)
    submissions_url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    content, _ = fetch_url(submissions_url, headers)
    submissions = json.loads(content)
    selected_filings = select_quarterly_filings(
        submissions["filings"]["recent"], cik, ticker, 4
    )

    for filing in selected_filings:
        time.sleep(0.5)
        metadata = download_filing(filing, headers, filings_directory)
        print("Downloaded:", filing.form, filing.report_date,
              metadata["size_bytes"], "bytes")

def main():
    root_directory = get_root_directory()
    download_filings_by_ticker("DIS", root_directory/"filings"/"sec")

if __name__ == "__main__":
    main()
