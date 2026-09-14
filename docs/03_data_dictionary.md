# Snapp Pay Data Pipeline — Data Dictionary

## 1. هدف سند

این سند ساختار دادهٔ پایگاه دادهٔ Snapp Pay Data Pipeline را توضیح می‌دهد.

برای هر Schema و Table، موارد زیر مشخص شده است:

- هدف جدول.
- نقش جدول در پایپلاین.
- ستون‌های اصلی.
- نوع دادهٔ منطقی.
- رابطه با سایر جداول.
- قواعد معنایی مهم.
- نمونهٔ استفاده در لایهٔ تحلیلی.

پایگاه داده از پنج Schema منطقی تشکیل شده است:

```text
raw
staging
core
audit
analytics
```

چهار Schema اول شامل داده‌ها و اطلاعات اجرایی هستند و Schema پنجم شامل
Viewهای مصرفی برای Queryهای تحلیلی و Dashboard است.

---

## 2. مدل کلی داده

```text
raw.ingestion_batches
        |
        +── raw.raw_file_registry
                |
                +── raw.raw_product_records
                        |
                        +── staging.stg_product_listings
                                |
                                +── audit.validation_issues
                                |
                                +── core.dim_products
                                |       |
                                |       +── core.dim_brands
                                |       +── core.dim_categories
                                |       +── core.dim_sources
                                |
                                +── core.dim_merchants
                                |
                                +── core.fact_product_listings
```

### نقش لایه‌ها

| Schema | نقش |
|---|---|
| `raw` | ثبت Batch، فایل ورودی و Payload خام |
| `staging` | دادهٔ استانداردشده و تبدیل‌شده |
| `core` | مدل تحلیلی شامل Dimension و Fact |
| `audit` | ثبت Issue، Metric و Log |
| `analytics` | Viewهای آماده برای مصرف تحلیلی |

---

# 3. Schema: raw

## 3.1 جدول `raw.ingestion_batches`

### هدف

این جدول هر اجرای پایپلاین را به‌عنوان یک Batch ثبت می‌کند.

هر بار اجرای Loader باید یک رکورد Batch داشته باشد تا وضعیت، تعداد
رکوردها، زمان اجرا و خطاهای احتمالی قابل پیگیری باشند.

### کلید اصلی

```text
batch_id
```

### ستون‌ها

| ستون | نوع منطقی | Nullable | توضیح |
|---|---|---:|---|
| `batch_id` | Integer / Serial | خیر | شناسهٔ یکتای Batch |
| `pipeline_name` | Text / Varchar | خیر | نام پایپلاین |
| `pipeline_version` | Text / Varchar | خیر | نسخهٔ Pipeline |
| `run_status` | Text / Varchar | خیر | وضعیت اجرا |
| `started_at` | Timestamp with timezone | خیر | زمان شروع |
| `finished_at` | Timestamp with timezone | بله | زمان پایان |
| `source_file_count` | Integer | بله | تعداد فایل‌های ورودی |
| `records_extracted` | Integer / Bigint | بله | تعداد رکوردهای استخراج‌شده |
| `records_valid` | Integer / Bigint | بله | تعداد رکوردهای معتبر، در صورت ثبت |
| `records_quarantined` | Integer / Bigint | بله | تعداد رکوردهای کنارگذاشته‌شده، در صورت ثبت |
| `records_loaded_staging` | Integer / Bigint | بله | تعداد رکوردهای Staging |
| `records_loaded_core` | Integer / Bigint | بله | تعداد رکوردهای Core |
| `error_message` | Text | بله | توضیح خطا در صورت شکست |

### مقادیر متداول `run_status`

```text
RUNNING
SUCCESS
FAILED
PARTIAL
```

### روابط

```text
raw.ingestion_batches.batch_id
    ├── raw.raw_file_registry.batch_id
    ├── core.fact_product_listings.batch_id
    ├── audit.validation_issues.batch_id
    ├── audit.data_quality_metrics.batch_id
    └── audit.etl_run_logs.batch_id
```

### نمونهٔ Batch موفق

```text
batch_id = 6
run_status = SUCCESS
source_file_count = 15
records_extracted = 1,187,166
records_loaded_staging = 1,187,166
records_loaded_core = 1,018,098
```

---

## 3.2 جدول `raw.raw_file_registry`

### هدف

این جدول Metadata مربوط به هر فایل ورودی را در هر Batch نگه‌داری می‌کند.

### کلید اصلی

```text
file_id
```

### ستون‌ها

