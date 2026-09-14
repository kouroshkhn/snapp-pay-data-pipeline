# Snapp Pay Data Pipeline — Validation Rules

## 1. هدف سند

این سند قوانین اعتبارسنجی داده را در پایپلاین Snapp Pay توضیح می‌دهد.

Validation پس از Extract و Transformation انجام می‌شود و هدف آن شناسایی
داده‌هایی است که:

- برای استفادهٔ تحلیلی ناقص هستند.
- با قواعد کسب‌وکار سازگار نیستند.
- احتمالاً تکراری هستند.
- قیمت غیرعادی دارند.
- از نظر ساختار فایل یا مقدار ستون‌ها ناسالم هستند.

نتیجهٔ Validation در جدول زیر ذخیره می‌شود:

```text
audit.validation_issues
```

اعتبارسنجی باعث حذف Raw Data نمی‌شود. رکورد خام همچنان در
`raw.raw_product_records` نگه‌داری می‌شود و دادهٔ استانداردشده نیز در
Staging قابل بررسی است.

---

## 2. جایگاه Validation در پایپلاین

ترتیب اجرای مراحل اصلی به شکل زیر است:

```text
Extract
   |
   v
Raw Layer
   |
   v
Transform and Cleaning
   |
   v
Staging Layer
   |
   v
Validation
   |
   +--> audit.validation_issues
   |
   +--> validation_status
   |
   v
Duplicate Detection
   |
   v
Price Outlier Detection
   |
   v
Core Layer
```

Validation روی دادهٔ استانداردشدهٔ Staging انجام می‌شود، نه مستقیماً روی
مقدار خام فایل.

---

## 3. سطوح Severity

هر Issue دارای یک سطح اهمیت است.

| Severity | معنی | رفتار معمول |
|---|---|---|
| `ERROR` | رکورد یا فیلد برای استفادهٔ عادی قابل اعتماد نیست | ممکن است از Core حذف شود |
| `WARNING` | رکورد قابل استفاده است، اما مشکل کیفیت دارد | رکورد حفظ و Flag می‌شود |
| `INFO` | نکتهٔ اطلاع‌رسانی یا اصلاح قابل‌ردیابی | در Audit ثبت می‌شود |

### 3.1 تفاوت Issue و حذف رکورد

ثبت Issue به‌تنهایی به معنی حذف رکورد نیست.

رفتار نهایی رکورد به این موارد بستگی دارد:

- نوع Rule.
- Severity.
- وضعیت عنوان و کلیدهای لازم.
- منطق Load به Core.
- وجود Duplicate قطعی.
- قابل استفاده بودن رکورد برای مدل Core.

در نتیجه، یک رکورد می‌تواند در Raw و Staging وجود داشته باشد اما به Core
وارد نشود.

---

## 4. ساختار ثبت Issue

Issueها در جدول زیر ثبت می‌شوند:

```text
audit.validation_issues
```

اطلاعات مهم ثبت‌شده برای هر Issue شامل موارد زیر است:

| فیلد | توضیح |
|---|---|
| `issue_id` | شناسهٔ Issue |
| `batch_id` | Batch ایجادکنندهٔ Issue |
| `raw_record_id` | شناسهٔ رکورد خام |
| `stg_listing_id` | شناسهٔ رکورد Staging |
| `listing_id` | شناسهٔ رکورد Core، در صورت وجود |
| `rule_code` | کد Rule |
| `severity` | سطح Issue |
| `field_name` | فیلد دارای مشکل |
| `field_value` | مقدار مشکل‌دار |
| `action_taken` | اقدامی که برای رکورد انجام شده |
| `message` | توضیح متنی Issue |
| `detected_at` | زمان شناسایی |

این ساختار باعث می‌شود هر Issue تا حد امکان به رکورد خام، رکورد Staging و
رکورد Core قابل ردیابی باشد.

---

## 5. کاتالوگ قوانین Validation

### 5.1 `REQ_TITLE`

| ویژگی | مقدار |
|---|---|
| فیلد | `product_title` |
| Severity | `ERROR` |
| شرط | عنوان پس از Cleaning خالی یا `NULL` باشد |
| Action | ثبت Issue و عدم ورود رکورد فاقد عنوان معتبر به Core |
| وضعیت رکورد | معمولاً `INVALID` یا حذف از Core |

