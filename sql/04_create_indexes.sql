BEGIN;

-- ============================================================
-- Performance Indexes for Snapp Pay Data Pipeline
-- Purpose: Optimize common dashboard and analytics queries
-- ============================================================

-- Core Fact Listings - Most queried table
CREATE INDEX IF NOT EXISTS idx_fact_listings_batch
    ON core.fact_product_listings (batch_id);

CREATE INDEX IF NOT EXISTS idx_fact_listings_product
    ON core.fact_product_listings (product_key);

CREATE INDEX IF NOT EXISTS idx_fact_listings_merchant
    ON core.fact_product_listings (merchant_key);

CREATE INDEX IF NOT EXISTS idx_fact_listings_validation
    ON core.fact_product_listings (validation_status);

CREATE INDEX IF NOT EXISTS idx_fact_listings_outlier
    ON core.fact_product_listings (is_price_outlier)
    WHERE is_price_outlier = TRUE;

CREATE INDEX IF NOT EXISTS idx_fact_listings_duplicate
    ON core.fact_product_listings (is_duplicate_candidate)
    WHERE is_duplicate_candidate = TRUE;

CREATE INDEX IF NOT EXISTS idx_fact_listings_availability
    ON core.fact_product_listings (is_available);

CREATE INDEX IF NOT EXISTS idx_fact_listings_price
    ON core.fact_product_listings (price)
    WHERE price > 0;

-- Composite indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_fact_listings_batch_product
    ON core.fact_product_listings (batch_id, product_key);

CREATE INDEX IF NOT EXISTS idx_fact_listings_batch_validation
    ON core.fact_product_listings (batch_id, validation_status);

CREATE INDEX IF NOT EXISTS idx_fact_listings_product_price
    ON core.fact_product_listings (product_key, price)
    WHERE price > 0;

-- Dimension tables
CREATE INDEX IF NOT EXISTS idx_dim_products_source
    ON core.dim_products (source_key);

CREATE INDEX IF NOT EXISTS idx_dim_products_brand
    ON core.dim_products (brand_key);

CREATE INDEX IF NOT EXISTS idx_dim_products_category
    ON core.dim_products (category_key);

CREATE INDEX IF NOT EXISTS idx_dim_products_business_key
    ON core.dim_products (source_key, product_business_key);

CREATE INDEX IF NOT EXISTS idx_dim_merchants_source
    ON core.dim_merchants (source_key);

CREATE INDEX IF NOT EXISTS idx_dim_categories_parent
    ON core.dim_categories (parent_category_key);

-- Audit tables
CREATE INDEX IF NOT EXISTS idx_validation_issues_batch
    ON audit.validation_issues (batch_id);

CREATE INDEX IF NOT EXISTS idx_validation_issues_rule
    ON audit.validation_issues (rule_code);

CREATE INDEX IF NOT EXISTS idx_validation_issues_severity
    ON audit.validation_issues (severity);

CREATE INDEX IF NOT EXISTS idx_validation_issues_staging
    ON audit.validation_issues (stg_listing_id)
    WHERE stg_listing_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_validation_issues_listing
    ON audit.validation_issues (listing_id)
    WHERE listing_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_data_quality_metrics_batch
    ON audit.data_quality_metrics (batch_id);

CREATE INDEX IF NOT EXISTS idx_data_quality_metrics_source
    ON audit.data_quality_metrics (source_key);

-- Staging table
CREATE INDEX IF NOT EXISTS idx_staging_raw_record
    ON staging.stg_product_listings (raw_record_id);

CREATE INDEX IF NOT EXISTS idx_staging_source
    ON staging.stg_product_listings (source);

CREATE INDEX IF NOT EXISTS idx_staging_transform_status
    ON staging.stg_product_listings (transform_status);

-- Raw tables
CREATE INDEX IF NOT EXISTS idx_raw_file_registry_batch
    ON raw.raw_file_registry (batch_id);

CREATE INDEX IF NOT EXISTS idx_raw_file_registry_status
    ON raw.raw_file_registry (file_status);

CREATE INDEX IF NOT EXISTS idx_raw_records_file
    ON raw.raw_product_records (file_id);


COMMIT;