| ستون | نوع منطقی | Nullable | توضیح |
|---|---|---:|---|
| `file_id` | Integer / Serial | خیر | شناسهٔ یکتای فایل |
| `batch_id` | Integer | خیر | Batch مربوط به فایل |
| `original_file_name` | Text / Varchar | خیر | نام اصلی فایل |
| `file_path` | Text | بله | مسیر فایل |
| `file_size_bytes` | Bigint | بله | اندازهٔ فایل بر حسب Byte |
| `file_hash_sha256` | Char(64) / Text | بله | Hash فایل |
| `file_format` | Text / Varchar | خیر | مانند CSV یا XLSX |
| `file_status` | Text / Varchar | خیر | وضعیت پردازش فایل |
| `records_extracted` | Integer / Bigint | بله | تعداد رکوردهای استخراج‌شده از فایل |
| `processed_at` | Timestamp with timezone | بله | زمان پردازش |
| `error_message` | Text | بله | خطای پردازش فایل |

### مقادیر متداول `file_status`

```text
PENDING
PROCESSED
FAILED
SKIPPED
```

### رابطه

```text
raw.raw_file_registry.batch_id
    -> raw.ingestion_batches.batch_id
```

---

## 3.3 جدول `raw.raw_product_records`

### هدف

این جدول یک نسخهٔ خام و غیرقابل‌تغییر از هر رکورد منبع نگه‌داری می‌کند.

### کلید اصلی

```text
raw_record_id
```

### ستون‌ها

| ستون | نوع منطقی | Nullable | توضیح |
|---|---|---:|---|
| `raw_record_id` | Integer / Serial | خیر | شناسهٔ رکورد خام |
| `file_id` | Integer | خیر | فایل منبع |
| `source_row_number` | Integer | بله | شمارهٔ ردیف در فایل |
| `raw_payload` | JSONB | خیر | رکورد اصلی به فرمت JSONB |
| `extracted_at` | Timestamp with timezone | خیر | زمان Extract |

### ویژگی مهم

`raw_payload` باید دادهٔ اصلی را تا حد امکان بدون تغییر نگه‌داری کند. این
ستون برای موارد زیر استفاده می‌شود:

- Audit.
- بررسی خطاهای Transformation.
- Reprocessing.
- مقایسهٔ مقدار خام و مقدار استانداردشده.
- بررسی اختلاف بین فایل و دیتابیس.

### رابطه

```text
raw.raw_product_records.file_id
    -> raw.raw_file_registry.file_id
```

---

# 4. Schema: staging

## 4.1 جدول `staging.stg_product_listings`

### هدف

این جدول دادهٔ خام را پس از Mapping، Cleaning و Transformation به یک
ساختار استاندارد تبدیل می‌کند.

Staging هنوز لایهٔ نهایی تحلیلی نیست و ممکن است شامل رکوردهای تکراری،
رکوردهای ناقص یا رکوردهای دارای Warning باشد.

### کلید اصلی

```text
stg_listing_id
```

### ستون‌ها

| ستون | نوع منطقی | Nullable | توضیح |
|---|---|---:|---|
| `stg_listing_id` | Integer / Serial | خیر | شناسهٔ رکورد Staging |
| `raw_record_id` | Integer | خیر | رکورد خام مرتبط |
| `source` | Text / Varchar | خیر | کد Source |
| `dataset` | Text / Varchar | بله | نام Dataset یا فایل |
| `source_id` | Text / Varchar | بله | شناسهٔ محصول یا Listing در Source |
| `product_title` | Text | بله | عنوان پاک‌سازی‌شده |
| `product_title_normalized` | Text | بله | عنوان نرمال‌شده برای Matching |
| `brand_raw` | Text | بله | مقدار خام یا استاندارد اولیهٔ Brand |
| `category_raw` | Text | بله | مقدار خام یا استاندارد اولیهٔ Category |
| `merchant_name_raw` | Text | بله | مقدار Merchant در Source |
| `price` | Numeric(30,2) | بله | قیمت استانداردشده |
| `old_price` | Numeric(30,2) | بله | قیمت قبلی یا مرجع |
| `cash_back_percent` | Numeric(5,2) | بله | درصد Cashback |
| `discount_percent` | Numeric(5,2) | بله | درصد تخفیف |
| `availability_raw` | Text | بله | مقدار خام Availability |
| `is_available` | Boolean | بله | مقدار استاندارد Availability |
| `product_url` | Text | بله | URL محصول |
| `image_url` | Text | بله | URL تصویر |
| `search_keyword` | Text | بله | کلیدواژهٔ جست‌وجو |
| `source_price_unit` | Text / Varchar | بله | واحد قیمت منبع |
| `currency_code` | Char(3) | خیر | کد ارز خروجی؛ در Batch 6 برابر `IRR` |
| `transform_status` | Text / Varchar | خیر | وضعیت Transformation |
| `transform_notes` | Text | بله | توضیح تبدیل یا خطا |