عنوان محصول یکی از فیلدهای اصلی مدل Product است. رکوردی که عنوان قابل
استفاده ندارد نمی‌تواند به‌صورت مطمئن در Dimension محصول قرار گیرد.

در Batch 6 یک مورد از این Rule ثبت شد.

---

### 5.2 `MISSING_PRICE`

| ویژگی | مقدار |
|---|---|
| فیلد | `price` |
| Severity | `WARNING` |
| شرط | قیمت `NULL` باشد |
| Action | ثبت Issue |
| وضعیت رکورد | در صورت امکان حفظ می‌شود؛ رفتار Core وابسته به Load Rule است |

قیمت ناموجود الزاماً به معنی حذف از Raw یا Staging نیست. این رکوردها برای
تحلیل Completeness و بررسی منبع نگه‌داری می‌شوند.

در Batch 6 تعداد این Issue برابر بود با:

```text
16,174
```

---

### 5.3 `ZERO_PRICE`

| ویژگی | مقدار |
|---|---|
| فیلد | `price` |
| Severity | `WARNING` |
| شرط | قیمت برابر صفر باشد |
| Action | ثبت Issue و نگه‌داری Flag |
| وضعیت رکورد | قابل حفظ در Staging و در صورت معتبر بودن سایر فیلدها قابل ورود به Core |

قیمت صفر ممکن است نشان‌دهندهٔ دادهٔ ناقص، محصول رایگان، خطای استخراج یا
عدم درج قیمت توسط منبع باشد.

در Batch 6 تعداد این Issue برابر بود با:

```text
38,584
```

---

### 5.4 `NEGATIVE_PRICE`

| ویژگی | مقدار |
|---|---|
| فیلد | `price` |
| Severity | طبق پیاده‌سازی فعلی باید از کد نهایی تأیید شود |
| شرط | قیمت کمتر از صفر باشد |
| Action پیشنهادی | ثبت Issue و جلوگیری از استفادهٔ عادی در Core |
| وضعیت پیشنهادی | `INVALID` یا حذف از Core |

قیمت منفی از نظر کسب‌وکار معتبر نیست.

نکتهٔ مهم: این Rule در کاتالوگ پروژه تعریف شده است، اما در فهرست Issueهای
ثبت‌شده برای Batch 6 نمایش داده نشد. بنابراین تعداد واقعی آن در Batch 6
نباید بدون Query مستقیم از دیتابیس اعلام شود.

برای بررسی:

```sql
SELECT
    rule_code,
    severity,
    COUNT(*) AS issue_count
FROM audit.validation_issues
WHERE batch_id = 6
  AND rule_code = 'NEGATIVE_PRICE'
GROUP BY rule_code, severity;
```

---

### 5.5 `OLD_PRICE_LT_PRICE`

| ویژگی | مقدار |
|---|---|
| فیلدها | `old_price`, `price` |
| Severity | `WARNING` |
| شرط | `old_price < price` |
| Action | ثبت ناسازگاری تجاری |
| وضعیت رکورد | رکورد حذف نمی‌شود |

در حالت معمول، قیمت قبلی باید بزرگ‌تر یا مساوی قیمت فعلی باشد. اگر قیمت
قبلی کمتر از قیمت فعلی باشد، احتمال خطای استخراج، جابه‌جایی ستون‌ها یا
تفسیر اشتباه قیمت وجود دارد.

در Batch 6 تعداد این Issue برابر بود با:

```text
428
```

---

### 5.6 `INVALID_PERCENTAGE`

| ویژگی | مقدار |
|---|---|
| فیلدها | `discount_percent`, `cash_back_percent` |
| Severity | `WARNING` |
| شرط | مقدار خارج از بازهٔ 0 تا 100 باشد |
| Action | ثبت Issue و تبدیل مقدار نامعتبر به `NULL` |
| وضعیت رکورد | رکورد اصلی در صورت معتبر بودن سایر فیلدها حفظ می‌شود |

قانون معتبر بودن درصد:

```text
0 <= percentage <= 100
```

مقادیر زیر باید بررسی شوند:

