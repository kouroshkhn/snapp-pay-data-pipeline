from __future__ import annotations

import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from config import get_db_config
from extract import PROJECT_ROOT, RAW_DATA_DIR, SUPPORTED_EXTENSIONS
from transform import main as run_transform
from validators import main as run_validation
from detect_duplicates import main as run_duplicate_detection
from detect_price_outliers import main as run_outlier_detection
from load_pipeline import main as run_load
from metrics import calculate_all_metrics, print_metric_summary

import psycopg


def check_prerequisites() -> None:
    """Check that all required files and settings exist."""
    raw_files = [
        p for p in RAW_DATA_DIR.glob("*")
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
    ]

    if len(raw_files) != 15:
        raise RuntimeError(
            f"Expected 15 raw data files; found {len(raw_files)}."
        )

    required_scripts = [
        PROJECT_ROOT / "src" / "transform.py",
        PROJECT_ROOT / "src" / "validators.py",
        PROJECT_ROOT / "src" / "detect_duplicates.py",
        PROJECT_ROOT / "src" / "detect_price_outliers.py",
        PROJECT_ROOT / "src" / "load_pipeline.py",
    ]

    for script in required_scripts:
        if not script.exists():
            raise FileNotFoundError(f"Required script not found: {script}")

    try:
        get_db_config()
    except RuntimeError as error:
        raise RuntimeError(f"Database configuration error: {error}") from error

    print("✓ All prerequisites satisfied.")


def run_pipeline(full_run: bool = True) -> dict[str, object]:
    """Run the complete ETL pipeline."""
    start_time = datetime.now(timezone.utc)
    results: dict[str, object] = {
        "started_at": start_time.isoformat(),
        "steps": {},
        "errors": [],
    }

    print("\n" + "=" * 70)
    print("Snapp Pay Data Pipeline - Starting")
    print("=" * 70 + "\n")

    try:
        # Step 1: Transform
        print("[1/5] Running Transform...")
        step_start = time.time()
        run_transform()
        results["steps"]["transform"] = {
            "status": "SUCCESS",
            "duration_seconds": round(time.time() - step_start, 2),
        }
        print("✓ Transform completed.\n")

        # Step 2: Validation
        print("[2/5] Running Validation...")
        step_start = time.time()
        run_validation()
        results["steps"]["validation"] = {
            "status": "SUCCESS",
            "duration_seconds": round(time.time() - step_start, 2),
        }
        print("✓ Validation completed.\n")

        # Step 3: Duplicate Detection
        print("[3/5] Running Duplicate Detection...")
        step_start = time.time()
        run_duplicate_detection()
        results["steps"]["duplicate_detection"] = {
            "status": "SUCCESS",
            "duration_seconds": round(time.time() - step_start, 2),
        }
        print("✓ Duplicate detection completed.\n")

        # Step 4: Outlier Detection
        print("[4/5] Running Outlier Detection...")
        step_start = time.time()
        run_outlier_detection()
        results["steps"]["outlier_detection"] = {
            "status": "SUCCESS",
            "duration_seconds": round(time.time() - step_start, 2),
        }
        print("✓ Outlier detection completed.\n")

        # Step 5: Load to PostgreSQL
        print("[5/5] Loading to PostgreSQL...")
        step_start = time.time()
        run_load()
        results["steps"]["load"] = {
            "status": "SUCCESS",
            "duration_seconds": round(time.time() - step_start, 2),
        }
        print("✓ Load completed.\n")

        # Optional: Calculate and display metrics
        if full_run:
            print("[BONUS] Calculating analytics metrics...")
            calculate_all_metrics()
            print_metric_summary()
            print("✓ Metrics calculated.\n")

    except Exception as error:
        results["errors"].append({
            "step": list(results["steps"].keys())[-1] if results["steps"] else "unknown",
            "error": str(error),
            "type": type(error).__name__,
        })
        print(f"\n✗ Pipeline failed at step: {results['steps'].keys()[-1] if results['steps'] else 'unknown'}")
        print(f"Error: {error}")
        raise

    end_time = datetime.now(timezone.utc)
    results["finished_at"] = end_time.isoformat()
    results["total_duration_seconds"] = round(
        (end_time - start_time).total_seconds(), 2
    )

    print("=" * 70)
    print("Pipeline completed successfully!")
    print(f"Total duration: {results['total_duration_seconds']:,} seconds")
    print("=" * 70 + "\n")

    return results


def main() -> None:
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Snapp Pay Data Pipeline"
    )
    parser.add_argument(
        "--skip-transform",
        action="store_true",
        help="Skip transform step if already done",
    )
    parser.add_argument(
        "--skip-validation",
        action="store_true",
        help="Skip validation step if already done",
    )
    parser.add_argument(
        "--skip-duplicates",
        action="store_true",
        help="Skip duplicate detection if already done",
    )
    parser.add_argument(
        "--skip-outliers",
        action="store_true",
        help="Skip outlier detection if already done",
    )
    parser.add_argument(
        "--skip-load",
        action="store_true",
        help="Skip load step if already done",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Check prerequisites without running",
    )

    args = parser.parse_args()

    if args.dry_run:
        print("Running in dry-run mode (prerequisites check only)...")
        check_prerequisites()
        print("\n✓ Dry run completed. All checks passed.")
        return

    try:
        check_prerequisites()
        results = run_pipeline(full_run=not any([
            args.skip_transform,
            args.skip_validation,
            args.skip_duplicates,
            args.skip_outliers,
            args.skip_load,
        ]))
    except Exception as error:
        print("\n" + "=" * 70)
        print("Pipeline execution failed!")
        print("=" * 70)
        sys.exit(1)


if __name__ == "__main__":
    main()