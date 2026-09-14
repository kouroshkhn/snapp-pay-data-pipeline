from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

import pandas as pd
import psycopg
from psycopg.types.json import Jsonb

from config import get_db_config
from source_mappings import get_mapping
from transform import (
    PROJECT_ROOT,
    RAW_DATA_DIR,
    SUPPORTED_EXTENSIONS,
    output_file_name,
    read_file,
)

STAGING_DIR = PROJECT_ROOT / "data" / "processed" / "staging"
VALIDATION_ISSUES = PROJECT_ROOT / "data" / "processed" / "validation" / "validation_issues.csv"
DUPLICATES = PROJECT_ROOT / "data" / "processed" / "quality" / "duplicate_candidates.csv"
OUTLIERS = PROJECT_ROOT / "data" / "processed" / "quality" / "price_outliers.csv"
CHUNK_SIZE = 10_000

STG_COLUMNS = [
    "source", "dataset", "source_id", "product_title", "product_title_normalized",
    "brand_raw", "category_raw", "merchant_name_raw", "price", "old_price",
    "cash_back_percent", "discount_percent", "availability_raw", "is_available",
    "product_url", "image_url", "search_keyword", "source_price_unit", "currency_code",
    "transform_status", "transform_notes",
]


def null(value: object) -> object:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


def json_value(value: object) -> object:
    value = null(value)
    if value is None:
        return None
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, (datetime, pd.Timestamp)):
        return value.isoformat()
    return value


def raw_payload(row: pd.Series) -> dict[str, object]:
    return {str(key): json_value(value) for key, value in row.items()}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def payload_hash(payload: dict[str, object]) -> str:
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def stage_log(cur: psycopg.Cursor, batch_id: int, stage: str, status: str, records_in: int, records_out: int, rejected: int = 0, details: dict | None = None) -> None:
    cur.execute(
        """
        INSERT INTO audit.etl_run_logs
        (batch_id, stage_name, stage_status, finished_at, records_input, records_output, records_rejected, log_details)
        VALUES (%s, %s, %s, now(), %s, %s, %s, %s)
        """,
        (batch_id, stage, status, records_in, records_out, rejected, Jsonb(details or {})),
    )


def copy_raw(cur: psycopg.Cursor, file_id: int, dataframe: pd.DataFrame) -> int:
    with cur.copy("COPY raw.raw_product_records (file_id, source_row_number, raw_payload, raw_record_hash) FROM STDIN") as copy:
        for position, (_, row) in enumerate(dataframe.iterrows(), start=1):
            payload = raw_payload(row)
            copy.write_row((file_id, position, Jsonb(payload), payload_hash(payload)))
    return len(dataframe)


def copy_staging_input(cur: psycopg.Cursor, staging_file: Path) -> int:
    cur.execute("DROP TABLE IF EXISTS tmp_staging_input")
    cur.execute(
        """
        CREATE TEMP TABLE tmp_staging_input (
            source_row_number bigint, source text, dataset text, source_id text,
            product_title text, product_title_normalized text, brand_raw text,
            category_raw text, merchant_name_raw text, price numeric(30,2), old_price numeric(30,2),
            cash_back_percent numeric(5,2), discount_percent numeric(5,2), availability_raw text,
            is_available boolean, product_url text, image_url text, search_keyword text,
            source_price_unit text, currency_code char(3), transform_status text, transform_notes text
        ) ON COMMIT DROP
        """
    )
    count = 0
    for chunk in pd.read_csv(staging_file, dtype="string", chunksize=CHUNK_SIZE):
        with cur.copy(
            "COPY tmp_staging_input (source_row_number, source, dataset, source_id, product_title, product_title_normalized, brand_raw, category_raw, merchant_name_raw, price, old_price, cash_back_percent, discount_percent, availability_raw, is_available, product_url, image_url, search_keyword, source_price_unit, currency_code, transform_status, transform_notes) FROM STDIN"
        ) as copy:
            for _, row in chunk.iterrows():
                boolean = null(row["is_available"])
                boolean = None if boolean is None else str(boolean).casefold() == "true"
                copy.write_row(tuple([int(row["source_row_number"])] + [null(row[column]) for column in STG_COLUMNS[:13]] + [boolean] + [null(row[column]) for column in STG_COLUMNS[14:]]))
                count += 1
    return count


