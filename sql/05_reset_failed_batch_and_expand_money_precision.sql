BEGIN;

-- This migration is intentionally limited to the confirmed failed initial-load batch.
-- It removes dependent data in foreign-key order, then expands canonical money columns.

DELETE FROM audit.validation_issues
WHERE batch_id = 2;

DELETE FROM audit.data_quality_metrics
WHERE batch_id = 2;

DELETE FROM audit.etl_run_logs
WHERE batch_id = 2;

DELETE FROM core.fact_product_listings
WHERE batch_id = 2;

DELETE FROM staging.stg_product_listings AS staging
USING raw.raw_product_records AS raw,
      raw.raw_file_registry AS file
WHERE staging.raw_record_id = raw.raw_record_id
  AND raw.file_id = file.file_id
  AND file.batch_id = 2;

DELETE FROM raw.raw_product_records AS raw
USING raw.raw_file_registry AS file
WHERE raw.file_id = file.file_id
  AND file.batch_id = 2;

DELETE FROM raw.raw_file_registry
WHERE batch_id = 2;

DELETE FROM raw.ingestion_batches
WHERE batch_id = 2
  AND run_status = 'FAILED';

ALTER TABLE staging.stg_product_listings
    ALTER COLUMN price TYPE NUMERIC(30, 2),
    ALTER COLUMN old_price TYPE NUMERIC(30, 2);

ALTER TABLE core.fact_product_listings
    ALTER COLUMN price TYPE NUMERIC(30, 2),
    ALTER COLUMN old_price TYPE NUMERIC(30, 2);

COMMIT;