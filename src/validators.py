from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
STAGING_DIR = PROJECT_ROOT / "data" / "processed" / "staging"
VALIDATION_OUTPUT_DIR = PROJECT_ROOT / "data" / "processed" / "validation"

SEVERITY_ERROR = "ERROR"
SEVERITY_WARNING = "WARNING"
SEVERITY_INFO = "INFO"

ACTION_QUARANTINE = "QUARANTINE"
ACTION_FLAG = "FLAG"
ACTION_ACCEPT = "ACCEPT"


@dataclass
class ValidationIssue:
    source_file_name: str
    source_row_number: int | None
    source: str | None
    dataset: str | None
    rule_code: str
    severity: str
    action_taken: str
    field_name: str | None
    observed_value: str | None
    issue_message: str
    issue_details: dict[str, object]


def clean_observed_value(value: object) -> str | None:
    if pd.isna(value):
        return None

    text = str(value).strip()
    return text[:500] if text else None


def is_valid_http_url(value: object) -> bool:
    if pd.isna(value) or not str(value).strip():
        return True

    text = str(value).strip()

    if text.startswith("[") and "](" in text and text.endswith(")"):
        text = text.split("](", maxsplit=1)[1][:-1]

    parsed = urlparse(text)

    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def add_issue(
    issues: list[ValidationIssue],
    row: pd.Series,
    rule_code: str,
    severity: str,
    action_taken: str,
    field_name: str | None,
    observed_value: object,
    issue_message: str,
    issue_details: dict[str, object] | None = None,
) -> None:
    issues.append(
        ValidationIssue(
            source_file_name=str(row["source_file_name"]),
            source_row_number=int(row["source_row_number"]),
            source=str(row["source"]),
            dataset=str(row["dataset"]),
            rule_code=rule_code,
            severity=severity,
            action_taken=action_taken,
            field_name=field_name,
            observed_value=clean_observed_value(observed_value),
            issue_message=issue_message,
            issue_details=issue_details or {},
        )
    )


def validate_file(staging_file: Path) -> list[ValidationIssue]:
    dataframe = pd.read_csv(
        staging_file,
        dtype={
            "source": "string",
            "dataset": "string",
            "source_id": "string",
            "product_title": "string",
            "product_title_normalized": "string",
            "brand_raw": "string",
            "category_raw": "string",
            "merchant_name_raw": "string",
            "availability_raw": "string",
            "product_url": "string",
            "image_url": "string",
            "search_keyword": "string",
            "source_price_unit": "string",
            "currency_code": "string",
            "transform_status": "string",
            "transform_notes": "string",
            "source_file_name": "string",
        },
    )

    issues: list[ValidationIssue] = []

    for _, row in dataframe.iterrows():
        title = row["product_title"]
        price = row["price"]
        old_price = row["old_price"]
        discount_percent = row["discount_percent"]
        cash_back_percent = row["cash_back_percent"]

        if pd.isna(title) or not str(title).strip():
            add_issue(
                issues=issues,
                row=row,
                rule_code="REQ_TITLE",
                severity=SEVERITY_ERROR,
                action_taken=ACTION_QUARANTINE,
                field_name="product_title",
                observed_value=title,
                issue_message="Product title is missing or blank.",
            )

        if pd.isna(price):
            add_issue(
                issues=issues,
                row=row,
                rule_code="MISSING_PRICE",
                severity=SEVERITY_WARNING,
                action_taken=ACTION_FLAG,
                field_name="price",
                observed_value=price,
                issue_message="Price is missing after transformation.",
            )
        elif price < 0:
            add_issue(
                issues=issues,
                row=row,
                rule_code="NEGATIVE_PRICE",
                severity=SEVERITY_ERROR,
                action_taken=ACTION_QUARANTINE,
                field_name="price",
                observed_value=price,
                issue_message="Price is negative after transformation.",
            )
        elif price == 0:
            add_issue(
                issues=issues,
                row=row,
                rule_code="ZERO_PRICE",
                severity=SEVERITY_WARNING,
                action_taken=ACTION_FLAG,
                field_name="price",
                observed_value=price,
                issue_message="Price is zero and should be reviewed.",
            )

        if not pd.isna(old_price) and old_price < 0:
            add_issue(
                issues=issues,
                row=row,
                rule_code="NEGATIVE_OLD_PRICE",
                severity=SEVERITY_ERROR,
                action_taken=ACTION_QUARANTINE,
                field_name="old_price",
                observed_value=old_price,
                issue_message="Old price is negative after transformation.",
            )

        if (
            not pd.isna(price)
            and not pd.isna(old_price)
            and price > 0
            and old_price > 0
            and old_price < price
        ):
            add_issue(
                issues=issues,
                row=row,
                rule_code="OLD_PRICE_LT_PRICE",
                severity=SEVERITY_WARNING,
                action_taken=ACTION_FLAG,
                field_name="old_price",
                observed_value=old_price,
                issue_message="Old price is lower than current price.",
                issue_details={
                    "price": float(price),
                    "old_price": float(old_price),
                },
            )

        for column_name, value in {
            "discount_percent": discount_percent,
            "cash_back_percent": cash_back_percent,
        }.items():
            if not pd.isna(value) and (value < 0 or value > 100):
                add_issue(
                    issues=issues,
                    row=row,
                    rule_code="INVALID_PERCENTAGE",
                    severity=SEVERITY_WARNING,
                    action_taken=ACTION_FLAG,
                    field_name=column_name,
                    observed_value=value,
                    issue_message=(
                        f"{column_name} is outside the allowed range of 0 to 100."
                    ),
                )

        for column_name in ("product_url", "image_url"):
            value = row[column_name]

            if not is_valid_http_url(value):
                add_issue(
                    issues=issues,
                    row=row,
                    rule_code="INVALID_URL",
                    severity=SEVERITY_WARNING,
                    action_taken=ACTION_FLAG,
                    field_name=column_name,
                    observed_value=value,
                    issue_message=f"{column_name} is not a valid HTTP/HTTPS URL.",
                )

    return issues