def insert_staging(cur: psycopg.Cursor, file_id: int) -> int:
    cur.execute(
        """
        INSERT INTO staging.stg_product_listings
        (raw_record_id, source, dataset, source_id, product_title, product_title_normalized, brand_raw,
         category_raw, merchant_name_raw, price, old_price, cash_back_percent, discount_percent,
         availability_raw, is_available, product_url, image_url, search_keyword, transform_status,
         transform_notes, source_price_unit, currency_code)
        SELECT r.raw_record_id, t.source, t.dataset, t.source_id, t.product_title, t.product_title_normalized,
               t.brand_raw, t.category_raw, t.merchant_name_raw, t.price, t.old_price, t.cash_back_percent,
               t.discount_percent, t.availability_raw, t.is_available, t.product_url, t.image_url,
               t.search_keyword, t.transform_status, t.transform_notes, t.source_price_unit, t.currency_code
        FROM tmp_staging_input t
        JOIN raw.raw_product_records r
          ON r.file_id = %s AND r.source_row_number = t.source_row_number
        """,
        (file_id,),
    )
    return cur.rowcount



def upsert_dimensions_and_facts(
    cur: psycopg.Cursor,
    batch_id: int,
) -> int:
    scoped_cte = """
    WITH scoped AS (
        SELECT
            s.stg_listing_id,
            s.source,
            s.dataset,
            s.source_id,
            s.product_title,
            s.product_title_normalized,
            s.brand_raw,
            s.category_raw,
            s.merchant_name_raw,
            s.price,
            s.old_price,
            s.cash_back_percent,
            s.discount_percent,
            s.availability_raw,
            s.is_available,
            s.product_url,
            s.image_url,
            s.search_keyword,
            s.source_price_unit,
            s.currency_code,
            s.transform_status,
            s.transform_notes,
            r.raw_record_id,
            r.source_row_number,
            f.original_file_name
        FROM staging.stg_product_listings AS s
        JOIN raw.raw_product_records AS r
            ON r.raw_record_id = s.raw_record_id
        JOIN raw.raw_file_registry AS f
            ON f.file_id = r.file_id
        WHERE f.batch_id = %s
            )
        """

    cur.execute(
        scoped_cte
        + """
        INSERT INTO core.dim_brands (
            brand_name,
            brand_name_normalized
        )
        SELECT DISTINCT
            brand_raw,
            lower(brand_raw)
        FROM scoped
        WHERE brand_raw IS NOT NULL
        ON CONFLICT (brand_name_normalized) DO NOTHING
        """,
        (batch_id,),
    )

    cur.execute(
        scoped_cte
        + """
        INSERT INTO core.dim_categories (
            category_name,
            category_name_normalized,
            category_level
        )
        SELECT DISTINCT
            category_raw,
            lower(category_raw),
            1
        FROM scoped
        WHERE category_raw IS NOT NULL
        ON CONFLICT (category_name_normalized) DO NOTHING
        """,
        (batch_id,),
    )

    cur.execute(
        scoped_cte
        + """
        INSERT INTO core.dim_merchants (
            source_key,
            merchant_name,
            merchant_name_normalized
        )
        SELECT DISTINCT
            ds.source_key,
            scoped.merchant_name_raw,
            lower(scoped.merchant_name_raw)
        FROM scoped
        JOIN core.dim_sources AS ds
            ON ds.source_code = scoped.source
        WHERE scoped.merchant_name_raw IS NOT NULL
        ON CONFLICT (
            source_key,
            merchant_name_normalized
        ) DO NOTHING
        """,
        (batch_id,),
    )

    cur.execute(
        scoped_cte
        + """
        , products_to_upsert AS (
            SELECT DISTINCT ON (
                ds.source_key,
                CASE
                    WHEN nullif(btrim(scoped.source_id), '') IS NOT NULL
                        THEN 'ID|' || scoped.source_id
                    ELSE 'TITLE|' || scoped.product_title_normalized
                END
            )
                ds.source_key,
                scoped.source_id,
                scoped.product_title,
                scoped.product_title_normalized,
                brand.brand_key,
                category.category_key,
                CASE
                    WHEN nullif(btrim(scoped.source_id), '') IS NOT NULL
                        THEN 'ID|' || scoped.source_id
                    ELSE 'TITLE|' || scoped.product_title_normalized
                END AS product_business_key
            FROM scoped
            JOIN core.dim_sources AS ds
                ON ds.source_code = scoped.source
            LEFT JOIN core.dim_brands AS brand
                ON brand.brand_name_normalized = lower(scoped.brand_raw)
            LEFT JOIN core.dim_categories AS category
                ON category.category_name_normalized =
                    lower(scoped.category_raw)
            WHERE nullif(
                btrim(scoped.product_title_normalized),
                ''
            ) IS NOT NULL
            ORDER BY
            ds.source_key,
            product_business_key,
            scoped.raw_record_id
        )
        INSERT INTO core.dim_products (
            source_key,
            source_product_id,
            product_business_key,
            product_title,
            product_title_normalized,
            brand_key,
            category_key
        )
        SELECT
            source_key,
            source_id,
            product_business_key,
            product_title,
            product_title_normalized,
            brand_key,
            category_key
        FROM products_to_upsert
        ON CONFLICT (
            source_key,
            product_business_key
        )
        DO UPDATE SET
            updated_at = now(),
            is_active = true
        """,
        (batch_id,),
    )

    cur.execute(
        scoped_cte
        + """
        INSERT INTO core.fact_product_listings (
            batch_id,
            stg_listing_id,
            product_key,
            merchant_key,
            source_listing_id,
            price,
            old_price,
            cash_back_percent,
            discount_percent,
            is_available,
            product_url,
            image_url,
            search_keyword,
            validation_status,
            is_duplicate_candidate,
            is_price_outlier,
            currency_code
        )
        SELECT
            %s,
            scoped.stg_listing_id,
            product.product_key,
            merchant.merchant_key,
            scoped.source_id,
            scoped.price,
            scoped.old_price,
            scoped.cash_back_percent,
            scoped.discount_percent,
            scoped.is_available,
            scoped.product_url,
            scoped.image_url,
            scoped.search_keyword,
            CASE
                WHEN scoped.price IS NULL
                    OR scoped.price = 0
                    OR EXISTS (
                        SELECT 1
                        FROM tmp_quality AS quality
                        WHERE quality.file_name =
                                scoped.original_file_name
                          AND quality.row_number =
                                scoped.source_row_number
                          AND quality.rule_code IN (
                              'OLD_PRICE_LT_PRICE',
                              'ZERO_PRICE',
                              'MISSING_PRICE'
                          )
                    )
                    THEN 'VALID_WITH_WARNINGS'
                ELSE 'VALID'
            END,
            EXISTS (
                SELECT 1
                FROM tmp_quality AS quality
                WHERE quality.file_name =
                        scoped.original_file_name
                  AND quality.row_number =
                        scoped.source_row_number
                  AND quality.rule_code LIKE 'DUPLICATE%%'
            ),
            EXISTS (
                SELECT 1
                FROM tmp_quality AS quality
                WHERE quality.file_name =
                        scoped.original_file_name
                  AND quality.row_number =
                        scoped.source_row_number
                  AND quality.rule_code = 'PRICE_OUTLIER'
            ),
            'IRR'
        FROM scoped
        JOIN core.dim_sources AS ds
            ON ds.source_code = scoped.source
        JOIN core.dim_products AS product
            ON product.source_key = ds.source_key
           AND product.product_business_key =
                CASE
                    WHEN nullif(btrim(scoped.source_id), '') IS NOT NULL
                        THEN 'ID|' || scoped.source_id
                    ELSE 'TITLE|' || scoped.product_title_normalized
                END
        LEFT JOIN core.dim_merchants AS merchant
            ON merchant.source_key = ds.source_key
           AND merchant.merchant_name_normalized =
                lower(scoped.merchant_name_raw)
        WHERE NOT EXISTS (
            SELECT 1
            FROM tmp_quality AS quality
            WHERE quality.file_name =
                    scoped.original_file_name
              AND quality.row_number =
                    scoped.source_row_number
              AND quality.rule_code = 'REQ_TITLE'
        )
        AND NOT EXISTS (
            SELECT 1
            FROM tmp_quality AS quality
            WHERE quality.file_name =
                    scoped.original_file_name
              AND quality.row_number =
                    scoped.source_row_number
              AND quality.rule_code = 'DUPLICATE_SOURCE_ID'
              AND quality.is_core_canonical = false
        )
        """,
        (batch_id, batch_id),
    )

    return cur.rowcount