```text
-5
101
150
```

در صورت وجود مقدار Fraction، مانند `0.15`، تبدیل آن باید مطابق Contract
Transformation انجام شود و نباید بدون تعریف قرارداد به‌صورت خودکار تفسیر
شود.

تعداد ثبت‌شدهٔ این Rule باید از دیتابیس بررسی شود. اگر در Batch 6 Issue
برای آن وجود نداشته باشد، نباید عددی برای آن در گزارش اعلام شود.

---

### 5.7 `INVALID_URL`

| ویژگی | مقدار |
|---|---|
| فیلدها | `product_url`, `image_url` |
| Severity | طبق Contract فعلی: `INFO` |
| شرط | مقدار با `http://` یا `https://` شروع نشود |
| Action | URL نامعتبر به `NULL` تبدیل و Issue ثبت می‌شود |
| وضعیت رکورد | معمولاً رکورد حذف نمی‌شود |

URL نامعتبر معمولاً مانع تحلیل قیمت یا محصول نمی‌شود؛ بنابراین بهتر است
به‌عنوان مشکل فیلد URL ثبت شود، نه دلیل حذف کل Listing.

تعداد ثبت‌شدهٔ این Rule در Batch 6 باید از دیتابیس خوانده شود. در خروجی
Issueهای ارسالی Batch 6، این Rule نمایش داده نشد.

---

### 5.8 `INVALID_AVAILABILITY_COLUMN`

| ویژگی | مقدار |
|---|---|
| فیلد | Availability |
| Severity | `WARNING` |
| شرط | مقدار خام به `TRUE` یا `FALSE` قابل نگاشت نباشد |
| Action | تنظیم `is_available = NULL` و ثبت Issue |
| وضعیت رکورد | رکورد حفظ می‌شود |

نمونهٔ مقادیر قابل نگاشت:

| مقدار خام | مقدار استاندارد |
|---|---|
| `موجود` | `TRUE` |
| `available` | `TRUE` |
| `in_stock` | `TRUE` |
| `1` | `TRUE` |
| `ناموجود` | `FALSE` |
| `unavailable` | `FALSE` |
| `out_of_stock` | `FALSE` |
| `0` | `FALSE` |

در Batch 6 یک مورد از این Rule ثبت شد.

---

### 5.9 `DUPLICATE_SOURCE_ID`

| ویژگی | مقدار |
|---|---|
| فیلد | `source_id` |
| Severity | `WARNING` |
| شرط | یک `source_id` در یک Source بیش از یک‌بار ظاهر شود |
| Action | ثبت Issue و Flag کردن رکوردهای تکراری |
| Flag | `is_duplicate_candidate = TRUE` |

کلید Duplicate این Rule به‌صورت منطقی چنین است:

```text
(source, source_id)
```

رکوردهای تکراری قطعی بر اساس Source ID معمولاً برای جلوگیری از تکرار در
Fact نهایی از Core حذف می‌شوند یا فقط یک رکورد نمایندهٔ آن‌ها به Core
وارد می‌شود؛ اما Raw، Staging و Audit آن‌ها باقی می‌ماند.

در Batch 6 تعداد این Issue برابر بود با:

```text
198,922
```

---

### 5.10 `DUPLICATE_FALLBACK_KEY`

| ویژگی | مقدار |
|---|---|
| فیلدها | عنوان نرمال‌شده، Merchant، قیمت |
| Severity | `WARNING` |
| شرط | رکوردهایی که Source ID ندارند و کلید جایگزین یکسان دارند |
| Action | ثبت Issue و Flag کردن رکوردها |
| Flag | `is_duplicate_candidate = TRUE` |

کلید جایگزین به‌صورت مفهومی از ترکیب زیر ساخته می‌شود:

```text
(source, product_title_normalized, merchant_name, price)
```

این Rule نسبت به Duplicate بر اساس Source ID قطعیت کمتری دارد؛ زیرا دو
محصول متفاوت ممکن است عنوان و قیمت یکسان داشته باشند.

در Batch 6 تعداد این Issue برابر بود با:

```text
165,953
```

---

### 5.11 `PRICE_OUTLIER`

