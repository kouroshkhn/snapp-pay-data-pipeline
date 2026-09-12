-- ============================================================
-- Snapp Pay Data Pipeline
-- File: 02_create_tables.sql
-- Purpose: Create raw-layer tables
-- ============================================================

BEGIN;

-- ------------------------------------------------------------
-- Table: raw.ingestion_batches
-- Purpose:
-- One row represents one execution of the ETL pipeline.
-- All loaded records, validation issues, and quality metrics
-- will be traceable to a batch_id.
-- ------------------------------------------------------------

CREATE TABLE IF NOT EXISTS raw.ingestion_batches (
    batch_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    pipeline_name TEXT NOT NULL DEFAULT 'snapp_pay_product_pipeline',
    pipeline_version TEXT NOT NULL DEFAULT '1.0.0',

    run_status TEXT NOT NULL DEFAULT 'RUNNING',

    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,

    source_file_count INTEGER NOT NULL DEFAULT 0,
    records_extracted BIGINT NOT NULL DEFAULT 0,
    records_valid BIGINT NOT NULL DEFAULT 0,
    records_quarantined BIGINT NOT NULL DEFAULT 0,
    records_loaded_staging BIGINT NOT NULL DEFAULT 0,
    records_loaded_core BIGINT NOT NULL DEFAULT 0,

    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_ingestion_batches_status
        CHECK (run_status IN ('RUNNING', 'SUCCESS', 'FAILED')),

    CONSTRAINT chk_ingestion_batches_source_file_count
        CHECK (source_file_count >= 0),

    CONSTRAINT chk_ingestion_batches_records_extracted
        CHECK (records_extracted >= 0),

    CONSTRAINT chk_ingestion_batches_records_valid
        CHECK (records_valid >= 0),

    CONSTRAINT chk_ingestion_batches_records_quarantined
        CHECK (records_quarantined >= 0),

    CONSTRAINT chk_ingestion_batches_records_loaded_staging
        CHECK (records_loaded_staging >= 0),

    CONSTRAINT chk_ingestion_batches_records_loaded_core
        CHECK (records_loaded_core >= 0),

    CONSTRAINT chk_ingestion_batches_finished_after_started
        CHECK (finished_at IS NULL OR finished_at >= started_at)
);

COMMENT ON TABLE raw.ingestion_batches IS
'One row per ETL execution batch. Provides end-to-end pipeline traceability.';

COMMENT ON COLUMN raw.ingestion_batches.batch_id IS
'Unique identifier for one ETL pipeline execution.';

COMMENT ON COLUMN raw.ingestion_batches.run_status IS
'Execution status: RUNNING, SUCCESS, or FAILED.';

COMMENT ON COLUMN raw.ingestion_batches.records_quarantined IS
'Count of records rejected from core loading because of ERROR-level validation issues.';


-- ------------------------------------------------------------
-- Table: raw.raw_file_registry
-- Purpose:
-- Stores metadata for every raw input file processed by ETL.
-- Each file belongs to exactly one ingestion batch.
-- ------------------------------------------------------------

CREATE TABLE IF NOT EXISTS raw.raw_file_registry (
    file_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    batch_id BIGINT NOT NULL,

    source_name_raw TEXT NOT NULL,
    dataset_name_raw TEXT,

    original_file_name TEXT NOT NULL,
    relative_file_path TEXT NOT NULL,
    file_extension TEXT NOT NULL,

    file_size_bytes BIGINT,
    file_sha256 TEXT,

    rows_read BIGINT NOT NULL DEFAULT 0,
    file_status TEXT NOT NULL DEFAULT 'DISCOVERED',

    discovered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    loaded_at TIMESTAMPTZ,

    error_message TEXT,

    CONSTRAINT fk_raw_file_registry_batch
        FOREIGN KEY (batch_id)
        REFERENCES raw.ingestion_batches(batch_id)
        ON DELETE RESTRICT,

    CONSTRAINT uq_raw_file_registry_batch_hash
        UNIQUE (batch_id, file_sha256),

    CONSTRAINT chk_raw_file_registry_extension
        CHECK (LOWER(file_extension) IN ('csv', 'xlsx', 'xls', 'parquet')),

    CONSTRAINT chk_raw_file_registry_file_size
        CHECK (file_size_bytes IS NULL OR file_size_bytes >= 0),

    CONSTRAINT chk_raw_file_registry_rows_read
        CHECK (rows_read >= 0),

    CONSTRAINT chk_raw_file_registry_status
        CHECK (file_status IN ('DISCOVERED', 'LOADED', 'FAILED', 'SKIPPED'))
);