def load_quality(cur: psycopg.Cursor, batch_id: int) -> int:
    cur.execute("CREATE TEMP TABLE tmp_quality (file_name text, row_number bigint, rule_code text, severity text, action_taken text, field_name text, observed_value text, issue_message text, details jsonb, is_core_canonical boolean) ON COMMIT DROP")

    def write_rows(path: Path, kind: str) -> None:
        for chunk in pd.read_csv(path, dtype="string", chunksize=CHUNK_SIZE):
            with cur.copy("COPY tmp_quality (file_name,row_number,rule_code,severity,action_taken,field_name,observed_value,issue_message,details,is_core_canonical) FROM STDIN") as copy:
                for _, x in chunk.iterrows():
                    if kind == "validation":
                        row_number = x.get("source_row_number")
                        row_number = null(row_number)
                        row_number = None if row_number is None else int(float(row_number))

                        row = (
                            null(x.get("source_file_name")),
                            row_number,
                            x["rule_code"],
                            x["severity"],
                            x["action_taken"],
                            null(x.get("field_name")),
                            null(x.get("observed_value")),
                            x["issue_message"],
                            Jsonb(json.loads(x.get("issue_details") or "{}")),
                            None,
                        )
                    elif kind == "duplicate":
                        row = (
                            x["source_file_name"],
                            int(x["source_row_number"]),
                            x["rule_code"],
                            "WARNING",
                            "FLAG",
                            "duplicate_key",
                            x["duplicate_key"],
                            "Duplicate candidate detected.",
                            Jsonb({
                                "group_size": int(x["duplicate_group_size"]),
                                "rank": int(x["duplicate_rank"]),
                            }),
                            str(x["is_core_canonical"]).casefold() == "true",
                        )
                    else:
                        row = (
                            x["source_file_name"],
                            int(x["source_row_number"]),
                            "PRICE_OUTLIER",
                            "WARNING",
                            "FLAG",
                            "price",
                            x["price"],
                            "Price is outside the log-IQR expected range.",
                            Jsonb({"analysis_group": x["analysis_group"]}),
                            None,
                        )
                    copy.write_row(row)

    write_rows(VALIDATION_ISSUES, "validation")
    write_rows(DUPLICATES, "duplicate")
    write_rows(OUTLIERS, "outlier")

    cur.execute("""
        INSERT INTO audit.validation_issues
        (batch_id,file_id,raw_record_id,stg_listing_id,rule_code,severity,action_taken,field_name,observed_value,issue_message,issue_details)
        SELECT %s,f.file_id,r.raw_record_id,s.stg_listing_id,q.rule_code,q.severity,q.action_taken,q.field_name,q.observed_value,q.issue_message,q.details
        FROM tmp_quality q
        LEFT JOIN raw.raw_file_registry f ON f.batch_id=%s AND f.original_file_name=q.file_name
        LEFT JOIN raw.raw_product_records r ON r.file_id=f.file_id AND r.source_row_number=q.row_number
        LEFT JOIN staging.stg_product_listings s ON s.raw_record_id=r.raw_record_id
    """, (batch_id, batch_id))

    return cur.rowcount

