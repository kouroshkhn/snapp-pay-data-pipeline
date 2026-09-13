from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
STAGING_DIR = PROJECT_ROOT / "data" / "processed" / "staging"
QUALITY_DIR = PROJECT_ROOT / "data" / "processed" / "quality"

CHUNK_SIZE = 100_000

SOURCE_ID_RULE = "DUPLICATE_SOURCE_ID"
FALLBACK_RULE = "DUPLICATE_FALLBACK_KEY"


def clean_key_value(value: object) -> str:
    if pd.isna(value):
        return ""

    return str(value).strip().casefold()


def build_source_id_key(row: pd.Series) -> str | None:
    source = clean_key_value(row["source"])
    source_id = clean_key_value(row["source_id"])
    merchant = clean_key_value(row["merchant_name_raw"])

    if not source or not source_id:
        return None

    return "|".join(
        [
            SOURCE_ID_RULE,
            source,
            source_id,
            merchant,
        ]
    )


def build_fallback_key(row: pd.Series) -> str | None:
    source = clean_key_value(row["source"])
    source_id = clean_key_value(row["source_id"])
    title = clean_key_value(row["product_title_normalized"])
    merchant = clean_key_value(row["merchant_name_raw"])
    price = clean_key_value(row["price"])

    if source_id:
        return None

    if not source or not title or not price:
        return None

    return "|".join(
        [
            FALLBACK_RULE,
            source,
            title,
            merchant,
            price,
        ]
    )


def find_staging_files() -> list[Path]:
    return sorted(STAGING_DIR.glob("*__staging.csv"))


def count_duplicate_keys(staging_files: list[Path]) -> Counter[str]:
    key_counts: Counter[str] = Counter()

    use_columns = [
        "source",
        "source_id",
        "product_title_normalized",
        "merchant_name_raw",
        "price",
    ]

    for file_number, staging_file in enumerate(staging_files, start=1):
        print(
            f"[Pass 1 | {file_number}/{len(staging_files)}] "
            f"Counting keys: {staging_file.name}"
        )

        for chunk in pd.read_csv(
            staging_file,
            usecols=use_columns,
            dtype="string",
            chunksize=CHUNK_SIZE,
        ):
            for _, row in chunk.iterrows():
                duplicate_key = build_source_id_key(row)

                if duplicate_key is None:
                    duplicate_key = build_fallback_key(row)

                if duplicate_key is not None:
                    key_counts[duplicate_key] += 1

    return key_counts