| ویژگی | مقدار |
|---|---|
| فیلد | `price` |
| Severity | `WARNING` |
| شرط | قیمت از بازهٔ آماری تعریف‌شده خارج باشد |
| Action | ثبت Issue و Flag کردن رکورد |
| Flag | `is_price_outlier = TRUE` |

تشخیص Outlier برای قیمت‌های مثبت انجام می‌شود. در روش مورد استفاده، مقدار
قیمت به فضای لگاریتمی منتقل می‌شود و با روش IQR بررسی می‌گردد.

فرم مفهومی بازه:

```text
lower_bound = Q1 - 3 * IQR
upper_bound = Q3 + 3 * IQR
```

در فضای لگاریتمی:

```text
log10(price)
```

قیمت‌هایی خارج از این بازه به‌عنوان Outlier شناسایی می‌شوند.

در Batch 6:

```text
Audit PRICE_OUTLIER issues: 11,492
Core rows with is_price_outlier = TRUE: 9,629
```

این دو عدد باید یکسان فرض نشوند. Audit ممکن است Issueهای بیشتری را شامل
شود، درحالی‌که Core فقط رکوردهایی را دارد که پس از سایر قواعد Load وارد
Fact شده‌اند.

Outlier حذف نمی‌شود؛ زیرا ممکن است قیمت واقعی یک کالای گران باشد. این
پرچم به Query یا Dashboard اجازه می‌دهد در صورت نیاز آن را فیلتر کند.

---

### 5.12 `FILE_EXTENSION_CONTENT_MISMATCH`

| ویژگی | مقدار |
|---|---|
| فیلد | فایل ورودی |
| Severity | `WARNING` |
| شرط | محتوای فایل با پسوند اعلام‌شده سازگار نباشد |
| Action | ثبت Issue و تلاش برای خواندن با مسیر جایگزین |
| وضعیت رکورد | وابسته به موفقیت خواندن فایل |

این Rule مربوط به خود فایل است، نه یک محصول خاص.

در Batch 6 یک مورد از این Rule ثبت شد.

---

## 6. وضعیت Validation در Fact

رکوردهای Core با وضعیت اعتبارسنجی ذخیره می‌شوند.

مقادیر مورد استفاده:

| مقدار | معنی |
|---|---|
| `VALID` | رکورد بدون Warning مهم |
| `VALID_WITH_WARNINGS` | رکورد قابل استفاده، اما دارای Warning |
| `INVALID` | رکورد دارای مشکل اساسی یا غیرقابل استفاده |

وجود Warning به‌تنهایی به معنی حذف رکورد از Core نیست.

نمونه:

```text
price = 0
```

می‌تواند باعث ثبت `ZERO_PRICE` شود، اما رکورد در صورت داشتن عنوان و ساختار
قابل استفاده، ممکن است با وضعیت `VALID_WITH_WARNINGS` در Core باقی بماند.

---

## 7. مثال‌های Validation

### 7.1 رکورد معتبر

```json
{
  "product_title": "گوشی سامسونگ S24",
  "price": 15000000,
  "old_price": 18000000,
  "discount_percent": 16.67,
  "is_available": true
}
```

نتیجه:

```text
validation_status = VALID
```

---

### 7.2 رکورد معتبر با Warning

```json
{
  "product_title": "محصول نمونه",
  "price": 0,
  "old_price": null,
  "is_available": null
}
```

نتیجه:

```text
rule_code = ZERO_PRICE
severity = WARNING
validation_status = VALID_WITH_WARNINGS
```

---

### 7.3 رکورد فاقد عنوان

```json
{
  "product_title": null,
  "price": 15000000
}
```

نتیجه:

```text
rule_code = REQ_TITLE
severity = ERROR
```

این رکورد نمی‌تواند به‌عنوان Product معتبر وارد Core شود.

---

### 7.4 رکورد تکراری

```json
{
  "source": "torob",
  "source_id": "ABC-123",
  "product_title": "محصول نمونه",
  "price": 15000000
}
```

اگر همین ترکیب Source و Source ID در رکورد دیگری نیز وجود داشته باشد:

```text
rule_code = DUPLICATE_SOURCE_ID
is_duplicate_candidate = TRUE
```

---