COMMENT ON TABLE raw.raw_file_registry IS
'Metadata for each raw input file processed in an ETL ingestion batch.';

COMMENT ON COLUMN raw.raw_file_registry.batch_id IS
'Foreign key to the ETL batch that processed this raw file.';

COMMENT ON COLUMN raw.raw_file_registry.file_sha256 IS
'SHA-256 hash of file content, used to detect the same file within a batch.';

COMMENT ON COLUMN raw.raw_file_registry.relative_file_path IS
'Project-relative path, for example: data/raw/torob_products.csv.';


-- ------------------------------------------------------------
-- Table: raw.raw_product_records
-- Purpose:
-- Stores each original product record from raw CSV/Excel files.
-- The full original row is preserved as JSONB for traceability.
-- ------------------------------------------------------------

CREATE TABLE IF NOT EXISTS raw.raw_product_records (
    raw_record_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    file_id BIGINT NOT NULL,

    source_row_number BIGINT NOT NULL,

    raw_payload JSONB NOT NULL,

    raw_record_hash TEXT,

    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT fk_raw_product_records_file
        FOREIGN KEY (file_id)
        REFERENCES raw.raw_file_registry(file_id)
        ON DELETE RESTRICT,

    CONSTRAINT uq_raw_product_records_file_row
        UNIQUE (file_id, source_row_number),

    CONSTRAINT chk_raw_product_records_row_number
        CHECK (source_row_number >= 1),

    CONSTRAINT chk_raw_product_records_payload_object
        CHECK (jsonb_typeof(raw_payload) = 'object')
);

COMMENT ON TABLE raw.raw_product_records IS
'Original product rows from raw input files, stored as JSONB before transformation.';

COMMENT ON COLUMN raw.raw_product_records.file_id IS
'Foreign key to the raw file that contains this source record.';

COMMENT ON COLUMN raw.raw_product_records.source_row_number IS
'Original one-based row number in the source file, excluding the header row.';

COMMENT ON COLUMN raw.raw_product_records.raw_payload IS
'Complete original row from CSV or Excel, stored as a JSONB object.';

COMMENT ON COLUMN raw.raw_product_records.raw_record_hash IS
'Optional SHA-256 hash of the normalized raw record for traceability and duplicate investigation.';

-- ============================================================
-- STAGING LAYER
-- ============================================================

-- ------------------------------------------------------------
-- Table: staging.stg_product_listings
-- Purpose:
-- Stores standardized product listings after initial extraction,
-- transformation, and cleaning, but before final validation
-- and loading into the core data model.
-- ------------------------------------------------------------

CREATE TABLE IF NOT EXISTS staging.stg_product_listings (
    stg_listing_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    raw_record_id BIGINT NOT NULL,

    source TEXT,
    dataset TEXT,
    source_id TEXT,

    product_title TEXT,
    product_title_normalized TEXT,

    brand_raw TEXT,
    category_raw TEXT,
    merchant_name_raw TEXT,

    price NUMERIC(18, 2),
    old_price NUMERIC(18, 2),
    cash_back NUMERIC(18, 2),
    discount NUMERIC(18, 2),

    availability_raw TEXT,
    is_available BOOLEAN,

    product_url TEXT,
    image_url TEXT,
    search_keyword TEXT,

    transform_status TEXT NOT NULL DEFAULT 'TRANSFORMED',
    transform_notes TEXT,

    transformed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT fk_stg_product_listings_raw_record
        FOREIGN KEY (raw_record_id)
        REFERENCES raw.raw_product_records(raw_record_id)
        ON DELETE RESTRICT,

    CONSTRAINT uq_stg_product_listings_raw_record
        UNIQUE (raw_record_id),

    CONSTRAINT chk_stg_product_listings_transform_status
        CHECK (
            transform_status IN (
                'TRANSFORMED',
                'PARTIAL',
                'FAILED'
            )
        )
);

COMMENT ON TABLE staging.stg_product_listings IS
'Standardized product listings after initial transformation and before final validation and core loading.';

COMMENT ON COLUMN staging.stg_product_listings.raw_record_id IS
'Foreign key to the original raw product record. Ensures full traceability.';

COMMENT ON COLUMN staging.stg_product_listings.source IS
'Standardized source name, for example SnappPay, Torob, Digikala, or Technolife.';