def write_duplicate_candidates(
    staging_files: list[Path],
    key_counts: Counter[str],
) -> dict[str, object]:
    QUALITY_DIR.mkdir(parents=True, exist_ok=True)

    candidates_path = QUALITY_DIR / "duplicate_candidates.csv"
    summary_path = QUALITY_DIR / "duplicate_summary.json"

    use_columns = [
        "source",
        "dataset",
        "source_id",
        "product_title",
        "product_title_normalized",
        "merchant_name_raw",
        "price",
        "source_file_name",
        "source_row_number",
    ]

    fieldnames = [
        "source_file_name",
        "source_row_number",
        "source",
        "dataset",
        "rule_code",
        "duplicate_key",
        "duplicate_group_size",
        "duplicate_rank",
        "is_core_canonical",
        "source_id",
        "product_title",
        "merchant_name_raw",
        "price",
    ]

    candidate_count = 0
    duplicate_groups: Counter[str] = Counter()
    duplicate_candidates_by_source: Counter[str] = Counter()
    duplicate_candidates_by_rule: Counter[str] = Counter()

    core_rows_to_skip = 0
    core_rows_to_keep = 0

    seen_duplicate_rank: Counter[str] = Counter()

    with candidates_path.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as output_file:
        writer = csv.DictWriter(
            output_file,
            fieldnames=fieldnames,
        )
        writer.writeheader()

        for file_number, staging_file in enumerate(staging_files, start=1):
            print(
                f"[Pass 2 | {file_number}/{len(staging_files)}] "
                f"Writing candidates: {staging_file.name}"
            )

            for chunk in pd.read_csv(
                staging_file,
                usecols=use_columns,
                dtype="string",
                chunksize=CHUNK_SIZE,
            ):
                for _, row in chunk.iterrows():
                    duplicate_key = build_source_id_key(row)

                    if duplicate_key is None:
                        duplicate_key = build_fallback_key(row)

                    if duplicate_key is None:
                        continue

                    duplicate_group_size = key_counts[duplicate_key]

                    if duplicate_group_size < 2:
                        continue

                    rule_code = duplicate_key.split("|", maxsplit=1)[0]

                    seen_duplicate_rank[duplicate_key] += 1
                    duplicate_rank = seen_duplicate_rank[duplicate_key]

                    is_core_canonical = (
                        rule_code != SOURCE_ID_RULE
                        or duplicate_rank == 1
                    )

                    if is_core_canonical:
                        core_rows_to_keep += 1
                    else:
                        core_rows_to_skip += 1

                    writer.writerow(
                        {
                            "source_file_name": row["source_file_name"],
                            "source_row_number": row["source_row_number"],
                            "source": row["source"],
                            "dataset": row["dataset"],
                            "rule_code": rule_code,
                            "duplicate_key": duplicate_key,
                            "duplicate_group_size": duplicate_group_size,
                            "duplicate_rank": duplicate_rank,
                            "is_core_canonical": is_core_canonical,
                            "source_id": row["source_id"],
                            "product_title": row["product_title"],
                            "merchant_name_raw": row["merchant_name_raw"],
                            "price": row["price"],
                        }
                    )

                    candidate_count += 1
                    duplicate_groups[duplicate_key] = duplicate_group_size
                    duplicate_candidates_by_source[str(row["source"])] += 1
                    duplicate_candidates_by_rule[rule_code] += 1

    summary = {
        "detected_at_utc": datetime.now(timezone.utc).isoformat(),
        "staging_file_count": len(staging_files),
        "duplicate_candidate_record_count": candidate_count,
        "duplicate_group_count": len(duplicate_groups),
        "core_canonical_duplicate_candidate_count": core_rows_to_keep,
        "core_rows_to_skip_due_to_source_id_duplicate": core_rows_to_skip,
        "duplicate_candidates_by_source": dict(
            sorted(duplicate_candidates_by_source.items())
        ),
        "duplicate_candidates_by_rule": dict(
            sorted(duplicate_candidates_by_rule.items())
        ),
        "largest_duplicate_groups": [
            {
                "duplicate_key": key,
                "group_size": count,
            }
            for key, count in key_counts.most_common(20)
            if count >= 2
        ],
    }

    summary_path.write_text(
        json.dumps(
            summary,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return {
        "candidates_path": candidates_path,
        "summary_path": summary_path,
        **summary,
    }


def main() -> None:
    staging_files = find_staging_files()

    if not staging_files:
        raise FileNotFoundError(
            f"No staging CSV files found in: {STAGING_DIR}"
        )

    print(f"Staging files found: {len(staging_files)}")
    print()

    key_counts = count_duplicate_keys(staging_files)

    result = write_duplicate_candidates(
        staging_files=staging_files,
        key_counts=key_counts,
    )

    print("\nDuplicate detection completed successfully.")
    print(
        "Duplicate-candidate records: "
        f"{result['duplicate_candidate_record_count']:,}"
    )
    print(
        "Duplicate groups: "
        f"{result['duplicate_group_count']:,}"
    )
    print(
        "Core rows skipped because of confirmed "
        "source-ID duplicates: "
        f"{result['core_rows_to_skip_due_to_source_id_duplicate']:,}"
    )
    print(
        "Candidate output: "
        f"{result['candidates_path'].relative_to(PROJECT_ROOT)}"
    )
    print(
        "Summary output: "
        f"{result['summary_path'].relative_to(PROJECT_ROOT)}"
    )


if __name__ == "__main__":
    main()