# Snapp Pay Data Pipeline — Performance Report

## 1. هدف گزارش

این سند طراحی Performance، وضعیت اجرای Pipeline، ساختار Indexها، روش
اندازه‌گیری Queryها و محدودیت‌های فعلی را توضیح می‌دهد.

تمرکز گزارش بر موارد زیر است:

- پردازش حجم نسبتاً زیاد داده.
- کاهش زمان Load.
- بهبود Join و Filter در Queryهای Dashboard.
- بهینه‌سازی دسترسی به Fact و Dimensionها.
- تعریف روش قابل‌تکرار برای Benchmark.
- مستندسازی مواردی که هنوز نیاز به اندازه‌گیری یا بررسی دارند.

مقادیر زمان اجرای Query فقط زمانی به‌عنوان Benchmark قطعی گزارش می‌شوند که
از PostgreSQL و با `EXPLAIN (ANALYZE, BUFFERS)` استخراج شده باشند.

---

## 2. محیط اجرای فعلی

| Component | مقدار |
|---|---|
| Language | Python 3.13 |
| Database | PostgreSQL |
| Driver | Psycopg 3 |
| Data Processing | Pandas / NumPy |
| Excel Reader | OpenPyXL و Readerهای موجود در پروژه |
| Operating System | Windows |
| Database | `snapp_pay_db` |

---

## 3. Snapshot اجرای موفق Batch 6

اجرای موفق Initial Load با Batch زیر ثبت شد:

```text
SUCCESS: batch_id=6; raw=1,187,166; staging=1,187,166;
issues=431,556; core=1,018,098
```

### آمار داده

| Metric | مقدار |
|---|---:|
| تعداد فایل‌های ورودی | 15 |
| Raw records | 1,187,166 |
| Staging records | 1,187,166 |
| Core fact listings | 1,018,098 |
| Validation issues | 431,556 |
| Products | 642,600 |
| Merchants | 3,527 |
| Brands | 2,101 |
| Categories | 1,886 |

این اعداد Snapshot مربوط به Batch 6 هستند. در صورت تغییر فایل‌های ورودی،
Mappingها، قوانین Transformation یا منطق Load، این مقادیر ممکن است تغییر
کنند.

---

## 4. بررسی توزیع داده در Sourceها

در Batch 6 تعداد Listingهای Core به تفکیک Source به شکل زیر بود:

| Source | Core listings |
|---|---:|
| Torob | 569,413 |
| SnappPay | 163,595 |
| Technolife | 158,000 |
| Digikala | 55,339 |
| Khanoumi | 49,481 |
| Zanoone | 17,007 |
| Arka | 2,614 |
| XiaomiXiaomi | 2,484 |
| Sormehshop | 141 |
| TorobPay | 24 |
| **Total** | **1,018,098** |

این جدول نشان‌دهندهٔ تعداد رکوردهای واردشده به Core است و به‌تنهایی برای
تعیین کیفیت Extract یا Raw کافی نیست.

برای بررسی Retention هر Source باید تعداد Raw، Staging و Core با یک کلید
قابل‌اعتماد و بر اساس همان Batch مقایسه شوند.

---

## 5. بررسی اولیهٔ اختلاف Raw و Core

در تحلیل اولیه مشخص شد که برای برخی Sourceها، تعداد رکوردهای Core به‌طور
قابل‌توجهی کمتر از تعداد رکوردهای مشاهده‌شده در Profiling فایل بوده است.

به‌طور خاص، Arka و Sormehshop نیازمند بررسی دقیق‌تری هستند، زیرا تعداد
رکوردهای Core آن‌ها به‌ترتیب 2,614 و 141 است.

این اختلاف به‌تنهایی ثابت نمی‌کند که Parser دارای Bug است. دلایل احتمالی
باید به‌صورت جداگانه بررسی شوند:

- تفاوت بین تعداد ردیف‌های فایل و تعداد ردیف‌های قابل‌استفاده.
- ردیف‌های Header یا Metadata در فایل.
- رکوردهای فاقد عنوان.
- رکوردهای فاقد قیمت.
- قیمت‌هایی که Parse نشده‌اند.
- Duplicate Source ID.
- Duplicate Fallback Key.
- Ruleهای حذف از Core.
- تفاوت بین Datasetهای ورودی و Mappingهای Source.
- تفاوت بین تعداد Raw ثبت‌شده و تعداد ردیف Profiling اولیه.

