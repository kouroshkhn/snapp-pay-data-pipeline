BEGIN;

-- ============================================================
-- Analytics Views for Snapp Pay Dashboard
-- Purpose: Simplify common dashboard queries and ensure consistency
-- ============================================================

-- View 1: Complete product listings with all dimensions
CREATE OR REPLACE VIEW analytics.vw_product_listings AS
SELECT
    f.listing_id,
    f.batch_id,
    f.product_key,
    f.merchant_key,
    f.source_listing_id,
    f.price,
    f.old_price,
    f.cash_back_percent,
    f.discount_percent,
    f.is_available,
    f.validation_status,
    f.is_duplicate_candidate,
    f.is_price_outlier,
    f.currency_code,
    f.observed_at,
    f.loaded_at,
    -- Product dimensions
    p.product_title,
    p.product_title_normalized,
    p.source_product_id,
    -- Source
    src.source_key,
    src.source_code,
    src.source_name,
    src.source_type,
    -- Brand
    b.brand_key,
    b.brand_name,
    b.brand_name_normalized,
    -- Category
    c.category_key,
    c.category_name,
    c.category_name_normalized,
    c.category_level,
    -- Merchant
    m.merchant_name,
    m.merchant_name_normalized,
    m.merchant_url
FROM core.fact_product_listings AS f
JOIN core.dim_products AS p ON p.product_key = f.product_key
JOIN core.dim_sources AS src ON src.source_key = p.source_key
LEFT JOIN core.dim_brands AS b ON b.brand_key = p.brand_key
LEFT JOIN core.dim_categories AS c ON c.category_key = p.category_key
LEFT JOIN core.dim_merchants AS m ON m.merchant_key = f.merchant_key;

COMMENT ON VIEW analytics.vw_product_listings IS 
'Complete product listings with all dimension attributes for dashboard queries.';

-- View 2: Source-level summary statistics
CREATE OR REPLACE VIEW analytics.vw_source_summary AS
SELECT
    src.source_key,
    src.source_code,
    src.source_name,
    src.source_type,
    src.is_active,
    -- Listing counts
    COUNT(*) AS total_listings,
    COUNT(DISTINCT f.product_key) AS distinct_products,
    COUNT(DISTINCT f.merchant_key) FILTER (WHERE f.merchant_key IS NOT NULL) AS distinct_merchants,
    -- Availability
    COUNT(*) FILTER (WHERE f.is_available = TRUE) AS available_listings,
    COUNT(*) FILTER (WHERE f.is_available = FALSE) AS unavailable_listings,
    COUNT(*) FILTER (WHERE f.is_available IS NULL) AS unknown_availability_listings,
    -- Quality flags
    COUNT(*) FILTER (WHERE f.is_price_outlier) AS outlier_listings,
    COUNT(*) FILTER (WHERE f.is_duplicate_candidate) AS duplicate_listings,
    COUNT(*) FILTER (WHERE f.validation_status = 'VALID_WITH_WARNINGS') AS warning_listings,
    COUNT(*) FILTER (WHERE f.validation_status = 'VALID') AS valid_listings,
    -- Price statistics (excluding outliers for realistic metrics)
    AVG(f.price) FILTER (WHERE f.price > 0 AND NOT f.is_price_outlier) AS avg_price_excl_outliers,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY f.price) FILTER (WHERE f.price > 0) AS median_price,
    MIN(f.price) FILTER (WHERE f.price > 0) AS min_price,
    MAX(f.price) AS max_price,
    -- Batch info
    MAX(f.loaded_at) AS last_loaded_at
FROM core.fact_product_listings AS f
JOIN core.dim_products AS p ON p.product_key = f.product_key
JOIN core.dim_sources AS src ON src.source_key = p.source_key
GROUP BY 
    src.source_key,
    src.source_code,
    src.source_name,
    src.source_type,
    src.is_active;

COMMENT ON VIEW analytics.vw_source_summary IS 
'Summary statistics by data source for dashboard overview.';

