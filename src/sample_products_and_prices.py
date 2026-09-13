from __future__ import annotations

from pathlib import Path

import pandas as pd

from extract import detect_content_format, read_csv_with_fallbacks


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"
REPORT_PATH = PROJECT_ROOT / "data" / "processed" / "product_price_samples.csv"
SUPPORTED_EXTENSIONS = {".csv", ".tsv", ".xlsx", ".xls", ".parquet"}
TITLE_COLUMNS = ["product_name", "Product Title", "title"]
PRICE_COLUMNS = ["Product Price", "current_price", "sale_price", "price"]
SAMPLES_PER_FILE = 5
RANDOM_SEED = 20260912


def read_file(file_path: Path) -> pd.DataFrame:
    content_format = detect_content_format(file_path)

    if content_format == "csv":
        return read_csv_with_fallbacks(file_path)
    if content_format == "xlsx":
        return pd.read_excel(file_path, engine="openpyxl")
    if content_format == "parquet":
        return pd.read_parquet(file_path)

    raise ValueError(f"Unsupported content format: {content_format}")


def first_existing_column(columns: pd.Index, candidates: list[str]) -> str | None:
    return next((column for column in candidates if column in columns), None)


def non_empty(series: pd.Series) -> pd.Series:
    return series.notna() & series.astype(str).str.strip().ne("")


def sample_file(file_path: Path) -> pd.DataFrame:
    dataframe = read_file(file_path)
    title_column = first_existing_column(dataframe.columns, TITLE_COLUMNS)
    price_column = first_existing_column(dataframe.columns, PRICE_COLUMNS)

    if title_column is None or price_column is None:
        return pd.DataFrame(
            [{
                "file_name": file_path.name,
                "source_row_number": None,
                "product_title": None,
                "raw_price": None,
                "title_column": title_column or "<not found>",
                "price_column": price_column or "<not found>",
                "note": "Required title or price column was not found.",
            }]
        )

    eligible = dataframe.loc[
        non_empty(dataframe[title_column]) & non_empty(dataframe[price_column]),
        [title_column, price_column],
    ].copy()

    if eligible.empty:
        return pd.DataFrame(
            [{
                "file_name": file_path.name,
                "source_row_number": None,
                "product_title": None,
                "raw_price": None,
                "title_column": title_column,
                "price_column": price_column,
                "note": "No row has both a non-empty product title and price.",
            }]
        )

    sample_size = min(SAMPLES_PER_FILE, len(eligible))
    sampled = eligible.sample(
        n=sample_size,
        random_state=RANDOM_SEED,
    ).sort_index()

    result = pd.DataFrame(
        {
            "file_name": file_path.name,
            "source_row_number": sampled.index + 1,
            "product_title": sampled[title_column].astype(str).str.replace(r"\s+", " ", regex=True).str.strip(),
            "raw_price": sampled[price_column].astype(str).str.strip(),
            "title_column": title_column,
            "price_column": price_column,
            "note": None,
        }
    )

    return result


def main() -> None:
    files = sorted(
        path
        for path in RAW_DATA_DIR.rglob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    )

    if not files:
        print(f"No supported files found in: {RAW_DATA_DIR}")
        return

    samples = []

    for index, file_path in enumerate(files, start=1):
        print(f"[{index}/{len(files)}] Sampling: {file_path.name}")
        try:
            samples.append(sample_file(file_path))
        except Exception as error:
            samples.append(
                pd.DataFrame(
                    [{
                        "file_name": file_path.name,
                        "source_row_number": None,
                        "product_title": None,
                        "raw_price": None,
                        "title_column": None,
                        "price_column": None,
                        "note": f"READ FAILED: {type(error).__name__}: {error}",
                    }]
                )
            )

    report = pd.concat(samples, ignore_index=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    report.to_csv(REPORT_PATH, index=False, encoding="utf-8-sig")

    print("\n" + "=" * 140)
    print("PRODUCT AND RAW-PRICE SAMPLES")
    print("=" * 140)

    for file_name, group in report.groupby("file_name", sort=False):
        print(f"\nFILE: {file_name}")
        print(group.drop(columns="file_name").to_string(index=False))

    print("\nSaved CSV report:", REPORT_PATH.relative_to(PROJECT_ROOT))
    print("The same deterministic five samples are returned on each run unless the source file changes.")


if __name__ == "__main__":
    main()