### مقادیر متداول `transform_status`

```text
SUCCESS
WARNING
ERROR
```

### قواعد مهم

- قیمت‌ها پس از استانداردسازی در Contract خروجی ذخیره می‌شوند.
- در اجرای موفق Batch 6، `currency_code` برابر `IRR` بود.
- مقدار خام Availability در `availability_raw` حفظ می‌شود.
- مقدار Boolean استاندارد در `is_available` قرار می‌گیرد.
- عنوان نمایشی و عنوان نرمال‌شده در دو ستون جدا نگه‌داری می‌شوند.
- Staging برای Traceability به Raw از طریق `raw_record_id` متصل است.

### رابطه

```text
staging.stg_product_listings.raw_record_id
    -> raw.raw_product_records.raw_record_id
```

---

# 5. Schema: core

Core از یک مدل ستاره‌ای تشکیل شده است:

```text
Dimensions
    |
    v
core.fact_product_listings
```

## 5.1 جدول `core.dim_sources`

### هدف

Master Data مربوط به منابع ورودی.

### کلید اصلی

```text
source_key
```

### ستون‌ها

| ستون | نوع منطقی | Nullable | توضیح |
|---|---|---:|---|
| `source_key` | Integer / Serial | خیر | کلید داخلی Source |
| `source_code` | Text / Varchar | خیر | کد یکتا مانند `torob` |
| `source_name` | Text / Varchar | خیر | نام نمایشی مانند `Torob` |
| `source_type` | Text / Varchar | بله | نوع Source |
| `source_url` | Text | بله | URL منبع |
| `is_active` | Boolean | خیر | فعال بودن Source |
| `created_at` | Timestamp with timezone | خیر | زمان ایجاد |
| `updated_at` | Timestamp with timezone | بله | زمان آخرین تغییر |

### نمونهٔ `source_code`

```text
arka
digikala
khanoumi
snapp_pay
sormehshop
technolife
torob
torob_pay
xiaomixiaomi
zanoone
```

### انواع Source

| نوع | توضیح |
|---|---|
| `DIRECT` | فروشگاه یا Retailer مستقیم |
| `MARKETPLACE` | Marketplace دارای فروشندگان |
| `PRICE_COMPARISON` | منبع مقایسهٔ قیمت |

---

## 5.2 جدول `core.dim_products`

### هدف

نگهداری هویت و مشخصات سطح Product.

هر رکورد این جدول نمایندهٔ یک Product در یک Source است.

### کلید اصلی

```text
product_key
```

### ستون‌ها

| ستون | نوع منطقی | Nullable | توضیح |
|---|---|---:|---|
| `product_key` | Integer / Serial | خیر | کلید داخلی Product |
| `source_key` | Integer | خیر | Source محصول |
| `source_product_id` | Text / Varchar | بله | شناسهٔ محصول در Source |
| `product_business_key` | Text / Varchar | خیر | کلید کسب‌وکاری Product |
| `product_title` | Text | خیر | عنوان محصول |
| `product_title_normalized` | Text | خیر | عنوان نرمال‌شده |
| `brand_key` | Integer | بله | Brand مرتبط |
| `category_key` | Integer | بله | Category مرتبط |
| `is_active` | Boolean | خیر | فعال بودن Product |
| `created_at` | Timestamp with timezone | خیر | زمان ایجاد |
| `updated_at` | Timestamp with timezone | بله | زمان آخرین تغییر |

### Business Key

منطق اصلی Business Key:

```text
اگر source_id وجود داشته باشد:
    ID|<source_id>

در غیر این صورت:
    TITLE|<product_title_normalized>
```

### روابط

```text
core.dim_products.source_key
    -> core.dim_sources.source_key

core.dim_products.brand_key
    -> core.dim_brands.brand_key

core.dim_products.category_key
    -> core.dim_categories.category_key
```

---

## 5.3 جدول `core.dim_brands`

### هدف

نگهداری برندهای نرمال‌شده برای تحلیل و گروه‌بندی.

### کلید اصلی

```text
brand_key
```

### ستون‌ها

| ستون | نوع منطقی | Nullable | توضیح |
|---|---|---:|---|
| `brand_key` | Integer / Serial | خیر | کلید داخلی Brand |
| `brand_name` | Text / Varchar | خیر | نام نمایشی Brand |
| `brand_name_normalized` | Text / Varchar | خیر | نام نرمال‌شده برای Match |
| `is_active` | Boolean | خیر | فعال بودن Brand |
| `created_at` | Timestamp with timezone | خیر | زمان ایجاد |
| `updated_at` | Timestamp with timezone | بله | زمان تغییر |

### رابطه

