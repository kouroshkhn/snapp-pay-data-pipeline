-- ============================================================
-- Snapp Pay Data Pipeline
-- File: 04_add_torob_pay_source.sql
-- Purpose: Add TorobPay as a separate source for traceability.
-- ============================================================

BEGIN;

INSERT INTO core.dim_sources (
    source_code,
    source_name,
    source_type
)
VALUES (
    'torob_pay',
    'TorobPay',
    'UNKNOWN'
)
ON CONFLICT (source_code) DO NOTHING;

COMMIT;