COMMENT ON COLUMN staging.stg_product_listings.source_id IS
'Original product/listing identifier from the source system, stored as text.';

COMMENT ON COLUMN staging.stg_product_listings.product_title_normalized IS
'Normalized product title used for duplicate detection and downstream matching.';

COMMENT ON COLUMN staging.stg_product_listings.is_available IS
'Normalized availability status: TRUE, FALSE, or NULL when unknown.';

COMMENT ON COLUMN staging.stg_product_listings.transform_status IS
'Transformation result: TRANSFORMED, PARTIAL, or FAILED.';

-- ============================================================
-- CORE LAYER
-- ============================================================

-- ------------------------------------------------------------
-- Table: core.dim_sources
-- Purpose:
-- Stores the canonical list of product data sources.
-- ------------------------------------------------------------

CREATE TABLE IF NOT EXISTS core.dim_sources (
    source_key BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    source_code TEXT NOT NULL,
    source_name TEXT NOT NULL,

    source_type TEXT NOT NULL DEFAULT 'UNKNOWN',
    website_url TEXT,

    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_dim_sources_source_code
        UNIQUE (source_code),

    CONSTRAINT uq_dim_sources_source_name
        UNIQUE (source_name),

    CONSTRAINT chk_dim_sources_source_type
        CHECK (
            source_type IN (
                'MARKETPLACE',
                'PRICE_COMPARISON',
                'RETAILER',
                'UNKNOWN'
            )
        )
);

COMMENT ON TABLE core.dim_sources IS
'Canonical reference list of product listing sources.';

COMMENT ON COLUMN core.dim_sources.source_code IS
'Stable machine-readable identifier, for example torob or digikala.';

COMMENT ON COLUMN core.dim_sources.source_name IS
'Human-readable canonical source name used in reports and dashboard.';

COMMENT ON COLUMN core.dim_sources.source_type IS
'Source classification: MARKETPLACE, PRICE_COMPARISON, RETAILER, or UNKNOWN.';

-- ------------------------------------------------------------
-- Table: core.dim_merchants
-- Purpose:
-- Stores canonical merchants/sellers within each data source.
-- A merchant is source-specific in the first version of the model.
-- ------------------------------------------------------------

CREATE TABLE IF NOT EXISTS core.dim_merchants (
    merchant_key BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    source_key BIGINT NOT NULL,

    merchant_name TEXT NOT NULL,
    merchant_name_normalized TEXT NOT NULL,

    merchant_url TEXT,

    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT fk_dim_merchants_source
        FOREIGN KEY (source_key)
        REFERENCES core.dim_sources(source_key)
        ON DELETE RESTRICT,

    CONSTRAINT uq_dim_merchants_source_name_normalized
        UNIQUE (source_key, merchant_name_normalized)
);

COMMENT ON TABLE core.dim_merchants IS
'Canonical source-specific merchant or seller dimension.';

COMMENT ON COLUMN core.dim_merchants.source_key IS
'Source to which the merchant belongs.';

COMMENT ON COLUMN core.dim_merchants.merchant_name IS
'Cleaned merchant name retained for display in dashboard and reports.';

COMMENT ON COLUMN core.dim_merchants.merchant_name_normalized IS
'Normalized merchant name used to prevent duplicates within one source.';

-- ------------------------------------------------------------
-- Table: core.dim_categories
-- Purpose:
-- Stores the canonical hierarchical product category dimension.
-- Categories are shared across sources in the first version.
-- ------------------------------------------------------------

CREATE TABLE IF NOT EXISTS core.dim_categories (
    category_key BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    category_name TEXT NOT NULL,
    category_name_normalized TEXT NOT NULL,

    parent_category_key BIGINT,

    category_level SMALLINT NOT NULL DEFAULT 1,

    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_dim_categories_name_normalized
        UNIQUE (category_name_normalized),

    CONSTRAINT fk_dim_categories_parent
        FOREIGN KEY (parent_category_key)
        REFERENCES core.dim_categories(category_key)
        ON DELETE RESTRICT,

    CONSTRAINT chk_dim_categories_level
        CHECK (category_level BETWEEN 1 AND 5),

    CONSTRAINT chk_dim_categories_not_own_parent
        CHECK (
            parent_category_key IS NULL
            OR parent_category_key <> category_key
        )
);

COMMENT ON TABLE core.dim_categories IS
'Canonical hierarchical product categories shared across all sources.';