```text
core.dim_brands.brand_key
    <- core.dim_products.brand_key
```

---

## 5.4 جدول `core.dim_categories`

### هدف

نگهداری دسته‌بندی‌های محصول و رابطهٔ احتمالی Parent/Child.

### کلید اصلی

```text
category_key
```

### ستون‌ها

| ستون | نوع منطقی | Nullable | توضیح |
|---|---|---:|---|
| `category_key` | Integer / Serial | خیر | کلید داخلی Category |
| `category_name` | Text / Varchar | خیر | نام نمایشی Category |
| `category_name_normalized` | Text / Varchar | خیر | نام نرمال‌شده |
| `category_level` | Integer | بله | سطح سلسله‌مراتب |
| `parent_category_key` | Integer | بله | Category والد |
| `is_active` | Boolean | خیر | فعال بودن Category |
| `created_at` | Timestamp with timezone | خیر | زمان ایجاد |
| `updated_at` | Timestamp with timezone | بله | زمان تغییر |

### رابطهٔ خودارجاع

```text
core.dim_categories.parent_category_key
    -> core.dim_categories.category_key
```

### رابطه

```text
core.dim_categories.category_key
    <- core.dim_products.category_key
```

---

## 5.5 جدول `core.dim_merchants`

### هدف

نگهداری هویت فروشندگان و Merchantهای قابل شناسایی.

### کلید اصلی

```text
merchant_key
```

### ستون‌ها

| ستون | نوع منطقی | Nullable | توضیح |
|---|---|---:|---|
| `merchant_key` | Integer / Serial | خیر | کلید داخلی Merchant |
| `source_key` | Integer | خیر | Source فروشنده |
| `merchant_name` | Text / Varchar | خیر | نام نمایشی فروشنده |
| `merchant_name_normalized` | Text / Varchar | خیر | نام نرمال‌شده |
| `merchant_url` | Text | بله | URL فروشنده |
| `is_active` | Boolean | خیر | فعال بودن Merchant |
| `created_at` | Timestamp with timezone | خیر | زمان ایجاد |
| `updated_at` | Timestamp with timezone | بله | زمان تغییر |

### روابط

```text
core.dim_merchants.source_key
    -> core.dim_sources.source_key

core.dim_merchants.merchant_key
    <- core.fact_product_listings.merchant_key
```

### Nullable بودن Merchant

ستون `merchant_key` در Fact قابل `NULL` است.

این اتفاق برای منابعی طبیعی است که Seller Identity ارائه نمی‌کنند؛ برای
مثال:

- بعضی Price Comparison Sourceها فقط عنوان و قیمت دارند.
- بعضی فایل‌ها Merchant را ثبت نکرده‌اند.
- بعضی Sourceها Merchant را فقط در بخشی از داده ارائه می‌کنند.

قرار دادن Merchant ساختگی برای این رکوردها از نظر کیفیت داده صحیح نیست.

---

## 5.6 جدول `core.fact_product_listings`

### هدف

این جدول Fact اصلی پروژه است و هر رکورد آن یک مشاهدهٔ محصول یا قیمت را
نمایندگی می‌کند.

### کلید اصلی

```text
listing_id
```

### ستون‌ها

| ستون | نوع منطقی | Nullable | توضیح |
|---|---|---:|---|
| `listing_id` | Integer / Serial | خیر | شناسهٔ Listing |
| `batch_id` | Integer | خیر | Batch ایجادکننده |
| `product_key` | Integer | خیر | Product مرتبط |
| `merchant_key` | Integer | بله | Merchant مرتبط |
| `source_listing_id` | Text / Varchar | بله | شناسهٔ Listing در Source |
| `price` | Numeric(30,2) | بله | قیمت استاندارد |
| `old_price` | Numeric(30,2) | بله | قیمت قبلی |
| `cash_back_percent` | Numeric(5,2) | بله | درصد Cashback |
| `discount_percent` | Numeric(5,2) | بله | درصد تخفیف |
| `is_available` | Boolean | بله | وضعیت موجودی |
| `validation_status` | Text / Varchar | خیر | وضعیت Validation |
| `is_duplicate_candidate` | Boolean | خیر | Flag Duplicate |
| `is_price_outlier` | Boolean | خیر | Flag Outlier |
| `currency_code` | Char(3) | خیر | کد ارز |
| `observed_at` | Timestamp with timezone | خیر | زمان مشاهدهٔ داده |
| `loaded_at` | Timestamp with timezone | خیر | زمان Load به Core |

### مقادیر `validation_status`

```text
VALID
VALID_WITH_WARNINGS
INVALID
```

### Flagهای کیفیت

