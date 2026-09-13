from __future__ import annotations

import ast
import json
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd

from extract import detect_content_format, read_csv_with_fallbacks
from source_mappings import SourceMapping, get_mapping


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"
STAGING_OUTPUT_DIR = PROJECT_ROOT / "data" / "processed" / "staging"
SUMMARY_PATH = PROJECT_ROOT / "data" / "processed" / "transform_summary.json"

SUPPORTED_EXTENSIONS = {".csv", ".tsv", ".xlsx", ".xls", ".parquet"}

PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")
ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


def read_file(file_path: Path) -> pd.DataFrame:
    content_format = detect_content_format(file_path)

    if content_format == "csv":
        return read_csv_with_fallbacks(file_path)

    if content_format == "xlsx":
        return pd.read_excel(file_path, engine="openpyxl")

    if content_format == "parquet":
        return pd.read_parquet(file_path)

    raise ValueError(
        f"Unsupported detected format '{content_format}' for {file_path.name}"
    )


def clean_text(value: object) -> str | None:
    if pd.isna(value):
        return None

    text = str(value).translate(PERSIAN_DIGITS).translate(ARABIC_DIGITS)
    text = text.replace("ي", "ی").replace("ى", "ی").replace("ك", "ک")
    text = re.sub(r"\s+", " ", text).strip()

    return text or None


def normalize_text(value: object) -> str | None:
    text = clean_text(value)
    return text.casefold() if text else None


def parse_decimal(value: object) -> Decimal | None:
    if pd.isna(value):
        return None

    if isinstance(value, Decimal):
        return value

    if isinstance(value, bool):
        return Decimal(int(value))

    if isinstance(value, int):
        return Decimal(value)

    if isinstance(value, float):
        if pd.isna(value):
            return None
        return Decimal(str(value))

    text = clean_text(value)

    if text is None:
        return None

    text = (
        text.replace(",", "")
        .replace("٬", "")
        .replace("ریال", "")
        .replace("تومان", "")
        .replace("تومن", "")
        .replace("IRT", "")
        .replace("IRR", "")
        .replace("irt", "")
        .replace("irr", "")
        .strip()
    )

    text = re.sub(r"[^0-9.\-]", "", text)

    if text in {"", "-", ".", "-."}:
        return None

    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def parse_price_to_irr(
    value: object,
    price_multiplier_to_irr: int | None,
) -> Decimal | None:
    raw_number = parse_decimal(value)

    if raw_number is None or price_multiplier_to_irr is None:
        return None

    return raw_number * Decimal(price_multiplier_to_irr)


def parse_percent(value: object) -> Decimal | None:
    if pd.isna(value):
        return None

    text = clean_text(value)

    if text is None:
        return None

    text = text.replace("%", "").replace("٪", "").strip()
    return parse_decimal(text)


def normalize_availability(
    value: object,
    mapping: SourceMapping,
) -> bool | None:
    normalized = normalize_text(value)

    if normalized is None:
        return None

    if normalized in mapping.availability_true_values:
        return True

    if normalized in mapping.availability_false_values:
        return False

    return None

def is_valid_http_url(value: str | None) -> bool:
    if not value:
        return False

    parsed = urlparse(value)

    return (
        parsed.scheme in {"http", "https"}
        and bool(parsed.netloc)
    )


def normalize_url(value: object) -> str | None:
    text = clean_text(value)

    if text is None:
        return None

    if text.startswith("[") and "](" in text and text.endswith(")"):
        text = text.split("](", maxsplit=1)[1][:-1].strip()

    if text.startswith("[") and text.endswith("]"):
        try:
            parsed_list = ast.literal_eval(text)
        except (SyntaxError, ValueError):
            parsed_list = None

        if isinstance(parsed_list, (list, tuple)):
            for item in parsed_list:
                candidate = clean_text(item)

                if candidate and is_valid_http_url(candidate):
                    return candidate

            return None

    return text

def get_column(
    dataframe: pd.DataFrame,
    column_name: str | None,
) -> pd.Series:
    if column_name is None:
        return pd.Series([None] * len(dataframe), index=dataframe.index)

    if column_name not in dataframe.columns:
        raise KeyError(f"Expected column not found: {column_name}")

    return dataframe[column_name]


def output_file_name(file_path: Path) -> str:
    safe_stem = re.sub(r"[^a-zA-Z0-9آ-ی_-]+", "_", file_path.stem)
    return f"{safe_stem}__staging.csv"


