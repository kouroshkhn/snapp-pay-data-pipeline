-- ============================================================
-- Performance Tests for Snapp Pay Data Pipeline
-- Purpose: Benchmark common dashboard queries with EXPLAIN ANALYZE
-- ============================================================

-- Test 1: Overall KPIs
-- Purpose: Total listings, distinct products, average price
-- Expected: < 1 second with indexes
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    COUNT(*) AS total_listings,
    COUNT(DISTINCT product_key) AS distinct_products,
    AVG(price) FILTER (
        WHERE price > 0
          AND NOT is_price_outlier
    ) AS avg_price_excl_outliers,
    PERCENTILE_CONT(0.5) WITHIN GROUP (
        ORDER BY price
    ) FILTER (
        WHERE price > 0
    ) AS median_price
FROM core.fact_product_listings;

-- Test 2: Source Summary
-- Purpose: Per-source listing and product counts
-- Expected: ~2 seconds with parallel query
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    src.source_code,
    src.source_name,
    COUNT(*) AS listing_count,
    COUNT(DISTINCT f.product_key) AS distinct_products,
    AVG(f.price) FILTER (
        WHERE f.price > 0
          AND NOT f.is_price_outlier
    ) AS avg_price_excl_outliers
FROM core.fact_product_listings AS f
JOIN core.dim_products AS p
    ON p.product_key = f.product_key
JOIN core.dim_sources AS src
    ON src.source_key = p.source_key
GROUP BY src.source_code, src.source_name
ORDER BY listing_count DESC;

-- Test 3: Price Distribution by Source
-- Purpose: Q1, Median, Q3 price per source
-- Expected: ~3 seconds with parallel query
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    src.source_code,
    src.source_name,
    MIN(f.price) FILTER (WHERE f.price > 0) AS min_price,
    PERCENTILE_CONT(0.25) WITHIN GROUP (
        ORDER BY f.price
    ) FILTER (
        WHERE f.price > 0
    ) AS q1_price,
    PERCENTILE_CONT(0.5) WITHIN GROUP (
        ORDER BY f.price
    ) FILTER (
        WHERE f.price > 0
    ) AS median_price,
    PERCENTILE_CONT(0.75) WITHIN GROUP (
        ORDER BY f.price
    ) FILTER (
        WHERE f.price > 0
    ) AS q3_price,
    MAX(f.price) AS max_price,
    COUNT(*) AS listing_count
FROM core.fact_product_listings AS f
JOIN core.dim_products AS p
    ON p.product_key = f.product_key
JOIN core.dim_sources AS src
    ON src.source_key = p.source_key
WHERE f.price > 0
GROUP BY src.source_code, src.source_name
ORDER BY median_price DESC;

-- Test 4: Filter by Outlier Flag
-- Purpose: Count price outliers
-- Expected: < 0.5 seconds with partial index
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    COUNT(*) AS outlier_count,
    COUNT(*) FILTER (WHERE is_price_outlier = TRUE) AS flagged_outliers
FROM core.fact_product_listings
WHERE is_price_outlier = TRUE;

-- Test 5: Filter by Duplicate Flag
-- Purpose: Count duplicate candidates
-- Expected: < 0.5 seconds with partial index
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    COUNT(*) AS duplicate_candidate_count,
    COUNT(*) FILTER (WHERE is_duplicate_candidate = TRUE) AS flagged_duplicates
FROM core.fact_product_listings
WHERE is_duplicate_candidate = TRUE;

-- Test 6: Validation Issues Summary
-- Purpose: Issue counts by rule and severity
-- Expected: < 1 second with indexes
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    rule_code,
    severity,
    COUNT(*) AS issue_count,
    COUNT(DISTINCT listing_id) FILTER (
        WHERE listing_id IS NOT NULL
    ) AS affected_listings
FROM audit.validation_issues
WHERE batch_id = 6
GROUP BY rule_code, severity
ORDER BY issue_count DESC;

-- Test 7: Data Quality Metrics
-- Purpose: Quality metrics by source
-- Expected: < 0.5 seconds with indexes
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    src.source_code,
    src.source_name,
    dqm.total_records,
    dqm.records_with_title,
    dqm.records_with_positive_price,
    dqm.duplicate_candidate_count,
    dqm.price_outlier_count,
    dqm.error_count,
    dqm.warning_count
FROM audit.data_quality_metrics AS dqm
JOIN core.dim_sources AS src
    ON src.source_key = dqm.source_key
WHERE dqm.batch_id = 6
ORDER BY dqm.total_records DESC;

-- Test 8: Batch Execution History
-- Purpose: Recent batch execution times
-- Expected: < 0.1 seconds
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    batch_id,
    run_status,
    started_at,
    finished_at,
    EXTRACT(
        EPOCH FROM (finished_at - started_at)
    ) AS duration_seconds,
    records_extracted,
    records_loaded_core
FROM raw.ingestion_batches
ORDER BY batch_id DESC
LIMIT 10;

-- Test 9: Product Search (ILIKE)
-- Purpose: Search products by keyword
-- Expected: ~5-10 seconds without pg_trgm, < 1 second with pg_trgm
-- Note: Consider adding GIN index with pg_trgm for better performance
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    p.product_title,
    f.price,
    src.source_code
FROM core.fact_product_listings AS f
JOIN core.dim_products AS p
    ON p.product_key = f.product_key
JOIN core.dim_sources AS src
    ON src.source_key = p.source_key
WHERE p.product_title ILIKE '%گوشی%'
  AND f.price > 0
ORDER BY f.price
LIMIT 50;

-- Test 10: Brand Statistics
-- Purpose: Listing and price stats by brand
-- Expected: ~2-3 seconds
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    b.brand_name,
    COUNT(*) AS listing_count,
    COUNT(DISTINCT f.product_key) AS distinct_products,
    AVG(f.price) FILTER (
        WHERE f.price > 0
          AND NOT f.is_price_outlier
    ) AS avg_price_excl_outliers,
    PERCENTILE_CONT(0.5) WITHIN GROUP (
        ORDER BY f.price
    ) FILTER (
        WHERE f.price > 0
    ) AS median_price
FROM core.fact_product_listings AS f
JOIN core.dim_products AS p
    ON p.product_key = f.product_key
JOIN core.dim_brands AS b
    ON b.brand_key = p.brand_key
GROUP BY b.brand_name
ORDER BY listing_count DESC
LIMIT 50;

-- ============================================================
-- Performance Summary
-- ============================================================
-- Run these tests and record:
-- 1. Execution Time (ms)
-- 2. Planning Time (ms)
-- 3. Buffers (shared hit, read, temp read/written)
-- 4. Index usage (Index Scan vs Seq Scan)
--
-- Compare results before and after:
-- - Adding/removing indexes
-- - Enabling pg_trgm for text search
-- - Creating materialized views
-- ============================================================