| ستون | معنی |
|---|---|
| `is_duplicate_candidate = TRUE` | رکورد در Duplicate Detection مشکوک یا تکراری تشخیص داده شده |
| `is_price_outlier = TRUE` | قیمت از محدودهٔ آماری مورد انتظار خارج است |

### روابط

```text
core.fact_product_listings.batch_id
    -> raw.ingestion_batches.batch_id

core.fact_product_listings.product_key
    -> core.dim_products.product_key

core.fact_product_listings.merchant_key
    -> core.dim_merchants.merchant_key
```

---

# 6. Schema: audit

## 6.1 جدول `audit.validation_issues`

### هدف

ثبت جزئیات تمام مشکلات کیفیت داده که در Validation، Duplicate Detection،
Outlier Detection یا پردازش فایل شناسایی می‌شوند.

### کلید اصلی

```text
issue_id
```

### ستون‌ها

| ستون | نوع منطقی | Nullable | توضیح |
|---|---|---:|---|
| `issue_id` | Integer / Serial | خیر | شناسهٔ Issue |
| `batch_id` | Integer | خیر | Batch ایجادکنندهٔ Issue |
| `raw_record_id` | Integer | بله | رکورد خام مرتبط |
| `stg_listing_id` | Integer | بله | رکورد Staging مرتبط |
| `listing_id` | Integer | بله | رکورد Core مرتبط |
| `rule_code` | Text / Varchar | خیر | کد Rule |
| `severity` | Text / Varchar | خیر | `ERROR`, `WARNING`, `INFO` |
| `field_name` | Text / Varchar | بله | فیلد مشکل‌دار |
| `field_value` | Text | بله | مقدار مشکل‌دار |
| `action_taken` | Text / Varchar | بله | اقدام انجام‌شده |
| `message` | Text | بله | توضیح Issue |
| `detected_at` | Timestamp with timezone | خیر | زمان تشخیص |

### Ruleهای ثبت‌شده در Batch 6

| Rule | Severity | تعداد |
|---|---|---:|
| `DUPLICATE_SOURCE_ID` | `WARNING` | 198,922 |
| `DUPLICATE_FALLBACK_KEY` | `WARNING` | 165,953 |
| `ZERO_PRICE` | `WARNING` | 38,584 |
| `MISSING_PRICE` | `WARNING` | 16,174 |
| `PRICE_OUTLIER` | `WARNING` | 11,492 |
| `OLD_PRICE_LT_PRICE` | `WARNING` | 428 |
| `INVALID_AVAILABILITY_COLUMN` | `WARNING` | 1 |
| `REQ_TITLE` | `ERROR` | 1 |
| `FILE_EXTENSION_CONTENT_MISMATCH` | `WARNING` | 1 |

مجموع:

```text
431,556 issues
```

---

## 6.2 جدول `audit.data_quality_metrics`

### هدف

نگهداری Metricهای تجمیعی Data Quality در سطح Batch و Source.

### دانه‌بندی

```text
یک رکورد برای هر ترکیب Batch و Source
```

### ستون‌ها

| ستون | نوع منطقی | Nullable | توضیح |
|---|---|---:|---|
| `metric_id` | Integer / Serial | خیر | شناسهٔ Metric |
| `batch_id` | Integer | خیر | Batch مربوط |
| `source_key` | Integer | خیر | Source مربوط |
| `total_records` | Integer / Bigint | خیر | کل رکوردهای Source |
| `records_with_title` | Integer / Bigint | خیر | رکوردهای دارای عنوان |
| `records_with_positive_price` | Integer / Bigint | خیر | رکوردهای دارای قیمت مثبت |
| `records_with_zero_price` | Integer / Bigint | خیر | رکوردهای دارای قیمت صفر |
| `records_with_null_price` | Integer / Bigint | خیر | رکوردهای فاقد قیمت |
| `records_with_brand` | Integer / Bigint | خیر | رکوردهای دارای Brand |
| `records_with_category` | Integer / Bigint | خیر | رکوردهای دارای Category |
| `records_available` | Integer / Bigint | خیر | رکوردهای موجود |
| `records_unavailable` | Integer / Bigint | خیر | رکوردهای ناموجود |
| `records_availability_unknown` | Integer / Bigint | خیر | رکوردهای دارای Availability ناشناخته |
| `duplicate_candidate_count` | Integer / Bigint | خیر | تعداد Duplicate Candidate |
| `price_outlier_count` | Integer / Bigint | خیر | تعداد Outlier |
| `error_count` | Integer / Bigint | خیر | تعداد Issueهای Error |
| `warning_count` | Integer / Bigint | خیر | تعداد Issueهای Warning |
| `info_count` | Integer / Bigint | خیر | تعداد Issueهای Info |
| `calculated_at` | Timestamp with timezone | خیر | زمان محاسبهٔ Metric |