### 7.5 رکورد دارای قیمت پرت

```json
{
  "product_title": "محصول نمونه",
  "price": 3284000003336000000
}
```

اگر قیمت نسبت به توزیع قیمت گروه مربوطه خارج از محدودهٔ آماری باشد:

```text
rule_code = PRICE_OUTLIER
is_price_outlier = TRUE
```

قیمت در Raw و Staging حفظ می‌شود، اما Queryهای تحلیلی می‌توانند آن را
فیلتر کنند.

---

## 8. کیفیت داده در سطح Source و Batch

جدول زیر برای نگهداری شاخص‌های تجمیعی کیفیت استفاده می‌شود:

```text
audit.data_quality_metrics
```

Metricهای اصلی شامل موارد زیر هستند:

- تعداد کل رکوردها.
- تعداد رکوردهای دارای عنوان.
- تعداد رکوردهای دارای قیمت مثبت.
- تعداد رکوردهای دارای قیمت صفر.
- تعداد رکوردهای فاقد قیمت.
- تعداد رکوردهای دارای Brand.
- تعداد رکوردهای دارای Category.
- تعداد رکوردهای موجود.
- تعداد رکوردهای ناموجود.
- تعداد رکوردهای با Availability ناشناخته.
- تعداد Duplicate Candidateها.
- تعداد Price Outlierها.
- تعداد Issueهای `ERROR`.
- تعداد Issueهای `WARNING`.
- تعداد Issueهای `INFO`.

این Metricها باید همیشه با `batch_id` و Source قابل ارتباط باشند.

---

## 9. نتایج Batch 6

اجرای موفق Batch 6 دارای نتایج زیر بود:

| معیار | مقدار |
|---|---:|
| Raw records | 1,187,166 |
| Staging records | 1,187,166 |
| Core listings | 1,018,098 |
| Validation issues | 431,556 |

توزیع Issueهای ثبت‌شده:

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

جمع Issueهای جدول بالا برابر با 431,556 است.

```text
198,922
+ 165,953
+ 38,584
+ 16,174
+ 11,492
+ 428
+ 1
+ 1
+ 1
= 431,556
```

---

## 10. Queryهای پایش کیفیت

### 10.1 خلاصهٔ Issueها بر اساس Rule

```sql
SELECT
    rule_code,
    severity,
    COUNT(*) AS issue_count
FROM audit.validation_issues
WHERE batch_id = 6
GROUP BY rule_code, severity
ORDER BY issue_count DESC;
```

### 10.2 خلاصهٔ Issueها بر اساس Source

در صورتی که رابطهٔ Source از طریق رکورد خام یا Staging در Query قابل
دسترسی باشد، می‌توان Issueها را بر اساس Source نیز گروه‌بندی کرد.

### 10.3 بررسی وضعیت Batch

```sql
SELECT
    batch_id,
    run_status,
    started_at,
    finished_at,
    records_extracted,
    records_loaded_staging,
    records_loaded_core,
    error_message
FROM raw.ingestion_batches
ORDER BY batch_id DESC
LIMIT 5;
```

### 10.4 بررسی رکوردهای Outlier در Core

```sql
SELECT
    f.listing_id,
    f.product_key,
    f.price,
    f.is_price_outlier,
    p.product_title
FROM core.fact_product_listings AS f
JOIN core.dim_products AS p
    ON p.product_key = f.product_key
WHERE f.is_price_outlier = TRUE
ORDER BY f.price DESC
LIMIT 50;
```

### 10.5 بررسی رکوردهای Duplicate Candidate در Core

```sql
SELECT
    f.listing_id,
    f.product_key,
    f.price,
    f.is_duplicate_candidate,
    p.product_title
FROM core.fact_product_listings AS f
JOIN core.dim_products AS p
    ON p.product_key = f.product_key
WHERE f.is_duplicate_candidate = TRUE
LIMIT 50;
```

---

## 11. Thresholdهای پیشنهادی برای پایش

Thresholdهای زیر معیار پیشنهادی برای Monitoring هستند و در نسخهٔ فعلی به
معنی Alert خودکار یا Notification خودکار نیستند.