COMMENT ON COLUMN core.dim_categories.category_name IS
'Human-readable canonical category name for dashboard and reporting.';

COMMENT ON COLUMN core.dim_categories.category_name_normalized IS
'Normalized canonical category name used for uniqueness and category mapping.';

COMMENT ON COLUMN core.dim_categories.parent_category_key IS
'Optional parent category reference for building category hierarchy.';

COMMENT ON COLUMN core.dim_categories.category_level IS
'Hierarchy depth: 1 is root category, 2 is subcategory, and so on.';


-- ------------------------------------------------------------
-- Table: core.dim_brands
-- Purpose:
-- Stores canonical product brands after standardization.
-- ------------------------------------------------------------

CREATE TABLE IF NOT EXISTS core.dim_brands (
    brand_key BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    brand_name TEXT NOT NULL,
    brand_name_normalized TEXT NOT NULL,

    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_dim_brands_name_normalized
        UNIQUE (brand_name_normalized)
);

COMMENT ON TABLE core.dim_brands IS
'Canonical list of product brands after normalization.';

COMMENT ON COLUMN core.dim_brands.brand_name IS
'Human-readable canonical brand name for dashboard and reporting.';

COMMENT ON COLUMN core.dim_brands.brand_name_normalized IS
'Normalized brand name used to prevent duplicate brand records.';

-- ------------------------------------------------------------
-- Table: core.dim_products
-- Purpose:
-- Stores canonical source-specific product entities.
-- Cross-source product matching is intentionally out of scope
-- for version 1 of this project.
-- ------------------------------------------------------------

CREATE TABLE IF NOT EXISTS core.dim_products (
    product_key BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    source_key BIGINT NOT NULL,

    source_product_id TEXT,

    product_business_key TEXT NOT NULL,

    product_title TEXT NOT NULL,
    product_title_normalized TEXT NOT NULL,

    brand_key BIGINT,
    category_key BIGINT,

    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT fk_dim_products_source
        FOREIGN KEY (source_key)
        REFERENCES core.dim_sources(source_key)
        ON DELETE RESTRICT,

    CONSTRAINT fk_dim_products_brand
        FOREIGN KEY (brand_key)
        REFERENCES core.dim_brands(brand_key)
        ON DELETE RESTRICT,

    CONSTRAINT fk_dim_products_category
        FOREIGN KEY (category_key)
        REFERENCES core.dim_categories(category_key)
        ON DELETE RESTRICT,

    CONSTRAINT uq_dim_products_source_business_key
        UNIQUE (source_key, product_business_key),

    CONSTRAINT chk_dim_products_business_key_not_blank
        CHECK (BTRIM(product_business_key) <> ''),

    CONSTRAINT chk_dim_products_title_not_blank
        CHECK (BTRIM(product_title) <> ''),

    CONSTRAINT chk_dim_products_title_normalized_not_blank
        CHECK (BTRIM(product_title_normalized) <> '')
);

COMMENT ON TABLE core.dim_products IS
'Canonical source-specific product dimension. Cross-source entity resolution is out of scope for the initial version.';

COMMENT ON COLUMN core.dim_products.source_key IS
'Source where this product identity originated.';

COMMENT ON COLUMN core.dim_products.source_product_id IS
'Optional original source identifier, derived from staging.source_id.';

COMMENT ON COLUMN core.dim_products.product_business_key IS
'Stable ETL-generated key used to identify one source-specific product and prevent duplicate products.';

COMMENT ON COLUMN core.dim_products.product_title IS
'Cleaned product title retained for display and reporting.';

COMMENT ON COLUMN core.dim_products.product_title_normalized IS
'Normalized product title used in duplicate detection and fallback product identity.';

COMMENT ON COLUMN core.dim_products.brand_key IS
'Optional reference to canonical product brand.';

COMMENT ON COLUMN core.dim_products.category_key IS
'Optional reference to canonical product category.';

-- ------------------------------------------------------------
-- Table: core.fact_product_listings
-- Purpose:
-- Main fact table containing dashboard-ready product listings,
-- prices, availability, discounts, and data-quality flags.
--
-- Grain:
-- One row = one transformed product listing observation
-- from one staging record in one ETL batch.
-- ------------------------------------------------------------

