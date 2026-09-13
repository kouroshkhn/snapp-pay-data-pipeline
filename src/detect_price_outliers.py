from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
STAGING_DIR = PROJECT_ROOT / "data" / "processed" / "staging"
QUALITY_DIR = PROJECT_ROOT / "data" / "processed" / "quality"

MIN_CATEGORY_RECORDS = 30
IQR_MULTIPLIER = 3.0

OUTLIER_RULE = "PRICE_OUTLIER"


def clean_group_value(value: object) -> str | None:
    if pd.isna(value):
        return None

    text = str(value).strip()

    return text if text else None


def build_analysis_group(dataframe: pd.DataFrame) -> pd.Series:
    category = dataframe["category_raw"].map(clean_group_value)

    category_counts = category.value_counts(dropna=True)

    category_is_large_enough = category.map(category_counts).fillna(0) >= MIN_CATEGORY_RECORDS

    fallback_group = (
        dataframe["source"].astype(str)
        + "|"
        + dataframe["dataset"].astype(str)
        + "|__DATASET_FALLBACK__"
    )

    category_group = (
        dataframe["source"].astype(str)
        + "|"
        + dataframe["dataset"].astype(str)
        + "|CATEGORY|"
        + category.fillna("")
    )

    return category_group.where(
        category_is_large_enough,
        fallback_group,
    )


def detect_outliers_in_file(staging_file: Path) -> pd.DataFrame:
    dataframe = pd.read_csv(
        staging_file,
        usecols=[
            "source",
            "dataset",
            "category_raw",
            "price",
            "source_file_name",
            "source_row_number",
            "product_title",
        ],
        dtype={
            "source": "string",
            "dataset": "string",
            "category_raw": "string",
            "source_file_name": "string",
            "product_title": "string",
        },
    )

    dataframe["price"] = pd.to_numeric(
        dataframe["price"],
        errors="coerce",
    )

    dataframe["analysis_group"] = build_analysis_group(dataframe)

    valid_price_mask = dataframe["price"].notna() & (dataframe["price"] > 0)

    valid_prices = dataframe.loc[
        valid_price_mask,
        [
            "source",
            "dataset",
            "category_raw",
            "price",
            "source_file_name",
            "source_row_number",
            "product_title",
            "analysis_group",
        ],
    ].copy()

    if valid_prices.empty:
        return pd.DataFrame()

    valid_prices["log_price"] = np.log10(valid_prices["price"])

    grouped = valid_prices.groupby("analysis_group")["log_price"]

    valid_prices["group_record_count"] = grouped.transform("size")
    valid_prices["q1_log_price"] = grouped.transform(
        lambda series: series.quantile(0.25)
    )
    valid_prices["q3_log_price"] = grouped.transform(
        lambda series: series.quantile(0.75)
    )

    valid_prices["iqr_log_price"] = (
        valid_prices["q3_log_price"]
        - valid_prices["q1_log_price"]
    )

    valid_prices["lower_log_limit"] = (
        valid_prices["q1_log_price"]
        - IQR_MULTIPLIER * valid_prices["iqr_log_price"]
    )

    valid_prices["upper_log_limit"] = (
        valid_prices["q3_log_price"]
        + IQR_MULTIPLIER * valid_prices["iqr_log_price"]
    )

    valid_prices["is_price_outlier"] = (
        valid_prices["log_price"] < valid_prices["lower_log_limit"]
    ) | (
        valid_prices["log_price"] > valid_prices["upper_log_limit"]
    )

    outliers = valid_prices.loc[
        valid_prices["is_price_outlier"],
        [
            "source_file_name",
            "source_row_number",
            "source",
            "dataset",
            "category_raw",
            "product_title",
            "price",
            "analysis_group",
            "group_record_count",
            "q1_log_price",
            "q3_log_price",
            "iqr_log_price",
            "lower_log_limit",
            "upper_log_limit",
        ],
    ].copy()

    outliers.insert(4, "rule_code", OUTLIER_RULE)
    outliers.insert(5, "severity", "WARNING")
    outliers.insert(6, "action_taken", "FLAG")

    return outliers


def main() -> None:
    staging_files = sorted(STAGING_DIR.glob("*__staging.csv"))

    if not staging_files:
        raise FileNotFoundError(
            f"No staging files found in: {STAGING_DIR}"
        )

    QUALITY_DIR.mkdir(parents=True, exist_ok=True)

    outlier_frames = []

    for number, staging_file in enumerate(staging_files, start=1):
        print(
            f"[{number}/{len(staging_files)}] "
            f"Checking outliers: {staging_file.name}"
        )

        outliers = detect_outliers_in_file(staging_file)
        outlier_frames.append(outliers)

        print(f"  Price outliers found: {len(outliers):,}")

    non_empty_frames = [
        frame
        for frame in outlier_frames
        if not frame.empty
    ]

    if non_empty_frames:
        all_outliers = pd.concat(
            non_empty_frames,
            ignore_index=True,
        )
    else:
        all_outliers = pd.DataFrame(
            columns=[
                "source_file_name",
                "source_row_number",
                "source",
                "dataset",
                "rule_code",
                "severity",
                "action_taken",
                "category_raw",
                "product_title",
                "price",
            ]
        )

    outliers_path = QUALITY_DIR / "price_outliers.csv"

    all_outliers.to_csv(
        outliers_path,
        index=False,
        encoding="utf-8-sig",
    )

    outliers_by_source = (
        all_outliers.groupby("source")
        .size()
        .sort_values(ascending=False)
        .to_dict()
        if not all_outliers.empty
        else {}
    )

    outliers_by_dataset = (
        all_outliers.groupby(["source", "dataset"])
        .size()
        .sort_values(ascending=False)
        .to_dict()
        if not all_outliers.empty
        else {}
    )

    summary = {
        "detected_at_utc": datetime.now(timezone.utc).isoformat(),
        "method": "log10_price_iqr",
        "iqr_multiplier": IQR_MULTIPLIER,
        "minimum_category_records": MIN_CATEGORY_RECORDS,
        "outlier_record_count": int(len(all_outliers)),
        "outliers_by_source": {
            str(key): int(value)
            for key, value in outliers_by_source.items()
        },
        "outliers_by_dataset": {
            f"{source}|{dataset}": int(count)
            for (source, dataset), count
            in outliers_by_dataset.items()
        },
    }

    summary_path = QUALITY_DIR / "price_outlier_summary.json"

    summary_path.write_text(
        json.dumps(
            summary,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("\nPrice-outlier detection completed successfully.")
    print(f"Outlier records: {len(all_outliers):,}")
    print(
        "Outlier detail output: "
        f"{outliers_path.relative_to(PROJECT_ROOT)}"
    )
    print(
        "Outlier summary output: "
        f"{summary_path.relative_to(PROJECT_ROOT)}"
    )


if __name__ == "__main__":
    main()