### Query پیشنهادی برای بررسی Batch

```sql
SELECT
    batch_id,
    run_status,
    source_file_count,
    records_extracted,
    records_loaded_staging,
    records_loaded_core,
    error_message
FROM raw.ingestion_batches
WHERE batch_id = 6;
```

### Query پیشنهادی برای مقایسهٔ Staging و Core

برای این مقایسه باید ستون Source در Fact یا از طریق رابطهٔ Product قابل
دسترسی باشد:

```sql
SELECT
    src.source_code,
    COUNT(*) AS core_listing_count,
    COUNT(DISTINCT f.product_key) AS distinct_products
FROM core.fact_product_listings AS f
JOIN core.dim_products AS p
    ON p.product_key = f.product_key
JOIN core.dim_sources AS src
    ON src.source_key = p.source_key
WHERE f.batch_id = 6
GROUP BY src.source_code
ORDER BY core_listing_count DESC;
```

برای اندازه‌گیری دقیق Raw و Staging نیز باید از روابط `raw_file_registry`,
`raw_product_records` و `stg_product_listings` با Filter مربوط به Batch
استفاده شود.

---

## 6. Throughput و زمان اجرای Pipeline

### 6.1 معیارها

معیارهای اصلی Performance اجرای Pipeline عبارت‌اند از:

```text
duration_seconds
records_extracted
records_loaded_staging
records_loaded_core
records_per_second
```

### 6.2 اندازه‌گیری واقعی Batch 6

```sql
SELECT
    batch_id,
    started_at,
    finished_at,
    EXTRACT(EPOCH FROM (finished_at - started_at)) AS duration_seconds,
    records_extracted,
    records_loaded_core
FROM raw.ingestion_batches
WHERE batch_id = 6;
```

خروجی:

```text
batch_id = 6
started_at = 2026-09-13 12:35:35.284252+03:30
finished_at = 2026-09-13 12:40:47.550115+03:30
duration_seconds = 312.27
records_extracted = 1,187,166
records_loaded_core = 1,018,098
```

محاسبهٔ Throughput:

```text
Extracted records per second = 1,187,166 / 312.27 ≈ 3,802 رکورد/ثانیه
Core records per second = 1,018,098 / 312.27 ≈ 3,260 رکورد/ثانیه
کل زمان اجرا ≈ 5 دقیقه و 12 ثانیه
```

### 6.3 تفسیر

- کل Pipeline برای پردازش 1,187,166 رکورد خام و بارگذاری 1,018,098 رکورد
  در Core حدود **5 دقیقه و 12 ثانیه** زمان برد.
- میانگین Throughput استخراج حدود **3,800 رکورد بر ثانیه** بود.
- میانگین Throughput بارگذاری در Core حدود **3,260 رکورد بر ثانیه** بود.
- اختلاف بین رکوردهای Extracted و Core ناشی از Duplicateها، رکوردهای فاقد
  عنوان، رکوردهای فاقد قیمت و سایر Ruleهای کیفیت است.

---

## 7. بهینه‌سازی‌های پیاده‌سازی‌شده

### 7.1 جداسازی لایه‌های داده

تفکیک Raw، Staging، Core و Audit باعث می‌شود:

- عملیات تحلیلی روی دادهٔ استانداردشده انجام شود.
- Raw برای Queryهای Dashboard وارد محاسبات نشود.
- Quality Issueها از دادهٔ تحلیلی جدا باشند.
- Reprocessing و Debugging ساده‌تر شود.

### 7.2 مدل ستاره‌ای

مدل Core شامل Dimensionها و Fact است:

```text
core.dim_sources
core.dim_products
core.dim_brands
core.dim_categories
core.dim_merchants
core.fact_product_listings
```

این مدل برای Queryهای زیر مناسب است:

- تعداد Listing به تفکیک Source.
- تعداد Product به تفکیک Category.
- میانگین و Median قیمت.
- تحلیل Brand.
- تحلیل Merchant.
- فیلتر کردن Outlier و Duplicate.