CREATE TABLE IF NOT EXISTS core.fact_product_listings (
    listing_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    batch_id BIGINT NOT NULL,

    stg_listing_id BIGINT NOT NULL,

    product_key BIGINT NOT NULL,
    merchant_key BIGINT,

    source_listing_id TEXT,

    price NUMERIC(18, 2),
    old_price NUMERIC(18, 2),
    cash_back NUMERIC(18, 2),
    discount NUMERIC(18, 2),

    is_available BOOLEAN,

    product_url TEXT,
    image_url TEXT,
    search_keyword TEXT,

    observed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    validation_status TEXT NOT NULL DEFAULT 'VALID',

    is_duplicate_candidate BOOLEAN NOT NULL DEFAULT FALSE,
    is_price_outlier BOOLEAN NOT NULL DEFAULT FALSE,

    CONSTRAINT fk_fact_product_listings_batch
        FOREIGN KEY (batch_id)
        REFERENCES raw.ingestion_batches(batch_id)
        ON DELETE RESTRICT,

    CONSTRAINT fk_fact_product_listings_staging
        FOREIGN KEY (stg_listing_id)
        REFERENCES staging.stg_product_listings(stg_listing_id)
        ON DELETE RESTRICT,

    CONSTRAINT fk_fact_product_listings_product
        FOREIGN KEY (product_key)
        REFERENCES core.dim_products(product_key)
        ON DELETE RESTRICT,

    CONSTRAINT fk_fact_product_listings_merchant
        FOREIGN KEY (merchant_key)
        REFERENCES core.dim_merchants(merchant_key)
        ON DELETE RESTRICT,

    CONSTRAINT uq_fact_product_listings_staging_record
        UNIQUE (stg_listing_id),

    CONSTRAINT chk_fact_product_listings_price
        CHECK (price IS NULL OR price >= 0),

    CONSTRAINT chk_fact_product_listings_old_price
        CHECK (old_price IS NULL OR old_price >= 0),

    CONSTRAINT chk_fact_product_listings_cash_back
        CHECK (cash_back IS NULL OR cash_back >= 0),

    CONSTRAINT chk_fact_product_listings_discount
        CHECK (discount IS NULL OR discount >= 0),

    CONSTRAINT chk_fact_product_listings_validation_status
        CHECK (
            validation_status IN (
                'VALID',
                'VALID_WITH_WARNINGS'
            )
        )
);

COMMENT ON TABLE core.fact_product_listings IS
'Main dashboard-ready fact table for product listing observations, prices, availability, and quality flags.';

COMMENT ON COLUMN core.fact_product_listings.batch_id IS
'ETL batch that loaded this product listing observation.';

COMMENT ON COLUMN core.fact_product_listings.stg_listing_id IS
'Unique source staging record from which this fact record was created.';

COMMENT ON COLUMN core.fact_product_listings.product_key IS
'Reference to the source-specific canonical product.';

COMMENT ON COLUMN core.fact_product_listings.merchant_key IS
'Optional reference to the source-specific merchant or seller.';

COMMENT ON COLUMN core.fact_product_listings.price IS
'Current observed selling price. NULL means price was missing; zero is retained and flagged by validation.';

COMMENT ON COLUMN core.fact_product_listings.old_price IS
'Previous, regular, or pre-discount price as provided by source.';

COMMENT ON COLUMN core.fact_product_listings.validation_status IS
'VALID means no warning-level issue; VALID_WITH_WARNINGS means record is usable but has one or more warnings.';

COMMENT ON COLUMN core.fact_product_listings.is_duplicate_candidate IS
'TRUE when duplicate detection identifies this listing as a possible duplicate.';

COMMENT ON COLUMN core.fact_product_listings.is_price_outlier IS
'TRUE when price outlier detection identifies this listing as suspicious.';

-- ============================================================
-- AUDIT LAYER
-- ============================================================

-- ------------------------------------------------------------
-- Table: audit.validation_issues
-- Purpose:
-- Stores all data-quality issues detected during ETL validation,
-- duplicate detection, and price outlier detection.
-- ------------------------------------------------------------

