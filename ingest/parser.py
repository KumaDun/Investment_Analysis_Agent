from docling.document_converter import DocumentConverter
from directories import get_filing_directory

converter = DocumentConverter()

def parse(ticker: str):
    filings_sec_directory = get_filing_directory()
    source_directory = filings_sec_directory / ticker.upper()
    if not source_directory.is_dir():
        raise FileNotFoundError(f"Directory not found: {source_directory}")

    for source_path in sorted(source_directory.rglob("*")):
        if not source_path.is_file():
            continue

        if source_path.suffix.lower() not in {".htm", ".html"}:
            continue

        print("Parsing:", source_path.name)

        result = converter.convert(source_path)
        document = result.document
        markdown = document.export_to_markdown()

        output_path = source_path.with_suffix(".md")
        output_path.write_text(markdown, encoding="utf-8")

        print("Saved:", output_path)