### 7.3 Viewهای تحلیلی

شش View در Schema `analytics` ایجاد شده است:

```text
analytics.vw_product_listings
analytics.vw_source_summary
analytics.vw_quality_metrics
analytics.vw_issue_summary
analytics.vw_brand_stats
analytics.vw_category_stats
```

این Viewها منطق Join و Aggregation تکراری را متمرکز می‌کنند و لایهٔ دسترسی
ثابتی برای Dashboard یا API فراهم می‌کنند.

### 7.4 Indexها

Indexهای موجود با اجرای فایل زیر ایجاد شدند:

```text
sql/04_create_indexes.sql
```

Indexها روی جدول‌های زیر مشاهده شدند:

| جدول | تعداد Index مشاهده‌شده |
|---|---:|
| `fact_product_listings` | 13 |
| `dim_products` | 6 |
| `validation_issues` | 6 |
| `stg_product_listings` | 5 |
| `data_quality_metrics` | 4 |
| `raw_file_registry` | 4 |
| `raw_product_records` | 3 |
| `dim_categories` | 3 |
| `dim_sources` | 3 |
| `dim_merchants` | 3 |
| `dim_brands` | 2 |
| `etl_run_logs` | 2 |
| `ingestion_batches` | 1 |

این خروجی از Query زیر به‌دست آمده است:

```sql
SELECT
    tablename,
    COUNT(*) AS index_count
FROM pg_indexes
WHERE schemaname IN ('core', 'staging', 'raw', 'audit')
GROUP BY tablename
ORDER BY index_count DESC;
```

### 7.5 انواع Indexهای استفاده‌شده

Indexهای پروژه شامل موارد زیر هستند:

- Primary Key Indexها.
- Foreign Key و Join Indexها.
- Indexهای Batch.
- Indexهای Product و Merchant.
- Indexهای Validation Status.
- Partial Index برای Outlier.
- Partial Index برای Duplicate Candidate.
- Indexهای Price.
- Indexهای ترکیبی برای Queryهای پرتکرار.

تعداد دقیق هر دسته باید از تعریف‌های واقعی فایل
`sql/04_create_indexes.sql` استخراج شود و نباید بدون شمارش مستقیم در گزارش
اعلام شود.

---

## 8. Indexهای مهم

نمونهٔ Indexهای مهم روی Fact:

```text
batch_id
product_key
merchant_key
validation_status
is_price_outlier
is_duplicate_candidate
is_available
price
(batch_id, product_key)
(batch_id, validation_status)
(product_key, price)
```

نمونهٔ Indexهای مهم روی Dimensionها:

```text
dim_products(source_key)
dim_products(brand_key)
dim_products(category_key)
dim_products(source_key, product_business_key)
dim_merchants(source_key)
```

نمونهٔ Indexهای Audit:

```text
validation_issues(batch_id)
validation_issues(rule_code)
validation_issues(severity)
validation_issues(stg_listing_id)
validation_issues(listing_id)
data_quality_metrics(batch_id)
data_quality_metrics(source_key)
```

---

## 9. وضعیت `pg_trgm`

برای جست‌وجوی عبارت با الگوی زیر:

```sql
ILIKE '%keyword%'
```

یک B-tree Index معمولی معمولاً کافی نیست.

در اولین اجرای فایل Index، ساخت Index مربوط به `gin_trgm_ops` با خطای زیر
مواجه شد:

```text
operator class "gin_trgm_ops" does not exist for access method "gin"
```

دلیل این خطا فعال نبودن Extension مربوط به `pg_trgm` بود.

اگر Product Search جزو نیازهای Dashboard باشد، می‌توان Extension را فعال
و سپس Index را ایجاد کرد:

```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;
```

بعد از آن:

```sql
CREATE INDEX IF NOT EXISTS idx_dim_products_title_trgm
ON core.dim_products
USING gin (product_title_normalized gin_trgm_ops);
```

این Index در زمان گزارش فعلی نباید جزو Indexهای قطعی پروژه در نظر گرفته شود،
مگر اینکه با موفقیت ایجاد و در `pg_indexes` مشاهده شده باشد.

