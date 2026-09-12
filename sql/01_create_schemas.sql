-- ============================================================
-- Snapp Pay Data Pipeline
-- File: 01_create_schemas.sql
-- Purpose: Create logical database layers
-- ============================================================

BEGIN;

CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS audit;
CREATE SCHEMA IF NOT EXISTS analytics;

COMMENT ON SCHEMA raw IS
'Raw layer: original ingestion batches, file metadata, and raw records.';

COMMENT ON SCHEMA staging IS
'Staging layer: standardized records before final validation and core loading.';

COMMENT ON SCHEMA core IS
'Core layer: validated and normalized entities and product listing facts.';

COMMENT ON SCHEMA audit IS
'Audit layer: ETL logs, validation issues, and data-quality metrics.';

COMMENT ON SCHEMA analytics IS
'Analytics layer: dashboard-ready views and optimized analytical queries.';

COMMIT;