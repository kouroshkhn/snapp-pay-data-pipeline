from __future__ import annotations

from pathlib import Path

import pandas as pd

from extract import detect_content_format, read_csv_with_fallbacks


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"

VALUE_COLUMNS = [
    "Product Price",
    "price",
    "sale_price",
    "current_price",
    "regular_price",
    "old_price",
    "discount",
    "cash_back",
    "availability",
    "available",
    "brand",
    "category",
    "category_name",
    "merchant_name",
    "seller_name",
]

def read_file(file_path: Path) -> pd.DataFrame:
    content_format = detect_content_format(file_path)

    if content_format == "csv":
        return read_csv_with_fallbacks(file_path)

    if content_format == "xlsx":
        return pd.read_excel(file_path, engine="openpyxl")

    raise ValueError(
        f"Unsupported content format for inspection: {content_format}"
    )


def format_value(value: object) -> str:
    if pd.isna(value):
        return "<NULL>"

    text = str(value).replace("\n", " ").strip()
    return text[:160] if text else "<EMPTY>"


def main() -> None:
    files = sorted(
        path
        for path in RAW_DATA_DIR.rglob("*")
        if path.is_file()
        and path.suffix.lower() in {".csv", ".tsv", ".xlsx", ".xls", ".parquet"}
    )

    print(f"Raw directory: {RAW_DATA_DIR}")
    print(f"Supported files found: {len(files)}")

    if not files:
        print("No supported files were found.")
        return

    for file_path in files:
        print("\n" + "=" * 100)
        print(f"Reading file: {file_path.name}")

        try:
            dataframe = read_file(file_path)
        except Exception as error:
            print(f"FAILED TO READ: {type(error).__name__}: {error}")
            continue

        print(f"ROWS: {len(dataframe):,}")
        print("=" * 100)

        available_columns = [
            column for column in VALUE_COLUMNS if column in dataframe.columns
        ]

        if not available_columns:
            print(
                "No configured price, availability, brand, "
                "category, or merchant columns."
            )
            continue

        for column in available_columns:
            series = dataframe[column]

            print(f"\nCOLUMN: {column}")
            print(f"Null count: {series.isna().sum():,}")
            print(f"Unique values: {series.nunique(dropna=True):,}")
            print("Top values:")

            counts = series.fillna("<NULL>").astype(str).value_counts().head(10)

            for value, count in counts.items():
                print(f"  {count:>10,} | {format_value(value)}")


if __name__ == "__main__":
    main()