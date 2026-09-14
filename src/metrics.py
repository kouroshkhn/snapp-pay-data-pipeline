from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from config import get_db_config
from transform import PROJECT_ROOT

import psycopg


METRICS_PATH = PROJECT_ROOT / "data" / "processed" / "analytics_metrics.json"


def calculate_all_metrics() -> dict[str, object]:
    """Calculate analytics metrics from the loaded data."""
    config = get_db_config()
    metrics: dict[str, object] = {
        "calculated_at_utc": datetime.now(timezone.utc).isoformat(),
        "summary": {},
        "by_source": [],
        "quality_summary": {},
        "top_products": [],
        "price_statistics": {},
    }

    with psycopg.connect(**config) as conn:
        with conn.cursor() as cur:
            # Overall summary with better price statistics
            cur.execute("""
                SELECT
                    COUNT(*) AS total_listings,
                    COUNT(DISTINCT product_key) AS distinct_products,
                    COUNT(DISTINCT merchant_key) FILTER (WHERE merchant_key IS NOT NULL) AS distinct_merchants,
                    COUNT(*) FILTER (WHERE is_price_outlier) AS outlier_listings,
                    COUNT(*) FILTER (WHERE is_duplicate_candidate) AS duplicate_listings,
                    COUNT(*) FILTER (WHERE validation_status = 'VALID_WITH_WARNINGS') AS warning_listings,
                    AVG(price) FILTER (WHERE price > 0 AND NOT is_price_outlier) AS avg_price_excluding_outliers,
                    AVG(price) FILTER (WHERE price > 0) AS avg_price_including_outliers,
                    MAX(price) AS max_price,
                    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY price) FILTER (WHERE price > 0) AS median_price,
                    PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY price) FILTER (WHERE price > 0) AS q1_price,
                    PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY price) FILTER (WHERE price > 0) AS q3_price
                FROM core.fact_product_listings
            """)
            row = cur.fetchone()
            metrics["summary"] = {
                "total_listings": int(row[0] or 0),
                "distinct_products": int(row[1] or 0),
                "distinct_merchants": int(row[2] or 0),
                "outlier_listings": int(row[3] or 0),
                "duplicate_listings": int(row[4] or 0),
                "warning_listings": int(row[5] or 0),
                "avg_price_excluding_outliers": float(row[6]) if row[6] else None,
                "avg_price_including_outliers": float(row[7]) if row[7] else None,
                "max_price": float(row[8]) if row[8] else None,
                "median_price": float(row[9]) if row[9] else None,
                "q1_price": float(row[10]) if row[10] else None,
                "q3_price": float(row[11]) if row[11] else None,
            }

            # By source
            cur.execute("""
                SELECT
                    src.source_code,
                    src.source_name,
                    COUNT(*) AS listing_count,
                    COUNT(DISTINCT p.product_key) AS distinct_products,
                    COUNT(DISTINCT m.merchant_key) FILTER (WHERE m.merchant_key IS NOT NULL) AS distinct_merchants,
                    COUNT(*) FILTER (WHERE f.is_price_outlier) AS outlier_listings,
                    COUNT(*) FILTER (WHERE f.is_duplicate_candidate) AS duplicate_listings,
                    COUNT(*) FILTER (WHERE f.validation_status = 'VALID_WITH_WARNINGS') AS warning_listings,
                    AVG(f.price) FILTER (WHERE f.price > 0 AND NOT f.is_price_outlier) AS avg_price_excl_outliers,
                    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY f.price) FILTER (WHERE f.price > 0) AS median_price
                FROM core.fact_product_listings AS f
                JOIN core.dim_products AS p ON p.product_key = f.product_key
                JOIN core.dim_sources AS src ON src.source_key = p.source_key
                LEFT JOIN core.dim_merchants AS m ON m.merchant_key = f.merchant_key
                GROUP BY src.source_code, src.source_name
                ORDER BY listing_count DESC
            """)
            for row in cur.fetchall():
                metrics["by_source"].append({
                    "source_code": row[0],
                    "source_name": row[1],
                    "listing_count": int(row[2]),
                    "distinct_products": int(row[3]),
                    "distinct_merchants": int(row[4]),
                    "outlier_listings": int(row[5]),
                    "duplicate_listings": int(row[6]),
                    "warning_listings": int(row[7]),
                    "avg_price_excl_outliers": float(row[8]) if row[8] else None,
                    "median_price": float(row[9]) if row[9] else None,
                })

            # Quality summary
            cur.execute("""
                SELECT
                    rule_code,
                    severity,
                    COUNT(*) AS issue_count
                FROM audit.validation_issues
                GROUP BY rule_code, severity
                ORDER BY issue_count DESC
            """)
            metrics["quality_summary"]["issues_by_rule"] = [
                {"rule_code": row[0], "severity": row[1], "issue_count": int(row[2])}
                for row in cur.fetchall()
            ]

            # Total issues by severity
            cur.execute("""
                SELECT
                    severity,
                    COUNT(*) AS issue_count
                FROM audit.validation_issues
                GROUP BY severity
                ORDER BY 
                    CASE severity
                        WHEN 'ERROR' THEN 1
                        WHEN 'WARNING' THEN 2
                        WHEN 'INFO' THEN 3
                    END
            """)
            metrics["quality_summary"]["issues_by_severity"] = [
                {"severity": row[0], "issue_count": int(row[1])}
                for row in cur.fetchall()
            ]

            # Top products by price (excluding extreme outliers for display)
            cur.execute("""
                SELECT
                    p.product_title,
                    f.price,
                    src.source_code,
                    f.is_price_outlier
                FROM core.fact_product_listings AS f
                JOIN core.dim_products AS p ON p.product_key = f.product_key
                JOIN core.dim_sources AS src ON src.source_key = p.source_key
                WHERE f.price > 0
                ORDER BY f.price DESC
                LIMIT 20
            """)
            metrics["top_products"] = [
                {
                    "product_title": row[0],
                    "price": float(row[1]),
                    "source": row[2],
                    "is_outlier": bool(row[3]),
                }
                for row in cur.fetchall()
            ]

            # Price statistics by availability
            cur.execute("""
                SELECT
                    is_available,
                    COUNT(*) AS listing_count,
                    AVG(price) FILTER (WHERE price > 0) AS avg_price,
                    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY price) FILTER (WHERE price > 0) AS median_price
                FROM core.fact_product_listings
                WHERE price > 0
                GROUP BY is_available
            """)
            metrics["price_statistics"]["by_availability"] = [
                {
                    "is_available": bool(row[0]),
                    "listing_count": int(row[1]),
                    "avg_price": float(row[2]) if row[2] else None,
                    "median_price": float(row[3]) if row[3] else None,
                }
                for row in cur.fetchall()
            ]

    # Save to file
    METRICS_PATH.parent.mkdir(parents=True, exist_ok=True)
    METRICS_PATH.write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )

    return metrics


