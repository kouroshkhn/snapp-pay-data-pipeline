-- ============================================================
-- Snapp Pay Data Pipeline
-- File: 03_add_currency_contract.sql
-- Purpose:
-- Define a clear canonical money contract:
-- - All transformed/core monetary amounts use IRR.
-- - Source unit is retained in staging.
-- - Discount and cashback values are stored as percentages.
-- ============================================================

BEGIN;

-- ------------------------------------------------------------
-- STAGING: preserve the original source unit and make
-- percentage semantics explicit.
-- ------------------------------------------------------------

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'staging'
          AND table_name = 'stg_product_listings'
          AND column_name = 'cash_back'
    ) THEN
        ALTER TABLE staging.stg_product_listings
        RENAME COLUMN cash_back TO cash_back_percent;
    END IF;
END $$;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'staging'
          AND table_name = 'stg_product_listings'
          AND column_name = 'discount'
    ) THEN
        ALTER TABLE staging.stg_product_listings
        RENAME COLUMN discount TO discount_percent;
    END IF;
END $$;

ALTER TABLE staging.stg_product_listings
    ADD COLUMN IF NOT EXISTS source_price_unit TEXT NOT NULL DEFAULT 'UNKNOWN';

ALTER TABLE staging.stg_product_listings
    ADD COLUMN IF NOT EXISTS currency_code CHAR(3) NOT NULL DEFAULT 'IRR';

ALTER TABLE staging.stg_product_listings
    ALTER COLUMN cash_back_percent TYPE NUMERIC(5, 2);

ALTER TABLE staging.stg_product_listings
    ALTER COLUMN discount_percent TYPE NUMERIC(5, 2);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'chk_stg_product_listings_source_price_unit'
    ) THEN
        ALTER TABLE staging.stg_product_listings
        ADD CONSTRAINT chk_stg_product_listings_source_price_unit
        CHECK (source_price_unit IN ('IRR', 'IRT', 'UNKNOWN'));
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'chk_stg_product_listings_currency_code'
    ) THEN
        ALTER TABLE staging.stg_product_listings
        ADD CONSTRAINT chk_stg_product_listings_currency_code
        CHECK (currency_code = 'IRR');
    END IF;
END $$;

COMMENT ON COLUMN staging.stg_product_listings.source_price_unit IS
'Declared unit in the source file: IRR, IRT, or UNKNOWN.';

COMMENT ON COLUMN staging.stg_product_listings.currency_code IS
'Canonical currency after transformation. Version 1 always stores IRR.';

COMMENT ON COLUMN staging.stg_product_listings.discount_percent IS
'Discount percentage after parsing values such as 10%.';

COMMENT ON COLUMN staging.stg_product_listings.cash_back_percent IS
'Cashback percentage supplied by SnappPay, when available.';


-- ------------------------------------------------------------
-- CORE FACT: all monetary values are canonical IRR;
-- discount and cashback values are percentages.
-- ------------------------------------------------------------

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'core'
          AND table_name = 'fact_product_listings'
          AND column_name = 'cash_back'
    ) THEN
        ALTER TABLE core.fact_product_listings
        RENAME COLUMN cash_back TO cash_back_percent;
    END IF;
END $$;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'core'
          AND table_name = 'fact_product_listings'
          AND column_name = 'discount'
    ) THEN
        ALTER TABLE core.fact_product_listings
        RENAME COLUMN discount TO discount_percent;
    END IF;
END $$;

ALTER TABLE core.fact_product_listings
    ADD COLUMN IF NOT EXISTS currency_code CHAR(3) NOT NULL DEFAULT 'IRR';

ALTER TABLE core.fact_product_listings
    ALTER COLUMN cash_back_percent TYPE NUMERIC(5, 2);

ALTER TABLE core.fact_product_listings
    ALTER COLUMN discount_percent TYPE NUMERIC(5, 2);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'chk_fact_product_listings_currency_code'
    ) THEN
        ALTER TABLE core.fact_product_listings
        ADD CONSTRAINT chk_fact_product_listings_currency_code
        CHECK (currency_code = 'IRR');
    END IF;
END $$;

COMMENT ON COLUMN core.fact_product_listings.currency_code IS
'Canonical currency of price and old_price. Version 1 always stores IRR.';

COMMENT ON COLUMN core.fact_product_listings.discount_percent IS
'Discount percentage.';

COMMENT ON COLUMN core.fact_product_listings.cash_back_percent IS
'Cashback percentage.';

COMMIT;