CREATE TABLE IF NOT EXISTS audit.validation_issues (
    issue_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    batch_id BIGINT NOT NULL,

    file_id BIGINT,
    raw_record_id BIGINT,
    stg_listing_id BIGINT,
    listing_id BIGINT,

    rule_code TEXT NOT NULL,
    severity TEXT NOT NULL,
    action_taken TEXT NOT NULL,

    field_name TEXT,

    observed_value TEXT,
    issue_message TEXT NOT NULL,

    issue_details JSONB NOT NULL DEFAULT '{}'::JSONB,

    issue_status TEXT NOT NULL DEFAULT 'OPEN',

    detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at TIMESTAMPTZ,
    resolution_note TEXT,

    CONSTRAINT fk_validation_issues_batch
        FOREIGN KEY (batch_id)
        REFERENCES raw.ingestion_batches(batch_id)
        ON DELETE RESTRICT,

    CONSTRAINT fk_validation_issues_file
        FOREIGN KEY (file_id)
        REFERENCES raw.raw_file_registry(file_id)
        ON DELETE RESTRICT,

    CONSTRAINT fk_validation_issues_raw_record
        FOREIGN KEY (raw_record_id)
        REFERENCES raw.raw_product_records(raw_record_id)
        ON DELETE RESTRICT,

    CONSTRAINT fk_validation_issues_staging
        FOREIGN KEY (stg_listing_id)
        REFERENCES staging.stg_product_listings(stg_listing_id)
        ON DELETE RESTRICT,

    CONSTRAINT fk_validation_issues_listing
        FOREIGN KEY (listing_id)
        REFERENCES core.fact_product_listings(listing_id)
        ON DELETE RESTRICT,

    CONSTRAINT chk_validation_issues_severity
        CHECK (
            severity IN (
                'ERROR',
                'WARNING',
                'INFO'
            )
        ),

    CONSTRAINT chk_validation_issues_action
        CHECK (
            action_taken IN (
                'REJECT',
                'QUARANTINE',
                'FLAG',
                'ACCEPT'
            )
        ),

    CONSTRAINT chk_validation_issues_status
        CHECK (
            issue_status IN (
                'OPEN',
                'RESOLVED',
                'IGNORED'
            )
        ),

    CONSTRAINT chk_validation_issues_resolution_time
        CHECK (
            resolved_at IS NULL
            OR resolved_at >= detected_at
        )
);

COMMENT ON TABLE audit.validation_issues IS
'All data validation, duplicate-detection, and outlier-detection issues detected during ETL.';

COMMENT ON COLUMN audit.validation_issues.batch_id IS
'ETL execution batch in which this data-quality issue was detected.';

COMMENT ON COLUMN audit.validation_issues.rule_code IS
'Stable machine-readable validation rule identifier, for example ZERO_PRICE or REQ_TITLE.';

COMMENT ON COLUMN audit.validation_issues.severity IS
'Issue severity: ERROR, WARNING, or INFO.';

COMMENT ON COLUMN audit.validation_issues.action_taken IS
'Pipeline action: REJECT, QUARANTINE, FLAG, or ACCEPT.';

COMMENT ON COLUMN audit.validation_issues.field_name IS
'Name of the column or data field that caused the issue.';

COMMENT ON COLUMN audit.validation_issues.observed_value IS
'Problematic value observed in the source or transformed record.';

COMMENT ON COLUMN audit.validation_issues.issue_details IS
'Optional structured JSON details, for example threshold, median, source, or duplicate group key.';

COMMENT ON COLUMN audit.validation_issues.issue_status IS
'Lifecycle status of the issue: OPEN, RESOLVED, or IGNORED.';

-- ------------------------------------------------------------
-- Table: audit.etl_run_logs
-- Purpose:
-- Stores execution logs for each ETL pipeline stage within a batch.
-- ------------------------------------------------------------

CREATE TABLE IF NOT EXISTS audit.etl_run_logs (
    etl_log_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    batch_id BIGINT NOT NULL,

    stage_name TEXT NOT NULL,
    attempt_number SMALLINT NOT NULL DEFAULT 1,

    stage_status TEXT NOT NULL DEFAULT 'RUNNING',

    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,

    records_input BIGINT NOT NULL DEFAULT 0,
    records_output BIGINT NOT NULL DEFAULT 0,
    records_rejected BIGINT NOT NULL DEFAULT 0,

    error_message TEXT,

    log_details JSONB NOT NULL DEFAULT '{}'::JSONB,

    CONSTRAINT fk_etl_run_logs_batch
        FOREIGN KEY (batch_id)
        REFERENCES raw.ingestion_batches(batch_id)
        ON DELETE RESTRICT,

    CONSTRAINT uq_etl_run_logs_batch_stage_attempt
        UNIQUE (batch_id, stage_name, attempt_number),

    CONSTRAINT chk_etl_run_logs_stage_name
        CHECK (
            stage_name IN (
                'EXTRACT',
                'TRANSFORM',
                'VALIDATE',
                'DEDUPLICATE',
                'OUTLIER_DETECTION',
                'LOAD_RAW',
                'LOAD_STAGING',
                'LOAD_CORE',
                'CALCULATE_METRICS'
            )
        ),

    CONSTRAINT chk_etl_run_logs_status
        CHECK (
            stage_status IN (
                'RUNNING',
                'SUCCESS',
                'FAILED',
                'SKIPPED'
            )
        ),

    CONSTRAINT chk_etl_run_logs_attempt
        CHECK (attempt_number >= 1),

    CONSTRAINT chk_etl_run_logs_records_input
        CHECK (records_input >= 0),

    CONSTRAINT chk_etl_run_logs_records_output
        CHECK (records_output >= 0),

    CONSTRAINT chk_etl_run_logs_records_rejected
        CHECK (records_rejected >= 0),

    CONSTRAINT chk_etl_run_logs_finished_after_started
        CHECK (
            finished_at IS NULL
            OR finished_at >= started_at
        )
);