-- View 3: Data quality metrics by source
CREATE OR REPLACE VIEW analytics.vw_quality_metrics AS
SELECT
    src.source_code,
    src.source_name,
    dqm.total_records,
    dqm.records_with_title,
    dqm.records_with_positive_price,
    dqm.records_with_zero_price,
    dqm.records_with_null_price,
    dqm.records_with_brand,
    dqm.records_with_category,
    dqm.records_available,
    dqm.records_unavailable,
    dqm.records_availability_unknown,
    dqm.duplicate_candidate_count,
    dqm.price_outlier_count,
    dqm.error_count,
    dqm.warning_count,
    dqm.info_count,
    dqm.calculated_at,
    -- Quality percentages
    ROUND(100.0 * dqm.records_with_title / NULLIF(dqm.total_records, 0), 2) AS pct_with_title,
    ROUND(100.0 * dqm.records_with_positive_price / NULLIF(dqm.total_records, 0), 2) AS pct_with_positive_price,
    ROUND(100.0 * dqm.duplicate_candidate_count / NULLIF(dqm.total_records, 0), 2) AS pct_duplicates,
    ROUND(100.0 * dqm.price_outlier_count / NULLIF(dqm.total_records, 0), 2) AS pct_outliers,
    ROUND(100.0 * dqm.error_count / NULLIF(dqm.total_records, 0), 2) AS pct_errors,
    ROUND(100.0 * dqm.warning_count / NULLIF(dqm.total_records, 0), 2) AS pct_warnings
FROM audit.data_quality_metrics AS dqm
JOIN core.dim_sources AS src ON src.source_key = dqm.source_key
ORDER BY dqm.total_records DESC;

COMMENT ON VIEW analytics.vw_quality_metrics IS 
'Data quality metrics by source for monitoring and reporting.';

-- View 4: Issue summary by rule and severity
CREATE OR REPLACE VIEW analytics.vw_issue_summary AS
SELECT
    rule_code,
    severity,
    action_taken,
    field_name,
    COUNT(*) AS issue_count,
    COUNT(DISTINCT raw_record_id) AS affected_records,
    COUNT(DISTINCT stg_listing_id) AS affected_staging_records,
    COUNT(DISTINCT listing_id) AS affected_core_listings
FROM audit.validation_issues
GROUP BY 
    rule_code,
    severity,
    action_taken,
    field_name
ORDER BY issue_count DESC;

COMMENT ON VIEW analytics.vw_issue_summary IS 
'Summary of validation issues by rule and severity for quality monitoring.';

-- View 5: Brand statistics
CREATE OR REPLACE VIEW analytics.vw_brand_stats AS
SELECT
    b.brand_key,
    b.brand_name,
    b.brand_name_normalized,
    b.is_active,
    COUNT(*) AS total_listings,
    COUNT(DISTINCT f.product_key) AS distinct_products,
    COUNT(DISTINCT src.source_code) AS sources_count,
    AVG(f.price) FILTER (WHERE f.price > 0 AND NOT f.is_price_outlier) AS avg_price_excl_outliers,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY f.price) FILTER (WHERE f.price > 0) AS median_price,
    MIN(f.price) FILTER (WHERE f.price > 0) AS min_price,
    MAX(f.price) AS max_price
FROM core.fact_product_listings AS f
JOIN core.dim_products AS p ON p.product_key = f.product_key
JOIN core.dim_brands AS b ON b.brand_key = p.brand_key
JOIN core.dim_sources AS src ON src.source_key = p.source_key
GROUP BY 
    b.brand_key,
    b.brand_name,
    b.brand_name_normalized,
    b.is_active
ORDER BY total_listings DESC;

COMMENT ON VIEW analytics.vw_brand_stats IS 
'Statistics by brand for product analysis and comparison.';

-- View 6: Category statistics
CREATE OR REPLACE VIEW analytics.vw_category_stats AS
SELECT
    c.category_key,
    c.category_name,
    c.category_name_normalized,
    c.category_level,
    c.is_active,
    COUNT(*) AS total_listings,
    COUNT(DISTINCT f.product_key) AS distinct_products,
    AVG(f.price) FILTER (WHERE f.price > 0 AND NOT f.is_price_outlier) AS avg_price_excl_outliers,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY f.price) FILTER (WHERE f.price > 0) AS median_price
FROM core.fact_product_listings AS f
JOIN core.dim_products AS p ON p.product_key = f.product_key
JOIN core.dim_categories AS c ON c.category_key = p.category_key
GROUP BY 
    c.category_key,
    c.category_name,
    c.category_name_normalized,
    c.category_level,
    c.is_active
ORDER BY total_listings DESC;

COMMENT ON VIEW analytics.vw_category_stats IS 
'Statistics by category for product analysis and hierarchy navigation.';

COMMIT;