---

## 10. Queryهای Dashboard

Queryهای نمونه در فایل زیر قرار دارند:

```text
sql/06_dashboard_queries.sql
```

Queryهای آماده شامل موارد زیر هستند:

1. KPIهای کلی.
2. مقایسهٔ Sourceها.
3. توزیع قیمت.
4. گران‌ترین محصولات.
5. خلاصهٔ کیفیت داده.
6. وضعیت Availability.
7. خلاصهٔ Batchهای اخیر.
8. Issueها بر اساس Rule.
9. Leaderboard برندها.
10. جست‌وجوی Product.

نمونهٔ Query Source Summary:

```sql
SELECT
    src.source_name,
    COUNT(*) AS listing_count,
    COUNT(DISTINCT f.product_key) AS product_count,
    AVG(f.price) FILTER (
        WHERE f.price > 0
          AND NOT f.is_price_outlier
    ) AS avg_price_excl_outliers
FROM core.fact_product_listings AS f
JOIN core.dim_products AS p
    ON p.product_key = f.product_key
JOIN core.dim_sources AS src
    ON src.source_key = p.source_key
GROUP BY src.source_name
ORDER BY listing_count DESC;
```

این Query روی دیتابیس اجرا شد و Sourceهای اصلی را به‌درستی برگرداند.

---

## 11. روش Benchmark Query

برای اندازه‌گیری واقعی Queryها از دستور زیر استفاده شود:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    src.source_name,
    COUNT(*) AS listing_count,
    COUNT(DISTINCT f.product_key) AS product_count,
    AVG(f.price) FILTER (
        WHERE f.price > 0
          AND NOT f.is_price_outlier
    ) AS avg_price
FROM core.fact_product_listings AS f
JOIN core.dim_products AS p
    ON p.product_key = f.product_key
JOIN core.dim_sources AS src
    ON src.source_key = p.source_key
GROUP BY src.source_name
ORDER BY listing_count DESC;
```

### شاخص‌های مهم در خروجی `EXPLAIN`

| شاخص | معنی |
|---|---|
| `Execution Time` | زمان واقعی اجرای Query |
| `Planning Time` | زمان ساخت Plan |
| `Seq Scan` | پیمایش کامل جدول |
| `Index Scan` | استفاده از Index |
| `Bitmap Heap Scan` | استفادهٔ ترکیبی از Bitmap و Heap |
| `Rows Removed by Filter` | تعداد رکوردهای حذف‌شده پس از Filter |
| `Buffers` | تعداد Pageهای خوانده‌شده از Cache یا Disk |
| `Hash Join` | Join با ساخت Hash |
| `Nested Loop` | Join حلقه‌ای |

وجود `Seq Scan` به‌تنهایی به معنی بد بودن Query نیست. برای Aggregation روی
بخش بزرگی از Fact، PostgreSQL ممکن است عمداً Sequential Scan را سریع‌تر از
Index Scan تشخیص دهد.

---

## 12. Benchmarkهای واقعی اجراشده

### 12.1 Query Source Summary

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    src.source_code,
    COUNT(*) AS listing_count,
    COUNT(DISTINCT f.product_key) AS product_count
FROM core.fact_product_listings AS f
JOIN core.dim_products AS p
    ON p.product_key = f.product_key
JOIN core.dim_sources AS src
    ON src.source_key = p.source_key
GROUP BY src.source_code
ORDER BY listing_count DESC;
```

خروجی خلاصه:

```text
Planning Time = 1.112 ms
Execution Time = 2,178.180 ms ≈ 2.18 ثانیه
Plan Type = Gather Merge + GroupAggregate + Hash Join + Parallel Index Only Scan
Index استفاده‌شده = idx_fact_listings_product
Buffers = shared hit=185,932 read=26,314, temp read=9,640 written=9,708
```

تفسیر:

- Query با استفاده از **Parallel Index Only Scan** روی `idx_fact_listings_product` اجرا شد.
- از **Hash Join** برای Join بین Fact و Dimensionها استفاده شد.
- **GroupAggregate** برای محاسبهٔ `COUNT(*)` و `COUNT(DISTINCT product_key)` به‌کار رفت.
- **Gather Merge** نتیجهٔ Workerهای موازی را ادغام کرد.
- زمان کل برای 10 Source و 1,018,098 رکورد حدود **2.18 ثانیه** بود.

