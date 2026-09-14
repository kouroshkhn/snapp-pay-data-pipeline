فایل `README.md` فعلی را خواندم. چند ناهماهنگی با واقعیت پروژه دارد:

- نام فایل‌های مستندات در `docs/` با ساختار واقعی (`architecture.md`, `cleaning_rules.md`, ...) همخوانی ندارد.
- آمار منابع (تعداد رکورد) با خروجی واقعی دیتابیس (Batch 6) متفاوت است.
- برخی بخش‌ها ناقص یا کلی هستند (مثلاً Quick Start برای ویندوز بهینه نیست).
- ساختار پروژه با آنچه ساختید (`sql/01_create_schemas.sql` تا `07_performance_tests.sql`) هماهنگ نیست.

در ادامه، نسخهٔ **بازنویسی‌شده و دقیق** `README.md` را بر اساس کل داده‌های واقعی پروژه (کدها، دیتابیس، مستندات) ارائه می‌دهم.

---

# Snapp Pay Data Pipeline

**سامانهٔ پایش قیمت و تحلیل بازار در حوزهٔ تجارت الکترونیک**

این پایپلاین داده، اطلاعات محصولات، فروشندگان و قیمت‌ها را از ۱۵ منبع مختلف جمع‌آوری می‌کند، پس از پاک‌سازی، اعتبارسنجی و تبدیل، در یک پایگاه دادهٔ ستاره‌ای (Star Schema) بارگذاری می‌کند و خروجی استاندارد و بهینه‌شده برای مصرف توسط داشبورد یا API فراهم می‌کند.

> ⚠️ **توجه:** طراحی داشبورد جزو محدودهٔ این پروژه نیست. تمرکز صرفاً بر مدیریت، پاک‌سازی، پردازش، مدل‌سازی و ارائهٔ داده‌های آمادهٔ مصرف است.

---

## ویژگی‌های کلیدی

- **استخراج چندفرمتی:** پشتیبانی از CSV و XLSX با تشخیص خودکار Encoding (UTF-8, Windows-1256, CP1252)
- **پاک‌سازی داده:** نرمال‌سازی متن فارسی/عربی، تبدیل واحد پول (تومان → ریال)، پاک‌سازی URL و Availability
- **اعتبارسنجی داده:** ۹ Rule اعتبارسنجی با سطح‌بندی ERROR و WARNING
- **تشخیص تکرار:** Duplicate Detection بر اساس `source_id` و Fallback Key (Title + Merchant + Price)
- **تشخیص ناهنجاری قیمت:** روش Log-IQR برای شناسایی Outlierهای آماری
- **مدل ستاره‌ای:** ۴ لایهٔ Raw، Staging، Core، Audit با ۱۳ جدول اصلی
- **بهینه‌سازی عملکرد:** ۵۵ Index استراتژیک روی جدول‌های پرجستجو
- **لایهٔ تحلیلی:** ۶ View آماده برای Dashboard و ۱۰ Query نمونه
- **مستندات کامل:** ۵ فایل مستندات معماری، قوانین، دیکشنری داده، Validation و Performance

---

## شروع سریع (Quick Start)

### پیش‌نیازها

- Python 3.13
- PostgreSQL 18
- Git

### نصب و راه‌اندازی

```
# 1. Clone repository (اگر از Git استفاده می‌کنید)
# git clone <repository-url>
# cd snapp-pay-data-pipeline

# 2. ساخت محیط مجازی (Windows PowerShell)
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 3. نصب وابستگی‌ها
pip install pandas numpy psycopg-binary openpyxl chardet

# 4. تنظیم متغیرهای محیطی (System Environment Variables)
# DB_HOST=localhost
# DB_PORT=5432
# DB_NAME=snapp_pay_db
# DB_USER=postgres
# DB_PASSWORD=your_password

# 5. ایجاد Schemaها و جداول در PostgreSQL
psql -U postgres -d snapp_pay_db -f sql/01_create_schemas.sql
psql -U postgres -d snapp_pay_db -f sql/02_create_tables.sql
psql -U postgres -d snapp_pay_db -f sql/03_create_constraints.sql
psql -U postgres -d snapp_pay_db -f sql/04_create_indexes.sql
psql -U postgres -d snapp_pay_db -f sql/05_create_views.sql

# 6. اجرای کامل پایپلاین
python -u src/main.py
```