### رابطه‌ها

```text
audit.data_quality_metrics.batch_id
    -> raw.ingestion_batches.batch_id

audit.data_quality_metrics.source_key
    -> core.dim_sources.source_key
```

---

## 6.3 جدول `audit.etl_run_logs`

### هدف

ثبت مراحل اجرای ETL، وضعیت هر مرحله، تعداد رکوردهای پردازش‌شده و خطاهای
اجرایی.

### نکته

نام و مجموعهٔ دقیق ستون‌های این جدول باید با DDL موجود در فایل زیر یکسان
باشد:

```text
sql/02_create_tables.sql
```

در مستندات، فقط ستون‌هایی باید به‌عنوان قطعی معرفی شوند که در DDL نهایی
پروژه وجود دارند.

ساختار منطقی مورد انتظار:

| مفهوم | توضیح |
|---|---|
| شناسهٔ Log | شناسهٔ یکتای Log |
| Batch | Batch مرتبط |
| Component یا Step | مرحلهٔ Extract، Transform، Validation یا Load |
| سطح Log | INFO، WARNING یا ERROR |
| وضعیت | SUCCESS، WARNING یا FAILED |
| پیام | متن Log |
| جزئیات | اطلاعات تکمیلی، در صورت وجود |
| زمان ثبت | زمان ایجاد Log |

برای جلوگیری از ناهماهنگی، Data Dictionary باید پس از نهایی شدن DDL این
جدول به‌روزرسانی شود.

---

# 7. Schema: analytics

Schema `analytics` شامل Viewهای مورد استفادهٔ Dashboard و API است.

Viewها دادهٔ چند جدول Core و Audit را در یک لایهٔ خواندنی و قابل‌مصرف
ارائه می‌کنند.

## 7.1 `analytics.vw_product_listings`

### هدف

ارائهٔ Listingهای Fact به‌همراه نام و ویژگی‌های Dimensionها.

### داده‌های اصلی

این View شامل ترکیبی از موارد زیر است:

- ستون‌های Listing از `core.fact_product_listings`.
- عنوان و شناسهٔ Product از `core.dim_products`.
- اطلاعات Source از `core.dim_sources`.
- اطلاعات Brand از `core.dim_brands`.
- اطلاعات Category از `core.dim_categories`.
- اطلاعات Merchant از `core.dim_merchants`.

### نمونهٔ ستون‌ها

| ستون | منبع |
|---|---|
| `listing_id` | Fact |
| `batch_id` | Fact |
| `product_key` | Fact |
| `merchant_key` | Fact |
| `source_listing_id` | Fact |
| `price` | Fact |
| `old_price` | Fact |
| `cash_back_percent` | Fact |
| `discount_percent` | Fact |
| `is_available` | Fact |
| `validation_status` | Fact |
| `is_duplicate_candidate` | Fact |
| `is_price_outlier` | Fact |
| `currency_code` | Fact |
| `product_title` | Product Dimension |
| `product_title_normalized` | Product Dimension |
| `source_product_id` | Product Dimension |
| `source_code` | Source Dimension |
| `source_name` | Source Dimension |
| `source_type` | Source Dimension |
| `brand_name` | Brand Dimension |
| `category_name` | Category Dimension |
| `category_level` | Category Dimension |
| `merchant_name` | Merchant Dimension |
| `merchant_url` | Merchant Dimension |

### نمونهٔ Query

```sql
SELECT
    source_code,
    source_name,
    product_title,
    price,
    is_available,
    validation_status,
    is_price_outlier
FROM analytics.vw_product_listings
WHERE price > 0
ORDER BY price DESC
LIMIT 100;
```

---

## 7.2 `analytics.vw_source_summary`

### هدف

ارائهٔ KPIهای تجمیعی برای هر Source.

### Metricهای اصلی

- تعداد کل Listing.
- تعداد Product یکتا.
- تعداد Merchant یکتا.
- تعداد Listing موجود.
- تعداد Listing ناموجود.
- تعداد Availability ناشناخته.
- تعداد Outlier.
- تعداد Duplicate Candidate.
- تعداد Listing معتبر.
- تعداد Listing دارای Warning.
- میانگین قیمت بدون Outlier.
- Median قیمت.
- حداقل و حداکثر قیمت.
- آخرین زمان Load.

### نمونهٔ Query

```sql
SELECT
    source_code,
    source_name,
    total_listings,
    distinct_products,
    distinct_merchants,
    avg_price_excl_outliers,
    median_price
FROM analytics.vw_source_summary
ORDER BY total_listings DESC;
```

---

## 7.3 `analytics.vw_quality_metrics`

### هدف

