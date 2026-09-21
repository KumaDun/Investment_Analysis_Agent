"""
Data models:
Scan for filing metadata
Each filing has a unique accession number
Each filing has a primary document
Each filing has multiple documents
Each document has a file name (uniqueness is not guanranted)
Define in /ingest/models

Workflow:
Scan for filing -> Visit the page to crawl documents information -> Write metadata -> Call external methods to download documents
"""

import json
import time
from dataclasses import asdict
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlsplit

from ingest.database import upsert_filing_manifest

from bs4 import BeautifulSoup

from directories import get_root_directory
from ingest.models import Filing, FilingDocument, FilingManifest
from ingest.sec_client import fetch_url

HEADERS = {
        "User-Agent": "InvestAnalysis/0.1 xuyun.lake@gmail.com",
        "Accept-Encoding": "gzip",
    }

def select_quarterly_filings(recent: dict, cik: str, ticker: str, limit: int = 4, headers: dict = HEADERS) -> list[Filing]:
    if limit < 1:
        raise ValueError("limit must be greater than 0")
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
        key=lambda one_filing: (one_filing.report_date, one_filing.filing_date),
        reverse=True,
    )

    selected_filings = []
    seen_periods = set()
    for filing in filings:
        if not filing.report_date or filing.report_date in seen_periods:
            continue

        metadata_path = make_filing_metadata_directory(filing)
        time.sleep(0.5)
        documents: list[FilingDocument] = discover_documents(filing, headers)

        # TODO atomicity across file system and database.
        # It is hard to guarantee immediate consistency across two systems
        # will adjust the order of two calls after database's implementation is finished
        manifest = save_filing_metadata(filing, documents, metadata_path)
        upsert_filing_manifest(manifest)

        selected_filings.append(filing)
        seen_periods.add(filing.report_date)
        if len(selected_filings) == limit:
            break

    if len(selected_filings) < limit:
        print(
            f"The recent filing history contains fewer than {limit} "
            "distinct 10-Q reporting periods."
        )
    return selected_filings

def save_filing_metadata(filing: Filing, documents: list[FilingDocument], metadata_path: Path) -> FilingManifest:
    existing_documents: dict[str, FilingDocument] = {}
    if metadata_path.exists():
        saved = json.loads(metadata_path.read_text(encoding="utf-8"))
        if saved["filing"]["accession_number"] != filing.accession_number:
            raise ValueError(
                f"Accession number mismatch: {filing.accession_number} != {saved["filing"]['accession_number']}"
            )

        for item in saved["documents"]:
            existing_documents[item["filename"]] = FilingDocument(**item)

    # Keep existing records unchanged; add newly discovered documents
    for document in documents:
        if document.filename not in existing_documents:
            existing_documents[document.filename] = document

    manifest = FilingManifest(filing=filing, documents=list(existing_documents.values()))
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = metadata_path.with_suffix(".json.tmp")

    try:
        temporary_path.write_text(
            json.dumps(asdict(manifest), indent=2),
            encoding="utf-8"
        )
        temporary_path.replace(metadata_path)
    finally:
        temporary_path.unlink(missing_ok=True)
    return manifest


def scan_matched_tickers_by_tickers(tickers: list[str], headers: dict = HEADERS) -> list[dict]:
    tickers = [ticker.strip().upper() for ticker in tickers]
    tickers_set = {ticker.strip().upper() for ticker in tickers}

    content, _ = fetch_url(
        "https://www.sec.gov/files/company_tickers.json",
        headers,
    )

    companies = json.loads(content)

    matched_companies = []

    for company in companies.values():
        if company["ticker"] in tickers_set:
            matched_companies.append(company)

    if len(matched_companies) == 0:
        raise ValueError("No companies found with the provided tickers.")

    return matched_companies

def make_filing_metadata_directory(filing: Filing) -> Path:
    root_directory = get_root_directory()
    filings_directory = root_directory/"filings"/"sec"
    safe_form = filing.form.replace("/", "-")
    filing_directory = (
            filings_directory / filing.ticker
            / f"{safe_form}_{filing.accession_number}"
    )
    filing_directory.mkdir(parents=True, exist_ok=True)
    metadata_path = filing_directory / "filing.json"
    return metadata_path

def discover_documents(filing: Filing, headers: dict = HEADERS) -> list[FilingDocument]:
    cik = str(int(filing.cik))
    accession = filing.accession_number.replace("-", "")
    base_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/"
    index_url = f"{base_url}{filing.accession_number}-index.htm"
    content, content_type = fetch_url(index_url, headers)

    if "html" not in content_type.lower():
        raise ValueError(
            f"Expected filing index HTML, received {content_type}"
        )

    soup = BeautifulSoup(content, "html.parser")

    documents: list[FilingDocument] = []
    seen_filenames = set()

    for row in soup.select("table.tableFile tr"):
        cells = row.find_all("td")

        if len(cells) != 5:
            continue

        sequence = cells[0].get_text(strip = True)

        if not sequence.isdigit():
            continue

        link = cells[2].find("a", href=True)

        if link is None:
            raise ValueError("No link found in filing index table")

        filename = link.get_text(strip=True)

        if filename in seen_filenames:
            continue

        href = str(link["href"])
        document_href = parse_qs(urlsplit(href).query).get("doc", [href])[0]

        source_url = urljoin(base_url, document_href)

        document = FilingDocument(
            filename = filename,
            document_type = cells[3].get_text(strip=True),
            source_url = source_url,
            document_sequence=int(sequence)
        )
        documents.append(document)
        seen_filenames.add(filename)

    if filing.primary_document not in seen_filenames:
        raise ValueError(f"Primary document {filing.primary_document} missing from index")
    return documents


def scan_filings_by_tickers(tickers: list[str], headers: dict,limit: int = 4) -> list[Filing]:
    if limit < 1:
        raise ValueError("limit must be greater than 0")

    matched_companies = scan_matched_tickers_by_tickers(tickers,headers)
    matched_filings: list[Filing] = []

    for company in matched_companies:
        cik = str(company["cik_str"]).zfill(10)
        time.sleep(0.5)
        submissions_url = (
            f"https://data.sec.gov/submissions/CIK{cik}.json"
        )
        content, _ = fetch_url(submissions_url, headers)
        submissions = json.loads(content)

        company_filings = select_quarterly_filings(submissions["filings"]["recent"],cik,company["ticker"],limit, headers=headers)
        matched_filings.extend(company_filings)

    return matched_filings

def main():
    tickers = ["DIS", "NVDA"]
    headers = HEADERS
    limit = 4
    scan_filings_by_tickers(tickers, headers, limit)

if __name__ == "__main__":
    main()