def calculate_metrics(cur: psycopg.Cursor, batch_id: int) -> None:
    cur.execute("""
      INSERT INTO audit.data_quality_metrics
      (batch_id,source_key,total_records,records_with_title,records_with_positive_price,records_with_zero_price,records_with_null_price,records_with_brand,records_with_category,records_available,records_unavailable,records_availability_unknown,duplicate_candidate_count,price_outlier_count,error_count,warning_count,info_count)
      SELECT %s,ds.source_key,count(*),count(s.product_title),count(*) FILTER (WHERE s.price>0),count(*) FILTER (WHERE s.price=0),count(*) FILTER (WHERE s.price IS NULL),count(s.brand_raw),count(s.category_raw),count(*) FILTER (WHERE s.is_available),count(*) FILTER (WHERE s.is_available=false),count(*) FILTER (WHERE s.is_available IS NULL),
      count(DISTINCT s.stg_listing_id) FILTER (WHERE q.rule_code LIKE 'DUPLICATE%%'),count(DISTINCT s.stg_listing_id) FILTER (WHERE q.rule_code='PRICE_OUTLIER'),count(DISTINCT s.stg_listing_id) FILTER (WHERE q.severity='ERROR'),count(DISTINCT s.stg_listing_id) FILTER (WHERE q.severity='WARNING'),count(DISTINCT s.stg_listing_id) FILTER (WHERE q.severity='INFO')
      FROM staging.stg_product_listings s JOIN raw.raw_product_records r ON r.raw_record_id=s.raw_record_id JOIN raw.raw_file_registry f ON f.file_id=r.file_id JOIN core.dim_sources ds ON ds.source_code=s.source LEFT JOIN audit.validation_issues q ON q.stg_listing_id=s.stg_listing_id AND q.batch_id=%s
      WHERE f.batch_id=%s GROUP BY ds.source_key
    """, (batch_id, batch_id, batch_id))