ارائهٔ Metricهای کیفیت به‌صورت آماده برای Monitoring.

### Metricهای مشتق‌شده

- درصد رکوردهای دارای عنوان.
- درصد رکوردهای دارای قیمت مثبت.
- درصد رکوردهای Duplicate.
- درصد رکوردهای Outlier.
- درصد Error.
- درصد Warning.

### نمونهٔ Query

```sql
SELECT
    source_code,
    source_name,
    total_records,
    pct_with_title,
    pct_with_positive_price,
    pct_duplicates,
    pct_outliers,
    pct_errors,
    pct_warnings
FROM analytics.vw_quality_metrics
ORDER BY total_records DESC;
```

---

## 7.4 `analytics.vw_issue_summary`

### هدف

تجمیع Issueها بر اساس Rule و Severity.

### Metricهای اصلی

- `rule_code`
- `severity`
- `action_taken`
- `field_name`
- تعداد Issue
- تعداد Raw Recordهای تحت‌تأثیر
- تعداد Staging Recordهای تحت‌تأثیر
- تعداد Core Listingهای تحت‌تأثیر

### نمونهٔ Query

```sql
SELECT
    rule_code,
    severity,
    issue_count,
    affected_records,
    affected_staging_records,
    affected_core_listings
FROM analytics.vw_issue_summary
ORDER BY issue_count DESC;
```

---

## 7.5 `analytics.vw_brand_stats`

### هدف

ارائهٔ آمار Listing و قیمت به تفکیک Brand.

### Metricهای اصلی

- تعداد Listing.
- تعداد Product یکتا.
- تعداد Source.
- میانگین قیمت بدون Outlier.
- Median قیمت.
- حداقل قیمت.
- حداکثر قیمت.

### نمونهٔ Query

```sql
SELECT
    brand_name,
    total_listings,
    distinct_products,
    sources_count,
    avg_price_excl_outliers,
    median_price
FROM analytics.vw_brand_stats
ORDER BY total_listings DESC
LIMIT 50;
```

---

## 7.6 `analytics.vw_category_stats`

### هدف

ارائهٔ آمار Listing و قیمت به تفکیک Category.

### Metricهای اصلی

- تعداد Listing.
- تعداد Product یکتا.
- سطح Category.
- میانگین قیمت بدون Outlier.
- Median قیمت.

### نمونهٔ Query

```sql
SELECT
    category_name,
    category_level,
    total_listings,
    distinct_products,
    avg_price_excl_outliers,
    median_price
FROM analytics.vw_category_stats
ORDER BY total_listings DESC
LIMIT 50;
```

---

# 8. آمار Batch موفق

اطلاعات ثبت‌شده برای Batch 6:

| موجودیت | تعداد |
|---|---:|
| Source files | 15 |
| Raw records | 1,187,166 |
| Staging records | 1,187,166 |
| Core fact listings | 1,018,098 |
| Products | 642,600 |
| Merchants | 3,527 |
| Brands | 2,101 |
| Categories | 1,886 |
| Validation issues | 431,556 |

این اعداد مربوط به اجرای موفق Batch 6 هستند و ممکن است در اجرای بعدی با
تغییر فایل‌ها یا منطق Transformation تغییر کنند.

---

# 9. روابط اصلی

## 9.1 Raw

```text
raw.ingestion_batches
    1 ─── N raw.raw_file_registry
    1 ─── N core.fact_product_listings
    1 ─── N audit.validation_issues
    1 ─── N audit.data_quality_metrics
```

```text
raw.raw_file_registry
    1 ─── N raw.raw_product_records
```

## 9.2 Raw به Staging

```text
raw.raw_product_records
    1 ─── N staging.stg_product_listings
```

در حالت معمول هر Staging Record به یک Raw Record ارجاع می‌دهد.

## 9.3 Core

```text
core.dim_sources
    1 ─── N core.dim_products

core.dim_sources
    1 ─── N core.dim_merchants

core.dim_products
    1 ─── N core.fact_product_listings

core.dim_merchants
    1 ─── N core.fact_product_listings

core.dim_brands
    1 ─── N core.dim_products

core.dim_categories
    1 ─── N core.dim_products
```

---

# 10. Naming Conventions

## 10.1 Schema

نام Schemaها کوتاه و نقش‌محور هستند:

```text
raw
staging
core
audit
analytics
```

## 10.2 Table

نام جدول‌ها با `snake_case` و همراه با Prefix لایه انتخاب شده‌اند:

```text
raw_product_records
stg_product_listings
dim_products
fact_product_listings
validation_issues
```

## 10.3 کلید اصلی

برای Dimensionها معمولاً از الگوی زیر استفاده می‌شود:

```text
<entity>_key
```

نمونه:

```text
product_key
brand_key
category_key
merchant_key
source_key
```

برای جدول‌های عملیاتی یا رکوردی:

```text
<table_or_entity>_id
```

نمونه:

```text
batch_id
file_id
raw_record_id
stg_listing_id
listing_id
issue_id
```

## 10.4 کلید خارجی

نام کلید خارجی مطابق موجودیت مرجع انتخاب می‌شود:

```text
source_key
product_key
merchant_key
batch_id
raw_record_id
```

## 10.5 ستون‌های Boolean

ستون‌های Boolean با یکی از Prefixهای زیر شروع می‌شوند:

```text
is_
has_
```

نمونه:

```text
is_active
is_available
is_duplicate_candidate
is_price_outlier
```

## 10.6 ستون‌های Timestamp

نام ستون‌های زمانی معمولاً با `_at` پایان می‌یابد:

```text
created_at
updated_at
started_at
finished_at
loaded_at
observed_at
calculated_at
```

---

# 11. انواع دادهٔ مهم

| نوع | کاربرد |
|---|---|
| `INTEGER` | کلیدها و شمارنده‌های معمول |
| `BIGINT` | تعداد رکوردها یا اندازه‌های بزرگ |
| `NUMERIC(30,2)` | قیمت و مبلغ |
| `NUMERIC(5,2)` | درصد تخفیف و Cashback |
| `TEXT` | عنوان، URL، پیام و Payload متنی |
| `VARCHAR` | کدها و مقادیر متنی محدود |
| `BOOLEAN` | پرچم‌ها و Availability |
| `TIMESTAMPTZ` | زمان همراه با Timezone |
| `JSONB` | Payload خام و جزئیات ساختاریافته |
| `CHAR(3)` | کد ارز مانند `IRR` |

---

# 12. قواعد داده‌ای مهم

## 12.1 قیمت

- قیمت با `NUMERIC(30,2)` ذخیره می‌شود.
- قیمت استاندارد خروجی در Batch 6 با `currency_code = 'IRR'` ذخیره شده است.
- قیمت خالی می‌تواند `NULL` باشد.
- قیمت صفر با Flag کیفیت نگه‌داری می‌شود.
- قیمت Outlier با Flag نگه‌داری می‌شود و حذف خاموش نمی‌شود.

## 12.2 درصد

- `discount_percent` و `cash_back_percent` با `NUMERIC(5,2)` ذخیره می‌شوند.
- بازهٔ مورد انتظار 0 تا 100 است.

## 12.3 Merchant

- `merchant_key` در Fact Nullable است.
- برای Sourceهای فاقد Seller Identity مقدار ساختگی ایجاد نمی‌شود.

## 12.4 Product

- Product بر اساس Source و Business Key شناسایی می‌شود.
- Source ID در صورت وجود اولویت دارد.
- در نبود Source ID، عنوان نرمال‌شده به‌عنوان بخش Fallback استفاده می‌شود.

## 12.5 کیفیت

- Issueها در Audit ثبت می‌شوند.
- Duplicate و Outlier با Flag در Fact قابل مشاهده‌اند.
- Raw Data برای بررسی مجدد حفظ می‌شود.

---

# 13. محدودیت‌های مستندسازی

این Data Dictionary باید همیشه با DDL واقعی پروژه هماهنگ باشد.

قبل از تحویل نهایی، این موارد باید بررسی شوند:

1. ستون‌های هر جدول با `sql/02_create_tables.sql` مقایسه شوند.
2. نوع و Nullable بودن ستون‌ها با DDL نهایی تطبیق داده شود.
3. نام ستون‌های `audit.etl_run_logs` با ساختار واقعی اصلاح شود.
4. نام Viewها با `sql/05_create_views.sql` تطبیق داده شود.
5. اگر ستونی در SQL اضافه یا حذف شد، این سند نیز به‌روزرسانی شود.
6. آمار Batch 6 به‌عنوان Snapshot همان اجرا شناخته شود، نه مقدار دائمی
   Schema.

---

# 14. فایل‌های مرتبط

| فایل | ارتباط |
|---|---|
| `sql/01_create_schemas.sql` | تعریف Schemaها |
| `sql/02_create_tables.sql` | تعریف جدول‌ها |
| `sql/03_create_constraints.sql` | Constraint و Foreign Key |
| `sql/04_create_indexes.sql` | Indexهای عملکردی |
| `sql/05_create_views.sql` | Viewهای Analytics |
| `docs/architecture.md` | معماری و جریان داده |
| `docs/cleaning_rules.md` | قوانین Cleaning و Transformation |
| `docs/validation_rules.md` | قوانین Validation |
| `docs/performance_report.md` | تست و گزارش Performance |