def transform_file(
    file_path: Path,
    mapping: SourceMapping,
) -> tuple[pd.DataFrame, dict[str, object]]:
    raw_dataframe = read_file(file_path)

    title_series = get_column(raw_dataframe, mapping.title_column)
    price_series = get_column(raw_dataframe, mapping.price_column)
    old_price_series = get_column(raw_dataframe, mapping.old_price_column)
    discount_series = get_column(raw_dataframe, mapping.discount_column)
    cash_back_series = get_column(raw_dataframe, mapping.cash_back_column)
    availability_series = get_column(raw_dataframe, mapping.availability_column)

    transformed = pd.DataFrame(
        {
            "source": mapping.source_code,
            "dataset": mapping.dataset,
            "source_id": get_column(raw_dataframe, mapping.source_id_column).map(clean_text),
            "product_title": title_series.map(clean_text),
            "product_title_normalized": title_series.map(normalize_text),
            "brand_raw": get_column(raw_dataframe, mapping.brand_column).map(clean_text),
            "category_raw": get_column(raw_dataframe, mapping.category_column).map(clean_text),
            "merchant_name_raw": get_column(raw_dataframe, mapping.merchant_column).map(clean_text),
            "price": price_series.map(
                lambda value: parse_price_to_irr(
                    value,
                    mapping.price_multiplier_to_irr,
                )
            ),
            "old_price": old_price_series.map(
                lambda value: parse_price_to_irr(
                    value,
                    mapping.price_multiplier_to_irr,
                )
            ),
            "cash_back_percent": cash_back_series.map(parse_percent),
            "discount_percent": discount_series.map(parse_percent),
            "availability_raw": availability_series.map(clean_text),
            "is_available": availability_series.map(
                lambda value: normalize_availability(value, mapping)
            ),
            "product_url": get_column(
                raw_dataframe,
                mapping.product_url_column,
            ).map(normalize_url),
            "image_url": get_column(
                raw_dataframe,
                mapping.image_url_column,
            ).map(normalize_url),
            "search_keyword": get_column(
                raw_dataframe,
                mapping.search_keyword_column,
            ).map(clean_text),
            "source_price_unit": mapping.source_price_unit,
            "currency_code": "IRR",
            "transform_status": "TRANSFORMED",
            "transform_notes": mapping.notes or None,
            "source_file_name": file_path.name,
            "source_row_number": raw_dataframe.index + 1,
        }
    )

    if mapping.source_price_unit == "UNKNOWN":
        transformed["transform_status"] = "PARTIAL"

    output_path = STAGING_OUTPUT_DIR / output_file_name(file_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    transformed.to_csv(
        output_path,
        index=False,
        encoding="utf-8-sig",
    )

    summary = {
        "file_name": file_path.name,
        "source": mapping.source_code,
        "dataset": mapping.dataset,
        "rows_input": len(raw_dataframe),
        "rows_output": len(transformed),
        "null_title_count": int(transformed["product_title"].isna().sum()),
        "null_price_count": int(transformed["price"].isna().sum()),
        "zero_price_count": int((transformed["price"] == 0).sum()),
        "available_count": int((transformed["is_available"] == True).sum()),
        "unavailable_count": int((transformed["is_available"] == False).sum()),
        "unknown_availability_count": int(
            transformed["is_available"].isna().sum()
        ),
        "source_price_unit": mapping.source_price_unit,
        "price_multiplier_to_irr": mapping.price_multiplier_to_irr,
        "output_file": output_path.relative_to(PROJECT_ROOT).as_posix(),
    }

    return transformed, summary


def main() -> None:
    raw_files = sorted(
        path
        for path in RAW_DATA_DIR.glob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    )

    if not raw_files:
        print(f"No supported raw files found in: {RAW_DATA_DIR}")
        return

    summaries = []

    for number, file_path in enumerate(raw_files, start=1):
        mapping = get_mapping(file_path)

        print(
            f"[{number}/{len(raw_files)}] Transforming: {file_path.name} "
            f"| source={mapping.source_code} "
            f"| raw_unit={mapping.source_price_unit}"
        )

        _, summary = transform_file(file_path, mapping)
        summaries.append(summary)

        print(
            f"  Output rows={summary['rows_output']:,} "
            f"| null_price={summary['null_price_count']:,} "
            f"| zero_price={summary['zero_price_count']:,} "
            f"| availability_unknown="
            f"{summary['unknown_availability_count']:,}"
        )

    SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_PATH.write_text(
        json.dumps(
            {
                "transformed_at_utc": datetime.now(timezone.utc).isoformat(),
                "file_count": len(summaries),
                "total_rows_input": sum(item["rows_input"] for item in summaries),
                "total_rows_output": sum(item["rows_output"] for item in summaries),
                "files": summaries,
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )

    print("\nTransform completed successfully.")
    print(f"Staging CSV folder: {STAGING_OUTPUT_DIR.relative_to(PROJECT_ROOT)}")
    print(f"Summary report: {SUMMARY_PATH.relative_to(PROJECT_ROOT)}")
    print(
        "Total rows transformed: "
        f"{sum(item['rows_output'] for item in summaries):,}"
    )


if __name__ == "__main__":
    main()