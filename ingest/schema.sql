CREATE TABLE IF NOT EXISTS filings (
    accession_number VARCHAR(20) PRIMARY KEY
        CHECK (accession_number ~ '^[0-9]{10}-[0-9]{2}-[0-9]{6}$'),
    cik VARCHAR(10) NOT NULL
        CHECK (cik ~ '^[0-9]{10}$'),
    ticker TEXT NOT NULL,
    form TEXT NOT NULL,
    filing_date DATE NOT NULL,
    report_date DATE,
    primary_document TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE filings
    ADD COLUMN IF NOT EXISTS selection_status TEXT
        NOT NULL DEFAULT 'pending'
        CHECK (selection_status IN ('pending', 'selected', 'ignored')),
    ADD COLUMN IF NOT EXISTS selection_reason TEXT,
    ADD COLUMN IF NOT EXISTS selection_policy_version TEXT,
    ADD COLUMN IF NOT EXISTS selection_at TIMESTAMPTZ;


CREATE TABLE IF NOT EXISTS filing_documents (
    accession_number VARCHAR(20)
        REFERENCES filings (accession_number)
        ON DELETE CASCADE,

    filename TEXT NOT NULL,
    document_type TEXT NOT NULL,
    source_url TEXT NOT NULL,
    document_sequence INTEGER
        CHECK (
            document_sequence IS NULL
            or document_sequence > 0
        ),
    selection_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (selection_status IN ('pending', 'selected', 'ignored')),
    download_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (download_status IN ('pending', 'downloading', 'downloaded', 'failed')),
    storage_key TEXT,
    downloaded_at TIMESTAMPTZ,
    content_type TEXT,
    size_bytes BIGINT
        CHECK(
            size_bytes IS NULL
            or size_bytes >= 0
        ),
    sha256 VARCHAR(64)
        CHECK(
            sha256 IS NULL
            or sha256 ~ '^[0-9a-f]{64}$'
        ),
    last_failed_attempt TIMESTAMPTZ,
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (accession_number, filename)
);