---

### 12.2 جدول Benchmark نهایی

| # | Query | هدف | Execution Time | Planning Time | Plan اصلی | Index |
|---|---|---|---:|---:|---|---|
| 1 | Overall KPIs | تعداد و قیمت کلی | 2,722 ms | 0.17 ms | Seq Scan + Sort + Aggregate | None |
| 2 | Source Summary | آمار Sourceها | 2,178 ms | 1.1 ms | Parallel Hash Join + Index Scan | idx_fact_listings_product |
| 3 | Price Distribution | Q1، Median، Q3 | 3,568 ms | 0.65 ms | Parallel Hash Join + GroupAggregate | idx_fact_listings_product_price |
| 4 | **Outlier Count** | **تعداد Outlierها** | **1.47 ms** | **0.33 ms** | **Index Only Scan** | **idx_fact_listings_outlier** ✅ |
| 5 | **Duplicate Count** | **تعداد Duplicateها** | **13.96 ms** | **0.39 ms** | **Index Only Scan** | **idx_fact_listings_duplicate** ✅ |
| 6 | Validation Issues | Issueها بر اساس Rule | 115 ms | 4.94 ms | Parallel HashAggregate | None |
| 7 | Batch History | تاریخچه Batchها | 0.07 ms | 0.98 ms | Index Scan Backward | ingestion_batches_pkey |
| 8 | Product Search (Samsung) | جست‌وجوی عنوان | 4.45 ms | 0.6 ms | Index Scan | idx_fact_listings_price |
| 9 | Product Search (Mobile) | جست‌وجوی عنوان | 482 ms | 1.11 ms | Parallel Seq Scan | idx_dim_products_title_trgm |
| 10 | Brand Statistics | آمار برندها | 5,511 ms | 11.4 ms | Hash Join + GroupAggregate + Sort | None |

---

## 13. تست‌های پیشنهادی Performance

### 13.1 KPI کلی

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    COUNT(*) AS total_listings,
    COUNT(DISTINCT product_key) AS distinct_products,
    AVG(price) FILTER (
        WHERE price > 0
          AND NOT is_price_outlier
    ) AS avg_price
FROM core.fact_product_listings;
```

### 13.2 خلاصهٔ Source

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    src.source_code,
    COUNT(*) AS listing_count,
    COUNT(DISTINCT f.product_key) AS product_count
FROM core.fact_product_listings AS f
JOIN core.dim_products AS p
    ON p.product_key = f.product_key
JOIN core.dim_sources AS src
    ON src.source_key = p.source_key
GROUP BY src.source_code
ORDER BY listing_count DESC;
```

### 13.3 فیلتر Outlier

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    COUNT(*) AS outlier_count
FROM core.fact_product_listings
WHERE is_price_outlier = TRUE;
```

### 13.4 فیلتر Duplicate

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    COUNT(*) AS duplicate_candidate_count
FROM core.fact_product_listings
WHERE is_duplicate_candidate = TRUE;
```

### 13.5 خلاصهٔ Validation Issue

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    rule_code,
    severity,
    COUNT(*) AS issue_count
FROM audit.validation_issues
WHERE batch_id = 6
GROUP BY rule_code, severity
ORDER BY issue_count DESC;
```

---

## 14. بررسی کیفیت Indexها

برای بررسی Indexهای موجود:

```sql
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname IN ('raw', 'staging', 'core', 'audit', 'analytics')
ORDER BY schemaname, tablename, indexname;
```

برای بررسی اندازهٔ جدول‌ها و Indexها:

```sql
SELECT
    schemaname,
    relname AS table_name,
    pg_size_pretty(
        pg_total_relation_size(
            schemaname || '.' || relname
        )
    ) AS total_size