COMMENT ON TABLE audit.etl_run_logs IS
'Step-level execution logs for ETL pipeline stages within each ingestion batch.';

COMMENT ON COLUMN audit.etl_run_logs.batch_id IS
'ETL execution batch to which this stage log belongs.';

COMMENT ON COLUMN audit.etl_run_logs.stage_name IS
'Pipeline stage name, for example EXTRACT, TRANSFORM, VALIDATE, or LOAD_CORE.';

COMMENT ON COLUMN audit.etl_run_logs.attempt_number IS
'Attempt number for retries of the same stage in the same batch.';

COMMENT ON COLUMN audit.etl_run_logs.stage_status IS
'Current stage execution status: RUNNING, SUCCESS, FAILED, or SKIPPED.';

COMMENT ON COLUMN audit.etl_run_logs.records_input IS
'Number of records received by the ETL stage.';

COMMENT ON COLUMN audit.etl_run_logs.records_output IS
'Number of records successfully produced by the ETL stage.';

COMMENT ON COLUMN audit.etl_run_logs.records_rejected IS
'Number of records rejected or quarantined during this stage.';

COMMENT ON COLUMN audit.etl_run_logs.log_details IS
'Structured JSON details such as source counts, elapsed seconds, or transformation statistics.';

-- ------------------------------------------------------------
-- Table: audit.data_quality_metrics
-- Purpose:
-- Stores pre-calculated data-quality metrics for each source
-- in each ETL batch. Used by dashboard and API reporting.
-- ------------------------------------------------------------