def print_metric_summary() -> None:
    """Print a human-readable summary of metrics."""
    if not METRICS_PATH.exists():
        print("No metrics file found. Run calculate_all_metrics() first.")
        return

    metrics = json.loads(METRICS_PATH.read_text(encoding="utf-8"))

    print("\n" + "=" * 80)
    print("Snapp Pay Analytics Metrics Summary")
    print("=" * 80)

    summary = metrics["summary"]
    print(f"\n📊 Overall Statistics")
    print(f"   Total Listings: {summary['total_listings']:,}")
    print(f"   Distinct Products: {summary['distinct_products']:,}")
    print(f"   Distinct Merchants: {summary['distinct_merchants']:,}")
    print()
    print(f"   Outlier Listings: {summary['outlier_listings']:,} ({summary['outlier_listings']/summary['total_listings']*100:.2f}%)")
    print(f"   Duplicate Candidates: {summary['duplicate_listings']:,} ({summary['duplicate_listings']/summary['total_listings']*100:.2f}%)")
    print(f"   Warning Listings: {summary['warning_listings']:,} ({summary['warning_listings']/summary['total_listings']*100:.2f}%)")
    print()
    print(f"💰 Price Statistics (IRR)")
    if summary.get("avg_price_excluding_outliers"):
        print(f"   Average Price (excl. outliers): {summary['avg_price_excluding_outliers']:,.0f}")
    if summary.get("median_price"):
        print(f"   Median Price: {summary['median_price']:,.0f}")
    if summary.get("q1_price") and summary.get("q3_price"):
        print(f"   Q1 (25th percentile): {summary['q1_price']:,.0f}")
        print(f"   Q3 (75th percentile): {summary['q3_price']:,.0f}")
    if summary.get("avg_price_including_outliers"):
        print(f"   Average Price (incl. outliers): {summary['avg_price_including_outliers']:,.0f}")
    if summary.get("max_price"):
        print(f"   Max Price: {summary['max_price']:,.0f}")
    print()

    print(f"🏪 Top 5 Sources by Listing Count")
    for i, src in enumerate(metrics["by_source"][:5], 1):
        outlier_pct = src['outlier_listings']/src['listing_count']*100 if src['listing_count'] > 0 else 0
        print(f"   {i}. {src['source_name']} ({src['source_code']})")
        print(f"      Listings: {src['listing_count']:,} | Products: {src['distinct_products']:,} | Merchants: {src['distinct_merchants']:,}")
        print(f"      Outliers: {src['outlier_listings']:,} ({outlier_pct:.1f}%) | Avg Price: {src['avg_price_excl_outliers']:,.0f} IRR")
    print()

    print(f"⚠️  Data Quality Issues")
    quality = metrics["quality_summary"]
    if "issues_by_severity" in quality:
        for sev in quality["issues_by_severity"]:
            print(f"   {sev['severity']}: {sev['issue_count']:,} issues")
    print()
    print(f"   Top 5 Rules by Issue Count:")
    for rule in quality.get("issues_by_rule", [])[:5]:
        print(f"   • {rule['rule_code']}: {rule['issue_count']:,} ({rule['severity']})")
    print()

    print(f"📈 Most Expensive Products (Top 10)")
    for i, prod in enumerate(metrics["top_products"][:10], 1):
        outlier_flag = " ⚠️ OUTLIER" if prod.get("is_outlier") else ""
        title = prod['product_title'][:70] + "..." if len(prod['product_title']) > 70 else prod['product_title']
        print(f"   {i}. {title}")
        print(f"      Price: {prod['price']:,.0f} IRR ({prod['source']}){outlier_flag}")
    print()

    print("=" * 80 + "\n")


if __name__ == "__main__":
    print("Calculating analytics metrics from database...")
    metrics = calculate_all_metrics()
    print_metric_summary()
    print(f"Metrics saved to: {METRICS_PATH}")