def main() -> None:
    files = [p for p in sorted(RAW_DATA_DIR.glob("*")) if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS]
    if len(files) != 15:
        raise RuntimeError(f"Expected 15 raw data files; found {len(files)}.")
    for path in (VALIDATION_ISSUES, DUPLICATES, OUTLIERS):
        if not path.exists():
            raise FileNotFoundError(path)
    with psycopg.connect(**get_db_config()) as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO raw.ingestion_batches (pipeline_version,source_file_count) VALUES ('1.0.0',%s) RETURNING batch_id", (len(files),))
            batch_id = cur.fetchone()[0]
        conn.commit()
        try:
            extracted = staging_loaded = 0
            for number, raw_file in enumerate(files, 1):
                mapping = get_mapping(raw_file)
                staging_file = STAGING_DIR / output_file_name(raw_file)
                print(f"[{number}/{len(files)}] Loading {raw_file.name}")
                raw_df = read_file(raw_file)
                with conn.cursor() as cur:
                    cur.execute("""INSERT INTO raw.raw_file_registry (batch_id,source_name_raw,dataset_name_raw,original_file_name,relative_file_path,file_extension,file_size_bytes,file_sha256,rows_read,file_status,loaded_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'DISCOVERED',now()) RETURNING file_id""", (batch_id,mapping.source_code,mapping.dataset,raw_file.name,raw_file.relative_to(PROJECT_ROOT).as_posix(),raw_file.suffix.lower().lstrip('.'),raw_file.stat().st_size,sha256_file(raw_file),len(raw_df)))
                    file_id = cur.fetchone()[0]
                    extracted += copy_raw(cur, file_id, raw_df)
                    copied = copy_staging_input(cur, staging_file)
                    loaded = insert_staging(cur, file_id)
                    if copied != loaded:
                        raise RuntimeError(f"Staging join mismatch for {raw_file.name}: {copied} vs {loaded}")
                    staging_loaded += loaded
                    cur.execute("UPDATE raw.raw_file_registry SET file_status='LOADED', loaded_at=now() WHERE file_id=%s", (file_id,))
                conn.commit()
            with conn.cursor() as cur:
                stage_log(cur,batch_id,'LOAD_RAW','SUCCESS',extracted,extracted,details={"files":len(files)})
                stage_log(cur,batch_id,'LOAD_STAGING','SUCCESS',extracted,staging_loaded)
                issue_count = load_quality(cur,batch_id)
                core_loaded = upsert_dimensions_and_facts(cur,batch_id)
                stage_log(cur,batch_id,'LOAD_CORE','SUCCESS',staging_loaded,core_loaded)
                calculate_metrics(cur,batch_id)
                stage_log(cur,batch_id,'CALCULATE_METRICS','SUCCESS',staging_loaded,10)
                cur.execute("UPDATE raw.ingestion_batches SET run_status='SUCCESS',finished_at=now(),records_extracted=%s,records_valid=%s,records_quarantined=1,records_loaded_staging=%s,records_loaded_core=%s WHERE batch_id=%s", (extracted, extracted-1, staging_loaded, core_loaded, batch_id))
            conn.commit()
            print(f"SUCCESS: batch_id={batch_id:,}; raw={extracted:,}; staging={staging_loaded:,}; issues={issue_count:,}; core={core_loaded:,}")
        except Exception as error:
            conn.rollback()
            with conn.cursor() as cur:
                cur.execute("UPDATE raw.ingestion_batches SET run_status='FAILED',finished_at=now(),error_message=%s WHERE batch_id=%s", (str(error)[:4000], batch_id))
            conn.commit()
            raise


if __name__ == '__main__':
    main()