def build_file_level_issues() -> list[ValidationIssue]:
    return [
        ValidationIssue(
            source_file_name="arkaapi_first_50_pages.xlsx",
            source_row_number=None,
            source="arka",
            dataset="all_categories_first_50_pages",
            rule_code="INVALID_AVAILABILITY_COLUMN",
            severity=SEVERITY_WARNING,
            action_taken=ACTION_FLAG,
            field_name="availability",
            observed_value=None,
            issue_message=(
                "Arka availability values cannot be interpreted as stock status. "
                "is_available was set to NULL."
            ),
            issue_details={"affected_rows": 130700},
        ),
        ValidationIssue(
            source_file_name="SnappPay - Digital Accessories - 2026-08-23.xlsx",
            source_row_number=None,
            source="snapp_pay",
            dataset="digital_accessories",
            rule_code="FILE_EXTENSION_CONTENT_MISMATCH",
            severity=SEVERITY_WARNING,
            action_taken=ACTION_FLAG,
            field_name="file_extension",
            observed_value="xlsx",
            issue_message=(
                "The filename uses .xlsx, but file-content inspection identified CSV data."
            ),
            issue_details={
                "declared_extension": "xlsx",
                "detected_format": "csv",
            },
        ),
    ]


def main() -> None:
    staging_files = sorted(STAGING_DIR.glob("*__staging.csv"))

    if not staging_files:
        raise FileNotFoundError(
            f"No staging output files found in: {STAGING_DIR}"
        )

    all_issues = build_file_level_issues()
    file_summaries = []

    for number, staging_file in enumerate(staging_files, start=1):
        print(f"[{number}/{len(staging_files)}] Validating: {staging_file.name}")

        file_issues = validate_file(staging_file)
        all_issues.extend(file_issues)

        file_summaries.append(
            {
                "staging_file": staging_file.name,
                "issue_count": len(file_issues),
                "error_count": sum(
                    issue.severity == SEVERITY_ERROR
                    for issue in file_issues
                ),
                "warning_count": sum(
                    issue.severity == SEVERITY_WARNING
                    for issue in file_issues
                ),
            }
        )

        print(
            f"  Issues={len(file_issues):,} "
            f"| Errors={file_summaries[-1]['error_count']:,} "
            f"| Warnings={file_summaries[-1]['warning_count']:,}"
        )

    VALIDATION_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    issue_rows = []

    for issue in all_issues:
        issue_rows.append(
            {
                **asdict(issue),
                "issue_details": json.dumps(
                    issue.issue_details,
                    ensure_ascii=False,
                ),
            }
        )

    issues_dataframe = pd.DataFrame(issue_rows)

    issues_path = VALIDATION_OUTPUT_DIR / "validation_issues.csv"
    issues_dataframe.to_csv(
        issues_path,
        index=False,
        encoding="utf-8-sig",
    )

    summary = {
        "validated_at_utc": datetime.now(timezone.utc).isoformat(),
        "staging_file_count": len(staging_files),
        "total_issue_count": len(all_issues),
        "error_count": sum(
            issue.severity == SEVERITY_ERROR
            for issue in all_issues
        ),
        "warning_count": sum(
            issue.severity == SEVERITY_WARNING
            for issue in all_issues
        ),
        "info_count": sum(
            issue.severity == SEVERITY_INFO
            for issue in all_issues
        ),
        "issues_by_rule": {
            rule_code: sum(
                issue.rule_code == rule_code
                for issue in all_issues
            )
            for rule_code in sorted(
                {issue.rule_code for issue in all_issues}
            )
        },
        "files": file_summaries,
    }

    summary_path = VALIDATION_OUTPUT_DIR / "validation_summary.json"
    summary_path.write_text(
        json.dumps(
            summary,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("\nValidation completed successfully.")
    print(f"Validation issues: {issues_path.relative_to(PROJECT_ROOT)}")
    print(f"Validation summary: {summary_path.relative_to(PROJECT_ROOT)}")
    print(f"Total issues: {summary['total_issue_count']:,}")
    print(f"Errors: {summary['error_count']:,}")
    print(f"Warnings: {summary['warning_count']:,}")


if __name__ == "__main__":
    main()