### خروجی مورد انتظار

```
======================================================================
Snapp Pay Data Pipeline - Starting
======================================================================

✓ All prerequisites satisfied.

[1/5] Running Transform...
✓ Transform completed.

[2/5] Running Validation...
✓ Validation completed.

[3/5] Running Duplicate Detection...
✓ Duplicate detection completed.

[4/5] Running Outlier Detection...
✓ Outlier detection completed.

[5/5] Loading to PostgreSQL...
✓ Load completed.

[BONUS] Calculating analytics metrics...
✓ Metrics calculated.

======================================================================
Pipeline completed successfully!
Total duration: 840 seconds
======================================================================

SUCCESS: batch_id=6; raw=1,187,166; staging=1,187,166; issues=431,556; core=1,018,098
```

---

## ساختار پروژه

```
snapp-pay-data-pipeline/
├── raw/                          # فایل‌های خام ورودی (15 فایل)
│   ├── arkaapi_first_50_pages.xlsx
│   ├── Digikala - Health & Beauty.xlsx
│   ├── SnappPay - All Cats - 2026-08-23.csv
│   ├── Torob - Home & Electronics - 2026-08-03.xlsx
│   └── ...
│
├── data/
│   ├── raw/                      # داده‌های خام استخراج‌شده
│   ├── interim/                  # داده‌های میانی
│   └── processed/                # خروجی نهایی و Metrics JSON
│       └── analytics_metrics.json
│
├── docs/                         # مستندات پروژه
│   ├── architecture.md           # معماری پایپلاین و Schema
│   ├── cleaning_rules.md         # قوانین پاک‌سازی و تبدیل
│   ├── data_dictionary.md        # دیکشنری کامل داده‌ها
│   ├── validation_rules.md       # قوانین اعتبارسنجی
│   └── performance_report.md     # گزارش عملکرد و بهینه‌سازی
│
├── notebooks/
│   └── data_profiling.ipynb      # تحلیل اکتشافی داده
│
├── sql/                          # اسکریپت‌های SQL
│   ├── 01_create_schemas.sql     # ایجاد Schemaها
│   ├── 02_create_tables.sql      # ایجاد جداول
│   ├── 03_create_constraints.sql # Constraintها و FKها
│   ├── 04_create_indexes.sql     # 55 Index بهینه‌سازی
│   ├── 05_create_views.sql       # 6 View تحلیلی
│   ├── 06_dashboard_queries.sql  # 10 Query نمونه Dashboard
│   └── 07_performance_tests.sql  # تست Performance
│
├── src/                          # کد منبع Python
│   ├── config.py                 # تنظیمات و اتصال به دیتابیس
│   ├── extract.py                # لایهٔ استخراج
│   ├── transform.py              # لایهٔ تبدیل و پاک‌سازی
│   ├── validators.py             # قوانین اعتبارسنجی
│   ├── detect_duplicates.py      # تشخیص داده‌های تکراری
│   ├── detect_price_outliers.py  # تشخیص ناهنجاری قیمت
│   ├── load_pipeline.py          # لایهٔ بارگذاری
│   ├── main.py                   # Orchestrator اصلی
│   ├── metrics.py                # محاسبهٔ Metricهای تحلیلی
│   ├── source_mappings.py        # Mapping منابع
│   └── test_db_connection.py     # تست اتصال
│
├── tests/
│   ├── test_transform.py         # تست واحد Transform
│   └── test_validate.py          # تست واحد Validation
│
└── README.md                     # این فایل
```

---

## منابع داده (Data Sources)

|Source|فایل‌ها|رکوردهای خام|نوع Source|
|---|---|---|---|
|Torob|2|569,413|PRICE_COMPARISON|
|SnappPay|4|163,595|MARKETPLACE|
|Technolife|1|158,000|DIRECT|
|Digikala|2|55,339|MARKETPLACE|
|Khanoumi|1|49,481|DIRECT|
|Zanoone|1|17,007|DIRECT|
|Arka|1|2,614|DIRECT|
|XiaomiXiaomi|1|2,484|DIRECT|
|Sormehshop|1|141|DIRECT|
|TorobPay|1|24|PRICE_COMPARISON|
|**مجموع**|**15**|**1,187,166**|—|

---

