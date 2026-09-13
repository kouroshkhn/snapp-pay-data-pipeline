from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from extract import detect_content_format, read_csv_with_fallbacks


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"
REPORT_PATH = PROJECT_ROOT / "data" / "processed" / "currency_profile.csv"
SUPPORTED_EXTENSIONS = {".csv", ".tsv", ".xlsx", ".xls", ".parquet"}
PRICE_COLUMNS = ["Product Price", "current_price", "sale_price", "price"]

PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")
ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
UNIT_MARKERS = {
    "IRT": ("irt",),
    "IRR": ("irr", "ریال"),
    "TOMAN": ("تومان", "تومن"),
}


def read_file(file_path: Path) -> pd.DataFrame:
    content_format = detect_content_format(file_path)

    if content_format == "csv":
        return read_csv_with_fallbacks(file_path)
    if content_format == "xlsx":
        return pd.read_excel(file_path, engine="openpyxl")
    if content_format == "parquet":
        return pd.read_parquet(file_path)

    raise ValueError(f"Unsupported content format: {content_format}")


def choose_price_column(columns: pd.Index) -> str | None:
    return next((column for column in PRICE_COLUMNS if column in columns), None)


def normalize_money(value: object) -> float | None:
    if pd.isna(value):
        return None

    text = str(value).translate(PERSIAN_DIGITS).translate(ARABIC_DIGITS).strip()
    text = text.replace(",", "").replace("٬", "").replace(" ", "")
    text = re.sub(r"[^0-9.\-]", "", text)

    if not text or text in {"-", ".", "-."}:
        return None

    return pd.to_numeric(text, errors="coerce")


def unit_evidence(values: pd.Series) -> str:
    text = values.dropna().astype(str).str.lower()
    evidence = []

    for label, markers in UNIT_MARKERS.items():
        count = sum(text.str.contains(marker, regex=False).sum() for marker in markers)
        if count:
            evidence.append(f"{label}: {count:,}")

    return "; ".join(evidence) if evidence else "No explicit marker"


def samples(values: pd.Series, limit: int = 5) -> str:
    unique_values = values.dropna().astype(str).str.strip()
    unique_values = unique_values[unique_values.ne("")].drop_duplicates().head(limit)
    return " | ".join(unique_values.tolist()) or "No non-null sample"


def profile_file(file_path: Path) -> dict[str, object]:
    dataframe = read_file(file_path)
    price_column = choose_price_column(dataframe.columns)

    base = {
        "file_name": file_path.name,
        "declared_extension": file_path.suffix.lower() or "<none>",
        "detected_format": detect_content_format(file_path),
        "rows": len(dataframe),
        "price_column": price_column or "<not found>",
    }

    if price_column is None:
        return {
            **base,
            "non_null_prices": 0,
            "parseable_prices": 0,
            "unparseable_non_null": 0,
            "zero_prices": 0,
            "min_numeric_price": None,
            "median_numeric_price": None,
            "max_numeric_price": None,
            "explicit_unit_evidence": "N/A",
            "sample_raw_prices": "N/A",
        }

    raw_prices = dataframe[price_column]
    numeric_prices = raw_prices.map(normalize_money)
    numeric_prices = pd.to_numeric(numeric_prices, errors="coerce")
    non_null_count = int(raw_prices.notna().sum())
    parseable_count = int(numeric_prices.notna().sum())
    valid_prices = numeric_prices.dropna()

    return {
        **base,
        "non_null_prices": non_null_count,
        "parseable_prices": parseable_count,
        "unparseable_non_null": non_null_count - parseable_count,
        "zero_prices": int((valid_prices == 0).sum()),
        "min_numeric_price": valid_prices.min() if not valid_prices.empty else None,
        "median_numeric_price": valid_prices.median() if not valid_prices.empty else None,
        "max_numeric_price": valid_prices.max() if not valid_prices.empty else None,
        "explicit_unit_evidence": unit_evidence(raw_prices),
        "sample_raw_prices": samples(raw_prices),
    }


def main() -> None:
    files = sorted(
        path
        for path in RAW_DATA_DIR.rglob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    )

    if not files:
        print(f"No supported files found in: {RAW_DATA_DIR}")
        return

    rows = []
    for index, file_path in enumerate(files, start=1):
        print(f"[{index}/{len(files)}] Profiling: {file_path.name}")
        try:
            rows.append(profile_file(file_path))
        except Exception as error:
            rows.append(
                {
                    "file_name": file_path.name,
                    "declared_extension": file_path.suffix.lower() or "<none>",
                    "detected_format": detect_content_format(file_path),
                    "rows": None,
                    "price_column": "<read failed>",
                    "non_null_prices": None,
                    "parseable_prices": None,
                    "unparseable_non_null": None,
                    "zero_prices": None,
                    "min_numeric_price": None,
                    "median_numeric_price": None,
                    "max_numeric_price": None,
                    "explicit_unit_evidence": f"ERROR: {type(error).__name__}",
                    "sample_raw_prices": str(error),
                }
            )

    report = pd.DataFrame(rows)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    report.to_csv(REPORT_PATH, index=False, encoding="utf-8-sig")

    display_columns = [
        "file_name",
        "price_column",
        "rows",
        "non_null_prices",
        "parseable_prices",
        "zero_prices",
        "explicit_unit_evidence",
        "sample_raw_prices",
    ]

    print("\n" + "=" * 150)
    print("CURRENCY AND PRICE PROFILING SUMMARY")
    print("=" * 150)
    print(report[display_columns].to_string(index=False))
    print("\nSaved CSV report:", REPORT_PATH.relative_to(PROJECT_ROOT))
    print("\nImportant: this report identifies explicit unit labels and price patterns; it does not infer whether unlabeled values are IRR or TOMAN.")


if __name__ == "__main__":
    main()