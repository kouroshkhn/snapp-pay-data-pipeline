-- ============================================================
-- Dashboard Queries for Snapp Pay Analytics
-- Purpose: Ready-to-use queries for dashboard components
-- ============================================================

-- Query 1: Overall KPI Cards
-- Use: Display main metrics on dashboard header
SELECT
    'Total Listings' AS metric_name,
    COUNT(*)::TEXT AS metric_value
FROM core.fact_product_listings

UNION ALL

SELECT
    'Distinct Products',
    COUNT(DISTINCT product_key)::TEXT
FROM core.fact_product_listings

UNION ALL

SELECT
    'Active Sources',
    COUNT(DISTINCT src.source_code)::TEXT
FROM core.fact_product_listings AS f
JOIN core.dim_products AS p ON p.product_key = f.product_key
JOIN core.dim_sources AS src ON src.source_key = p.source_key

UNION ALL

SELECT
    'Avg Price (excl. outliers)',
    TO_CHAR(AVG(price) FILTER (WHERE price > 0 AND NOT is_price_outlier), 'FM999,999,999,999') || ' IRR'
FROM core.fact_product_listings

UNION ALL

SELECT
    'Median Price',
    TO_CHAR(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY price) FILTER (WHERE price > 0), 'FM999,999,999,999') || ' IRR'
FROM core.fact_product_listings;

-- Query 2: Source Comparison Chart
-- Use: Bar chart comparing sources
SELECT
    src.source_name,
    src.source_code,
    COUNT(*) AS listing_count,
    COUNT(DISTINCT f.product_key) AS product_count,
    ROUND(AVG(f.price) FILTER (WHERE f.price > 0 AND NOT f.is_price_outlier) / 1000000, 2) AS avg_price_million_irr,
    COUNT(*) FILTER (WHERE f.is_price_outlier) AS outlier_count,
    ROUND(100.0 * COUNT(*) FILTER (WHERE f.is_price_outlier) / NULLIF(COUNT(*), 0), 2) AS outlier_pct
FROM core.fact_product_listings AS f
JOIN core.dim_products AS p ON p.product_key = f.product_key
JOIN core.dim_sources AS src ON src.source_key = p.source_key
GROUP BY src.source_name, src.source_code
ORDER BY listing_count DESC;

-- Query 3: Price Distribution by Source
-- Use: Box plot or histogram of prices
SELECT
    src.source_code,
    src.source_name,
    MIN(f.price) FILTER (WHERE f.price > 0) AS min_price,
    PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY f.price) FILTER (WHERE f.price > 0) AS q1_price,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY f.price) FILTER (WHERE f.price > 0) AS median_price,
    PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY f.price) FILTER (WHERE f.price > 0) AS q3_price,
    MAX(f.price) AS max_price,
    AVG(f.price) FILTER (WHERE f.price > 0 AND NOT f.is_price_outlier) AS avg_price_excl_outliers,
    COUNT(*) AS listing_count
FROM core.fact_product_listings AS f
JOIN core.dim_products AS p ON p.product_key = f.product_key
JOIN core.dim_sources AS src ON src.source_key = p.source_key
WHERE f.price > 0
GROUP BY src.source_code, src.source_name
ORDER BY median_price DESC;

-- Query 4: Top 20 Most Expensive Products
-- Use: Table of premium products
SELECT
    p.product_title,
    src.source_name,
    f.price,
    f.is_price_outlier,
    f.validation_status
FROM core.fact_product_listings AS f
JOIN core.dim_products AS p ON p.product_key = f.product_key
JOIN core.dim_sources AS src ON src.source_key = p.source_key
WHERE f.price > 0
ORDER BY f.price DESC
LIMIT 20;

-- Query 5: Data Quality Overview
-- Use: Quality dashboard section
SELECT
    src.source_name,
    dqm.total_records,
    dqm.records_with_title,
    dqm.records_with_positive_price,
    dqm.duplicate_candidate_count,
    dqm.price_outlier_count,
    dqm.error_count,
    dqm.warning_count,
    ROUND(100.0 * dqm.records_with_title / NULLIF(dqm.total_records, 0), 2) AS completeness_title_pct,
    ROUND(100.0 * dqm.records_with_positive_price / NULLIF(dqm.total_records, 0), 2) AS completeness_price_pct,
    ROUND(100.0 * dqm.error_count / NULLIF(dqm.total_records, 0), 4) AS error_rate_pct
FROM audit.data_quality_metrics AS dqm
JOIN core.dim_sources AS src ON src.source_key = dqm.source_key
ORDER BY dqm.total_records DESC;

-- Query 6: Availability Status by Source
-- Use: Pie chart or stacked bar
SELECT
    src.source_name,
    f.is_available,
    COUNT(*) AS listing_count,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (PARTITION BY src.source_name), 2) AS pct_of_source
FROM core.fact_product_listings AS f
JOIN core.dim_products AS p ON p.product_key = f.product_key
JOIN core.dim_sources AS src ON src.source_key = p.source_key
GROUP BY src.source_name, f.is_available
ORDER BY src.source_name, f.is_available;

-- Query 7: Recent Batch Summary
-- Use: Show latest data load status
SELECT
    ib.batch_id,
    ib.pipeline_version,
    ib.run_status,
    ib.started_at,
    ib.finished_at,
    ib.source_file_count,
    ib.records_loaded_core,
    ib.records_loaded_staging,
    ib.records_quarantined,
    ib.error_message,
    EXTRACT(EPOCH FROM (ib.finished_at - ib.started_at)) AS duration_seconds
FROM raw.ingestion_batches AS ib
ORDER BY ib.batch_id DESC
LIMIT 5;

-- Query 8: Validation Issues by Rule
-- Use: Quality issues breakdown
SELECT
    rule_code,
    severity,
    COUNT(*) AS issue_count,
    COUNT(DISTINCT listing_id) AS affected_listings,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS pct_of_total_issues
FROM audit.validation_issues
GROUP BY rule_code, severity
ORDER BY issue_count DESC
LIMIT 15;

-- Query 9: Brand Leaderboard (Top 20)
-- Use: Brand comparison table
SELECT
    b.brand_name,
    COUNT(*) AS listing_count,
    COUNT(DISTINCT f.product_key) AS product_count,
    ROUND(AVG(f.price) FILTER (WHERE f.price > 0 AND NOT f.is_price_outlier) / 1000000, 2) AS avg_price_million_irr,
    src.source_name
FROM core.fact_product_listings AS f
JOIN core.dim_products AS p ON p.product_key = f.product_key
JOIN core.dim_brands AS b ON b.brand_key = p.brand_key
JOIN core.dim_sources AS src ON src.source_key = p.source_key
GROUP BY b.brand_name, src.source_name
ORDER BY listing_count DESC
LIMIT 20;

-- Query 10: Product Search (for future full-text search)
-- Use: Search products by keyword
-- Note: Replace 'گوشی' with actual search term
SELECT
    p.product_title,
    src.source_name,
    f.price,
    f.is_available,
    f.validation_status
FROM core.fact_product_listings AS f
JOIN core.dim_products AS p ON p.product_key = f.product_key
JOIN core.dim_sources AS src ON src.source_key = p.source_key
WHERE p.product_title ILIKE '%گوشی%'
  AND f.price > 0
ORDER BY f.price
LIMIT 50;