CREATE TABLE IF NOT EXISTS audit.data_quality_metrics (
    metric_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    batch_id BIGINT NOT NULL,
    source_key BIGINT NOT NULL,

    total_records BIGINT NOT NULL DEFAULT 0,

    records_with_title BIGINT NOT NULL DEFAULT 0,
    records_with_positive_price BIGINT NOT NULL DEFAULT 0,
    records_with_zero_price BIGINT NOT NULL DEFAULT 0,
    records_with_null_price BIGINT NOT NULL DEFAULT 0,

    records_with_brand BIGINT NOT NULL DEFAULT 0,
    records_with_category BIGINT NOT NULL DEFAULT 0,

    records_available BIGINT NOT NULL DEFAULT 0,
    records_unavailable BIGINT NOT NULL DEFAULT 0,
    records_availability_unknown BIGINT NOT NULL DEFAULT 0,

    duplicate_candidate_count BIGINT NOT NULL DEFAULT 0,
    price_outlier_count BIGINT NOT NULL DEFAULT 0,

    error_count BIGINT NOT NULL DEFAULT 0,
    warning_count BIGINT NOT NULL DEFAULT 0,
    info_count BIGINT NOT NULL DEFAULT 0,

    calculated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT fk_data_quality_metrics_batch
        FOREIGN KEY (batch_id)
        REFERENCES raw.ingestion_batches(batch_id)
        ON DELETE RESTRICT,

    CONSTRAINT fk_data_quality_metrics_source
        FOREIGN KEY (source_key)
        REFERENCES core.dim_sources(source_key)
        ON DELETE RESTRICT,

    CONSTRAINT uq_data_quality_metrics_batch_source
        UNIQUE (batch_id, source_key),

    CONSTRAINT chk_dq_metrics_total_records
        CHECK (total_records >= 0),

    CONSTRAINT chk_dq_metrics_with_title
        CHECK (
            records_with_title >= 0
            AND records_with_title <= total_records
        ),

    CONSTRAINT chk_dq_metrics_positive_price
        CHECK (
            records_with_positive_price >= 0
            AND records_with_positive_price <= total_records
        ),

    CONSTRAINT chk_dq_metrics_zero_price
        CHECK (
            records_with_zero_price >= 0
            AND records_with_zero_price <= total_records
        ),

    CONSTRAINT chk_dq_metrics_null_price
        CHECK (
            records_with_null_price >= 0
            AND records_with_null_price <= total_records
        ),

    CONSTRAINT chk_dq_metrics_brand
        CHECK (
            records_with_brand >= 0
            AND records_with_brand <= total_records
        ),

    CONSTRAINT chk_dq_metrics_category
        CHECK (
            records_with_category >= 0
            AND records_with_category <= total_records
        ),

    CONSTRAINT chk_dq_metrics_available
        CHECK (
            records_available >= 0
            AND records_available <= total_records
        ),

    CONSTRAINT chk_dq_metrics_unavailable
        CHECK (
            records_unavailable >= 0
            AND records_unavailable <= total_records
        ),

    CONSTRAINT chk_dq_metrics_availability_unknown
        CHECK (
            records_availability_unknown >= 0
            AND records_availability_unknown <= total_records
        ),

    CONSTRAINT chk_dq_metrics_duplicate_candidates
        CHECK (
            duplicate_candidate_count >= 0
            AND duplicate_candidate_count <= total_records
        ),

    CONSTRAINT chk_dq_metrics_price_outliers
        CHECK (
            price_outlier_count >= 0
            AND price_outlier_count <= total_records
        ),

    CONSTRAINT chk_dq_metrics_errors
        CHECK (
            error_count >= 0
            AND error_count <= total_records
        ),

    CONSTRAINT chk_dq_metrics_warnings
        CHECK (
            warning_count >= 0
            AND warning_count <= total_records
        ),

    CONSTRAINT chk_dq_metrics_info
        CHECK (
            info_count >= 0
            AND info_count <= total_records
        )
);

COMMENT ON TABLE audit.data_quality_metrics IS
'Pre-calculated data-quality metrics per source and ETL batch for dashboard and API consumption.';

COMMENT ON COLUMN audit.data_quality_metrics.batch_id IS
'ETL batch for which quality metrics were calculated.';

COMMENT ON COLUMN audit.data_quality_metrics.source_key IS
'Source for which quality metrics were calculated.';

COMMENT ON COLUMN audit.data_quality_metrics.total_records IS
'Total number of standardized records processed for this source in this batch.';

COMMENT ON COLUMN audit.data_quality_metrics.records_with_positive_price IS
'Count of records with a price greater than zero.';

COMMENT ON COLUMN audit.data_quality_metrics.records_with_zero_price IS
'Count of records with a price equal to zero.';

COMMENT ON COLUMN audit.data_quality_metrics.records_with_null_price IS
'Count of records with a missing price.';

COMMENT ON COLUMN audit.data_quality_metrics.duplicate_candidate_count IS
'Count of records flagged as possible duplicates.';

COMMENT ON COLUMN audit.data_quality_metrics.price_outlier_count IS
'Count of records flagged as suspicious price outliers.';

COMMENT ON COLUMN audit.data_quality_metrics.error_count IS
'Count of ERROR-level validation issues associated with this source and batch.';

COMMENT ON COLUMN audit.data_quality_metrics.warning_count IS
'Count of WARNING-level validation issues associated with this source and batch.';

-- ------------------------------------------------------------
-- Initial reference data: canonical product sources
-- ------------------------------------------------------------

INSERT INTO core.dim_sources (
    source_code,
    source_name,
    source_type
)
VALUES
    ('snapp_pay', 'SnappPay', 'UNKNOWN'),
    ('torob', 'Torob', 'UNKNOWN'),
    ('digikala', 'Digikala', 'UNKNOWN'),
    ('technolife', 'Technolife', 'UNKNOWN'),
    ('arka', 'Arka', 'UNKNOWN'),
    ('khanoumi', 'Khanoumi', 'UNKNOWN'),
    ('zanoone', 'Zanoone', 'UNKNOWN'),
    ('sormehshop', 'Sormehshop', 'UNKNOWN'),
    ('xiaomixiaomi', 'XiaomiXiaomi', 'UNKNOWN')
ON CONFLICT (source_code) DO NOTHING;

COMMIT; 