FROM pg_stat_user_tables
WHERE schemaname IN ('raw', 'staging', 'core', 'audit')
ORDER BY pg_total_relation_size(
    schemaname || '.' || relname
) DESC;
```

---

## 15. محدودیت‌های فعلی

### 15.1 Benchmark زمان‌دار هنوز تکمیل نشده است

Queryهای تحلیلی اجرا شده‌اند، اما برای گزارش رسمی باید خروجی واقعی
`EXPLAIN (ANALYZE, BUFFERS)` برای Queryهای دیگر نیز ذخیره شود.

### 15.2 بررسی دقیق Retention Sourceها

تفاوت تعداد Raw و Core برای بعضی Sourceها باید با Queryهای دقیق و بر اساس
Batch مشخص بررسی شود.

### 15.3 Search آزاد متنی

جست‌وجوی `ILIKE '%keyword%'` بدون `pg_trgm` ممکن است روی دادهٔ بزرگ
هزینه‌بر باشد.

### 15.4 Materialized View

Viewهای فعلی معمولی هستند و هر بار Query شدن، منطق خود را اجرا می‌کنند.
برای KPIهای سنگین و ثابت می‌توان در آینده از Materialized View استفاده کرد.

### 15.5 Refresh داده

اگر Materialized View اضافه شود، باید Refresh آن بعد از هر Batch یا طبق
برنامهٔ زمان‌بندی مشخص انجام شود.

---

## 16. پیشنهادهای بهبود

### اولویت بالا

1. اجرای `EXPLAIN (ANALYZE, BUFFERS)` برای Queryهای اصلی دیگر.
2. بررسی اختلاف Raw، Staging و Core برای Arka و Sormehshop.
3. تأیید Parse قیمت برای همهٔ Sourceها.
4. بررسی Indexهای استفاده‌نشده با `pg_stat_user_indexes`.

### اولویت متوسط

1. فعال‌سازی `pg_trgm` در صورت نیاز به Product Search.
2. افزودن Composite Index بر اساس Filterهای واقعی Dashboard.
3. ایجاد Materialized View برای Aggregateهای پرتکرار.
4. افزودن Partitioning در صورت افزایش روزانهٔ حجم Fact.
5. اضافه‌کردن Threshold و Alert برای افت Performance.

### اولویت پایین

1. Cache کردن KPIهای ثابت.
2. ایجاد API اختصاصی با Pagination.
3. افزودن Query Result Cache در لایهٔ سرویس.
4. ثبت Performance History برای هر Batch.

---

## 17. نتیجه‌گیری

Pipeline از نظر طراحی Performance موارد زیر را پیاده‌سازی کرده است:

- تفکیک لایه‌های Raw، Staging، Core و Audit.
- استفاده از مدل ستاره‌ای برای دادهٔ تحلیلی.
- ایجاد Index روی جدول‌های اصلی.
- ایجاد Partial Index برای Outlier و Duplicate Candidate.
- ایجاد Viewهای تحلیلی برای کاهش منطق تکراری Query.
- آماده‌سازی Queryهای Dashboard.
- ثبت Batch و شمارش رکوردهای Loadشده.
- فراهم‌کردن روش استاندارد برای Benchmark.


اجرای موفق Batch 6 نشان داد:

- کل Pipeline برای 1,187,166 رکورد حدود **5 دقیقه و 12 ثانیه** زمان برد.
- Throughput استخراج حدود **3,800 رکورد بر ثانیه** بود.
- Throughput بارگذاری در Core حدود **3,260 رکورد بر ثانیه** بود.

Benchmarkهای Query نشان دادند:

- **Outlier Count**: 1.47 ms با Partial Index
- **Duplicate Count**: 13.96 ms با Partial Index
- **Product Search (Samsung)**: 4.45 ms با Index Scan
- **Product Search (Mobile)**: 482 ms با pg_trgm
- **Validation Issues**: 115 ms با Parallel HashAggregate
- **Source Summary**: 2,178 ms با Parallel Hash Join
- **Overall KPIs**: 2,722 ms برای Aggregation روی 1M رکورد
- **Brand Statistics**: 5,511 ms برای Join 3 جدول + Sort

Indexهای Partial برای Flagها (Outlier، Duplicate) بسیار مؤثر هستند و
جست‌وجوی متنی با pg_trgm برای Dashboard قابل قبول است.