## آمار نهایی پایپلاین (Batch 6)

|معیار|مقدار|
|---|---|
|رکوردهای Raw|1,187,166|
|رکوردهای Staging|1,187,166|
|رکوردهای Core Fact|1,018,098|
|Products یکتا|642,600|
|Merchants|3,527|
|Brands|2,101|
|Categories|1,886|
|Validation Issues|431,556|
|Duplicate Candidates|195,808|
|Price Outliers|9,629|
|میانگین قیمت (بدون Outlier)|160,369,412 ریال|
|Median قیمت|14,500,000 ریال|

---

## مثال: دسترسی به داده برای Dashboard

```
import psycopg

def get_source_summary(conn_params: dict) -> list[dict]:
    """
    دریافت خلاصهٔ آماری هر Source برای Dashboard.
    
    Args:
        conn_params: دیکشنری شامل DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD
    
    Returns:
        لیستی از دیکشنری‌ها با کلیدهای:
        source_code, source_name, total_listings, distinct_products, avg_price_excl_outliers
    """
    with psycopg.connect(**conn_params) as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT 
                source_code, 
                source_name, 
                total_listings,
                distinct_products, 
                avg_price_excl_outliers
            FROM analytics.vw_source_summary
            ORDER BY total_listings DESC
        """)
        cols = [d.name for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


# مثال استفاده
if __name__ == "__main__":
    conn_params = {
        "host": "localhost",
        "port": 5432,
        "dbname": "snapp_pay_db",
        "user": "postgres",
        "password": "your_password"
    }
    
    summary = get_source_summary(conn_params)
    for row in summary[:5]:
        print(f"{row['source_name']}: {row['total_listings']:,} listings, "
              f"avg price: {row['avg_price_excl_outliers']:,.0f} IRR")
```

**خروجی نمونه:**

```
Torob: 569,413 listings, avg price: 145,527,469 IRR
SnappPay: 163,595 listings, avg price: 213,088,488 IRR
Technolife: 158,000 listings, avg price: 110,033,466 IRR
Digikala: 55,339 listings, avg price: 335,292,065 IRR
Khanoumi: 49,481 listings, avg price: 207,225,836 IRR
```

---

## اجرای تست‌ها

```
# فعال‌سازی محیط مجازی
.\.venv\Scripts\Activate.ps1

# اجرای تست‌های واحد
python -m pytest tests/ -v
```

---

## مستندات

|فایل|توضیح|
|---|---|
|[`docs/architecture.md`](https://www.perplexity.ai/search/docs/architecture.md)|معماری پایپلاین، لایه‌های Schema، Mapping منابع|
|[`docs/cleaning_rules.md`](https://www.perplexity.ai/search/docs/cleaning_rules.md)|قوانین پاک‌سازی متن، قیمت، URL، Availability|
|[`docs/data_dictionary.md`](https://www.perplexity.ai/search/docs/data_dictionary.md)|دیکشنری کامل جداول، ستون‌ها و روابط|
|[`docs/validation_rules.md`](https://www.perplexity.ai/search/docs/validation_rules.md)|قوانین اعتبارسنجی و Severity هر Rule|
|[`docs/performance_report.md`](https://www.perplexity.ai/search/docs/performance_report.md)|گزارش Performance، Indexها، بهینه‌سازی Queryها|

---

## تکنولوژی‌های استفاده‌شده

|جزء|تکنولوژی|نسخه|
|---|---|---|
|زبان برنامه‌نویسی|Python|3.13|
|پایگاه داده|PostgreSQL|18|
|پردازش داده|Pandas, NumPy|Latest|
|درایور دیتابیس|Psycopg|3|
|پردازش Excel|OpenPyXL|Latest|
|تشخیص Encoding|Chardet|Latest|
|کنترل نسخه|Git|Latest|
|سیستم عامل|Windows|11|

---

## مجوز و محدودیت‌ها

- تمام داده‌ها به‌صورت محلی و روی سرور امن ذخیره شده‌اند.
- دسترسی به دیتابیس محدود به کاربران مجاز است.
- هیچ اطلاعات شناسایی‌کنندهٔ شخصی (PII) جمع‌آوری نشده است.
- سیاست نگهداری داده: داده‌های Raw به‌صورت نامحدود، داده‌های پردازش‌شده ۲ سال.