| معیار | Warning | Critical |
|---|---:|---:|
| Error rate | بیشتر از 1٪ | بیشتر از 5٪ |
| Warning rate | بیشتر از 10٪ | بیشتر از 25٪ |
| Duplicate rate | بیشتر از 15٪ | بیشتر از 30٪ |
| Outlier rate | بیشتر از 1٪ | بیشتر از 5٪ |
| Title completeness | کمتر از 95٪ | کمتر از 80٪ |
| Price completeness | کمتر از 90٪ | کمتر از 70٪ |

### نحوهٔ استفاده

اگر یک Source از Threshold عبور کند:

1. Batch نباید فوراً بدون بررسی رد شود.
2. باید Source و فایل مربوط به آن مشخص شود.
3. Ruleهای غالب بررسی شوند.
4. تفاوت بین مشکل واقعی داده و Bug در Parser جدا شود.
5. نتیجه در گزارش کیفیت Batch ثبت شود.

---

## 12. نکات مهم تفسیری

### 12.1 تعداد Issue با تعداد رکورد مشکل‌دار یکسان نیست

یک رکورد می‌تواند چند Issue داشته باشد. بنابراین:

```text
تعداد Issueها ≠ تعداد رکوردهای مشکل‌دار
```

برای مثال یک رکورد می‌تواند هم‌زمان:

- قیمت صفر داشته باشد.
- عنوان ناقص داشته باشد.
- Duplicate باشد.
- Outlier باشد.

### 12.2 تعداد Audit Outlier با تعداد Core Outlier متفاوت است

در Batch 6:

```text
Audit PRICE_OUTLIER = 11,492
Core is_price_outlier = TRUE = 9,629
```

این اختلاف طبیعی است، چون Audit و Core مراحل و هدف متفاوتی دارند.

### 12.3 Warning به معنی حذف نیست

بیشتر Warningها برای حفظ داده و ایجاد امکان تحلیل کیفیت ثبت می‌شوند.
Dashboard می‌تواند هنگام محاسبهٔ قیمت متوسط یا Median، Outlierها و قیمت‌های
صفر را فیلتر کند.

### 12.4 قیمت‌های غیرعادی باید Flag شوند

قیمت بسیار بزرگ الزاماً خطا نیست؛ ممکن است حاصل واحد اشتباه، Parse نامناسب
یا یک محصول خاص باشد. به همین دلیل قیمت در Raw نگه‌داری می‌شود و با
`is_price_outlier` علامت‌گذاری می‌گردد.

---

## 13. محدودیت‌ها و کارهای قابل بهبود

موارد زیر برای نسخهٔ بعدی پیشنهاد می‌شوند:

- اجرای تست مستقیم برای همهٔ Ruleها با دادهٔ مصنوعی.
- ثبت دقیق `action_taken` برای هر نوع Rule.
- افزودن Query برای تعداد رکورد یکتای دارای هر Issue.
- اضافه‌کردن Threshold check به پایان Pipeline.
- ایجاد Alert برای افزایش ناگهانی Error یا Warning rate.
- تفکیک دقیق‌تر Issueهای فایل از Issueهای رکورد.
- ثبت نسخهٔ Ruleها در هر Batch.
- بررسی منبع Price Outlierهای بسیار بزرگ.
- تأیید این‌که همهٔ Ruleهای موجود در مستندات دقیقاً در کد فعال هستند.
- ثبت جداگانهٔ تعداد رکوردهای حذف‌شده از Core به تفکیک دلیل.

---

## 14. جمع‌بندی

Validation در این پروژه بر پایهٔ Audit و Flagging طراحی شده است:

- دادهٔ خام حذف نمی‌شود.
- مشکلات در `audit.validation_issues` ثبت می‌شوند.
- رکوردهای قابل استفاده با Warning در Core باقی می‌مانند.
- رکوردهای دارای مشکل اساسی می‌توانند از Core کنار گذاشته شوند.
- Duplicate و Outlier با Flag در اختیار مصرف‌کنندهٔ داده قرار می‌گیرند.
- شاخص‌های کیفیت در سطح Source و Batch ذخیره می‌شوند.
- Dashboard یا API می‌تواند بر اساس نیاز، رکوردهای Warning، Duplicate و
  Outlier را فیلتر کند.