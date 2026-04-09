# Maestro Yoga

تطبيق مراكز يوغا مبني ببايثون، مخصص للهواتف الذكية واللوحات الذكية، وقابل للتوسع لخدمة مئات المراكز (SaaS متعدد المستأجرين).

## ما الذي يتضمنه هذا الإصدار

- **تشغيل وإنتاج وجوال**: راجع [`docs/operations.md`](docs/operations.md) — صيانة (`MAINTENANCE_MODE`)، CORS، جاهزية قاعدة البيانات (`/health/ready`)، **`/api/v1/*`**، **`GET /api/v1/meta`**، ورؤوس التتبع. **`docs/android-first-steps.md`** — خطوات أولى لأندرويد؛ **`scripts/verify_production_readiness.py`** — فحص الخادم بعد النشر (`BASE_URL=...`).
- **Backend API** باستخدام `FastAPI` مع دعم `SQLite` و`PostgreSQL` عبر متغيرات البيئة.
- **نظام متعدد المراكز** عبر `center_id`.
- **Auth + Roles** باستخدام JWT:
  - center_owner
  - center_staff
  - trainer
  - superadmin
- إدارة:
  - العملاء
  - أنواع الاشتراكات (شهري / سنوي)
  - اشتراكات العملاء
  - الغرف
  - الجلسات
  - الحجوزات
  - المدفوعات
- **تطبيق أندرويد أصلي (Kotlin)** في المجلد [`android/`](android/README.md) — يتصل بـ `GET /api/v1/meta`؛ افتح المجلد في Android Studio.
- **تطبيق موبايل/تابلت** أولي باستخدام `Flet`:
  - عرض الجلسات
  - حجز جلسة
  - تنفيذ دفع تجريبي داخل التطبيق
- **صفحات ويب** (لوحة إدارة + صفحة عامة للجمهور):
  - `/admin/login` ثم `/admin` — المسؤول يضيف الغرف والجلسات (الوقت، المدة، السعر، الغرفة).
  - `/index?center_id=1` — الجمهور يحجز ثم يدفع؛ الحجز يصبح **مؤكدًا** بعد نجاح الدفع (Stripe أو وضع mock). المسار الافتراضي نفسه معرّف في الكود كـ `PUBLIC_INDEX_DEFAULT_PATH` في `backend/app/web_shared.py`.
  - مصادقة جمهور مستقلة:
    - `/public/register` — إنشاء حساب جمهور
    - `/public/login` و`/public/logout`
    - تحقق البريد الإلكتروني عبر رابط `/public/verify-email?token=...`
    - استعادة كلمة المرور:
      - `/public/forgot-password`
      - `/public/reset-password?token=...`
    - لا يمكن إكمال الحجز أو الاشتراك إلا بعد تسجيل الدخول والتحقق من البريد.
    - حماية إضافية:
      - استعادة كلمة المرور عبر البريد
      - إرسال البريد بشكل غير متزامن (Async queue) لتحسين سرعة الاستجابة
      - Rate Limiting جاهز للإنتاج (Redis أو Memory fallback)
      - Audit Logs أمني داخل DB + قسم عرض في لوحة الإدارة مع فلاتر
  - إدارة المستخدمين (الواجهة العامة) في لوحة الإدارة:
    - فلترة وبحث
    - إجراءات جماعية (تفعيل/تعطيل/توثيق/إعادة إرسال/استعادة)
    - حذف آمن بنمط Soft Delete بدل الحذف النهائي

> ملاحظة: الدفع يعمل عبر مزود قابل للتبديل (`PAYMENT_PROVIDER=mock|stripe`). مع Stripe يُفضّل تشغيل `stripe listen` لاستقبال Webhook وتأكيد الحجز.

بعد تحديث قاعدة البيانات (عمود `booking_id` في المدفوعات)، إن واجهت أخطاء قديمة احذف ملف `maestro_yoga.db` وأعد التشغيل.

## التشغيل السريع

1) تجهيز البيئة بشكل متوافق بين الأجهزة:

```bash
powershell -ExecutionPolicy Bypass -File scripts/bootstrap_env.ps1
```

ملفات المتطلبات أصبحت مقسمة للتنظيم:

- `requirements-api.txt` لمكونات الـ API
- `requirements-mobile.txt` لمكونات تطبيق الموبايل
- `requirements.txt` يجمع الاثنين تلقائيًا للتثبيت الكامل كما السابق

## جاهزية النقل إلى Hetzner من الآن

تم تجهيز ملفات جاهزة لتسهيل الانتقال لاحقًا بدون إعادة هيكلة كبيرة:

- `Dockerfile`
- `docker-compose.prod.yml`
- `.env.production.example`
- `.env.staging.example`
- `scripts/backup_postgres.sh`
- `scripts/restore_postgres.sh`
- `docs/render_to_hetzner_migration_checklist.md`
- `render.yaml` — تعريف **PostgreSQL** عبر [Render Blueprint](https://docs.render.com/docs/infrastructure-as-code) (بيانات دائمة؛ عكس SQLite على قرص الحاوية المؤقت).

### Render: إنشاء Postgres وربط التطبيق

1. ادفع `render.yaml` إلى Git، ثم في Render: **Blueprints → New Blueprint Instance** واختر المستودع؛ سيُنشأ قاعدة **`maestro-postgres`**.
2. افتح **Web Service** الخاص بالتطبيق → **Environment**:
   - أزل أو استبدل `DATABASE_URL=sqlite:///...`
   - أضف **`DATABASE_URL`** = **Internal Database URL** من صفحة قاعدة `maestro-postgres` (قسم *Connect*).
3. **Save** ثم **Manual Deploy**. عند أول تشغيل يُنشئ التطبيق الجداول تلقائياً (`init_db`).

بديل يدوي بدون Blueprint: **Dashboard → New → PostgreSQL**، ثم نفس خطوة نسخ Internal URL إلى `DATABASE_URL`.

#### إن ظهر «Deploy failed / Timed out» رغم ظهور Uvicorn في السجلات

- في **Web Service → Settings → Health Checks**: اضبط **Health Check Path** على **`/health`** (أو `/`).
- تأكد أن **Start Command** يستخدم **`$PORT`**، مثال:  
  `python -m uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT`  
  ([توثيق المنفذ](https://render.com/docs/web-services#port-binding)).
- راجع [Troubleshooting deploys](https://render.com/docs/troubleshooting-deploys).

خطوة مقترحة الآن:

1) على التطوير المحلي/Render استمر باستخدام `render.env` أو `.env` حسب الحاجة.  
2) عند بدء النقل الفعلي إلى VPS:
   - انسخ `.env.production.example` إلى `.env.production` مع القيم الحقيقية.
   - شغل: `docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build`
   - طبق Checklist النقل من الملف:
     `docs/render_to_hetzner_migration_checklist.md`
3) سكربتات مساعدة على السيرفر:
   - تهيئة أولية Ubuntu: `scripts/bootstrap_hetzner_ubuntu.sh`
   - نشر التحديثات: `scripts/deploy_prod.sh`
   - التحقق السريع بعد النشر: `scripts/healthcheck_prod.sh`
4) الرجوع/الاستعادة:
   - تحضير قبل النقل: `docs/pre_migration_prep.md`
   - النسخ الاحتياطي: `scripts/backup_postgres.sh`
   - الاسترجاع: `scripts/restore_postgres.sh`

## تشغيل الـ API

```bash
uvicorn backend.app.main:app --reload
```

يفضّل (خصوصًا عند العمل من أكثر من جهاز) التشغيل عبر سكربت المشروع؛ السكربت يقوم تلقائيًا بفحص `.venv` وإعادة بنائها إن كانت مكسورة أو من جهاز آخر:

```bash
powershell -ExecutionPolicy Bypass -File scripts/run_api.ps1 -Port 8000 -Reload
```

خيارات مفيدة:

```bash
# إعادة إنشاء البيئة من الصفر
powershell -ExecutionPolicy Bypass -File scripts/run_api.ps1 -RecreateVenv

# فرض إصدار بايثون معيّن عند الإنشاء (مثال 3.12)
powershell -ExecutionPolicy Bypass -File scripts/run_api.ps1 -PythonSpec "3.12"
```

يمكنك اختيار قاعدة البيانات:

```bash
set DATABASE_URL=sqlite:///./maestro_yoga.db
```

أو PostgreSQL:

```bash
set DATABASE_URL=postgresql+psycopg2://user:password@localhost:5432/maestro_yoga
```

إعداد الدفع:

```bash
set PAYMENT_PROVIDER=mock
```

إعداد البريد للتحقق (اختياري؛ بدون SMTP سيتم طباعة رابط التحقق في logs):

```bash
set SMTP_HOST=smtp.gmail.com
set SMTP_PORT=587
set SMTP_USER=your@email.com
set SMTP_PASSWORD=app-password
set SMTP_FROM=no-reply@maestroyoga.local
```

### حل مشكلة عدم وصول الإيميل (Gmail)

استخدم Gmail عبر SMTP بالطريقة التالية:

1) فعّل التحقق بخطوتين (2FA) في Google Account.  
2) أنشئ **App Password** من إعدادات الأمان.  
3) لا تستخدم كلمة مرور Gmail العادية.

إعداد موصى به في `.env`:

```bash
MAIL_PROVIDER=smtp
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_email@gmail.com
SMTP_PASSWORD=your_16_char_app_password
SMTP_FROM=your_email@gmail.com
SMTP_SECURITY=starttls
MAILER_ASYNC_WORKERS=2
PUBLIC_BASE_URL=http://127.0.0.1:8000
APP_ENV=development
COOKIE_SECURE=0
GA4_MEASUREMENT_ID=G-XXXXXXXXXX
APP_NAME=Maestro Yoga
```

اختبار الإرسال مباشرة:

```bash
.\.venv\Scripts\python scripts/test_email.py --to your_email@gmail.com
```

> التطبيق يحمل `.env` تلقائيًا عند التشغيل.
>
> إذا كان المستخدم يفتح رابط التحقق من جهاز/هاتف مختلف عن جهاز السيرفر، اضبط `PUBLIC_BASE_URL` على دومين أو IP يمكن الوصول إليه من الخارج (ولا تتركه `127.0.0.1`).

### Google Analytics 4 (Funnel Tracking)

لإضافة تتبع funnel جاهز:

1) أنشئ Web Data Stream في GA4.
2) انسخ `Measurement ID` وضعه في:

```bash
GA4_MEASUREMENT_ID=G-XXXXXXXXXX
```

الأحداث التي تُرسلها الواجهة الآن تشمل:

- `page_view_public_index`
- `begin_checkout`
- `purchase_success` / `purchase_cancelled` / `purchase_failed`
- `page_view_public_register` / `sign_up_attempt` / `sign_up_failed` / `sign_up_completed`
- `page_view_public_login` / `login_attempt` / `login_failed`
- `page_view_verify_pending` / `email_verification_resend_attempt` / `email_verification_resent`
- `page_view_forgot_password` / `password_reset_request_attempt`
- `page_view_reset_password` / `password_reset_attempt` / `password_reset_failed`

#### Events Mapping (جاهز للتقارير)

| Event Name | متى يُطلق | باراميترات رئيسية |
|---|---|---|
| `page_view_public_index` | عند فتح `index` | `page_name`, `center_id` |
| `public_cta_click` | عند الضغط على زر حجز/اشتراك | `kind`, `name`, `price` |
| `begin_checkout` | عند بدء خطوة الدفع من الواجهة | `item_category`, `item_name`, `value_text` |
| `purchase_success` | عند عودة الدفع بنجاح | `source` |
| `purchase_cancelled` | عند إلغاء الدفع | `source` |
| `purchase_failed` | عند فشل تهيئة/إرجاع الدفع | `reason` |
| `subscription_activated` | عند تفعيل اشتراك | `mode` |
| `booking_paid_mock` | عند نجاح دفع تجريبي | `mode` |
| `page_view_public_register` | عند فتح صفحة التسجيل | `page_name` |
| `sign_up_attempt` | عند إرسال نموذج التسجيل | — |
| `sign_up_failed` | عند فشل التسجيل (تحقق/حدود/هاتف/SMTP) | `reason` |
| `sign_up_completed` | بعد إنشاء الحساب (صفحة انتظار التحقق) | — |
| `page_view_public_login` | عند فتح صفحة الدخول | `page_name` |
| `login_attempt` | عند إرسال نموذج الدخول | — |
| `login_failed` | عند فشل تسجيل الدخول | `reason` |
| `page_view_verify_pending` | عند فتح صفحة انتظار التحقق | `page_name` |
| `email_verification_resend_attempt` | عند طلب إعادة إرسال التحقق | — |
| `email_verification_resent` | عند نجاح إعادة إرسال رابط التحقق | — |
| `email_verification_resend_failed` | عند فشل إعادة الإرسال | `reason` |
| `page_view_forgot_password` | عند فتح صفحة استعادة كلمة المرور | `page_name` |
| `password_reset_request_attempt` | عند إرسال طلب الاستعادة | — |
| `password_reset_request_accepted` | عند قبول الطلب (بدون كشف وجود الحساب) | — |
| `password_reset_request_failed` | عند فشل إرسال طلب الاستعادة | `reason` |
| `page_view_reset_password` | عند فتح صفحة إعادة التعيين | `page_name` |
| `password_reset_attempt` | عند إرسال كلمة المرور الجديدة | — |
| `password_reset_failed` | عند فشل إعادة التعيين | `reason` |
| `password_reset_completed` | بعد نجاح التعيين والعودة للدخول | — |

#### Recommended GA4 Conversions

- `purchase_success`
- `subscription_activated`
- `sign_up_completed`
- `login_attempt` (اختياري كـ micro-conversion)
- `password_reset_completed` (اختياري)

#### Recommended Funnel (Explorations)

1) `page_view_public_index`  
2) `begin_checkout`  
3) `login_attempt` *(أو `sign_up_attempt` للمستخدم الجديد)*  
4) `sign_up_completed` *(عند التسجيل الجديد)*  
5) `purchase_success` أو `subscription_activated`

### طبقة بريد Production (SPF / DKIM / DMARC)

لتحسين وصول الرسائل بشكل احترافي وتقليل دخولها إلى Spam:

1) استخدم نطاقًا بريدياً خاصًا (مثل `mail.yourdomain.com` أو `yourdomain.com`).
2) أضف سجل **SPF** في DNS.
3) فعّل **DKIM** من مزود البريد (Google Workspace/Resend/SendGrid/Mailgun).
4) أضف سجل **DMARC** بسياسة تدريجية.

مثال مبدئي (يُعدل حسب مزودك):

```txt
SPF   (TXT @): v=spf1 include:_spf.google.com ~all
DMARC (TXT _dmarc): v=DMARC1; p=quarantine; rua=mailto:dmarc@yourdomain.com
DKIM: من مزود الإرسال (selector + public key)
```

> ملاحظة: بدون SPF/DKIM/DMARC صحيحين، حتى لو نجح SMTP قد لا تصل الرسالة لصندوق الوارد.

يمكن اختيار مزود الإرسال:

```bash
set MAIL_PROVIDER=smtp
```

أو عبر `pywhatkit`:

```bash
set MAIL_PROVIDER=pywhatkit
```

> في Gmail يفضّل بشدة استخدام **App Password** بدل كلمة المرور العادية.

إظهار رابط التحقق داخل صفحة `verify-pending` (للتطوير فقط):

```bash
set SHOW_DEV_VERIFY_LINK=1
```

> اتركه `0` في الإنتاج.

إعداد Rate Limiting (Enterprise):

```bash
set RATE_LIMIT_BACKEND=redis
set REDIS_URL=redis://localhost:6379/0
set RATE_LIMIT_PREFIX=maestroyoga:rl
set RATE_LIMIT_MAX_LOCKOUT_SECONDS=900
```

> إذا لم يتوفر Redis أو كان `RATE_LIMIT_BACKEND=auto` سيستخدم التطبيق fallback تلقائيًا إلى Memory.

Audit Logs أمني:

```bash
set SECURITY_AUDIT_LOG_FILE=logs/security_audit.log
set SECURITY_AUDIT_LOG_MAX_BYTES=2097152
set SECURITY_AUDIT_LOG_BACKUPS=5
```

- يسجل أحداث الأمان الحساسة (تسجيل/فشل الدخول، rate limit، استعادة كلمة المرور) مع IP وUser-Agent.

## حل جذري لمشكلة Interpreter بين جهازين

تمت إضافة إعدادات Workspace ثابتة داخل:

- `.vscode/settings.json`

بحيث يعتمد Cursor/VSCode دائمًا على:

- `${workspaceFolder}\.venv\Scripts\python.exe`

وهذا يمنع كسر المسار عند تغيير الجهاز أو اسم المستخدم.

لتجهيز نفس البيئة على أي جهاز:

```bash
powershell -ExecutionPolicy Bypass -File scripts/bootstrap_env.ps1
```

بعدها افتح المشروع في Cursor وسيتم اختيار interpreter الصحيح تلقائيًا من إعدادات الـ workspace.

### تشخيص سريع لمشكلة interpreter

إذا ظهر traceback لمسارات مثل `PythonSoftwareFoundation.Python.3.13` فهذا يعني أنك تشغّل Python النظام بدل بيئة المشروع.

تحقق من interpreter المستخدم:

```bash
python -c "import sys; print(sys.executable)"
```

المسار الصحيح يجب أن يكون داخل المشروع:

- `...\MaestroYoga\.venv\Scripts\python.exe`

أو Stripe الحقيقي:

```bash
set PAYMENT_PROVIDER=stripe
set STRIPE_SECRET_KEY=sk_test_xxx
set STRIPE_WEBHOOK_SECRET=whsec_xxx
```

3) تشغيل تطبيق العميل (Flet):

```bash
python mobile_app/main.py
```

4) صفحات الويب (المتصفح):

- الصفحة العامة (حجز + دفع): [http://127.0.0.1:8000/index?center_id=1](http://127.0.0.1:8000/index?center_id=1)
- تسجيل دخول الإدارة: [http://127.0.0.1:8000/admin/login](http://127.0.0.1:8000/admin/login)  
  (حساب الديمو: `owner@maestroyoga.local` / `Admin@12345`)
  
تهيئة الديمو عبر API أصبحت محمية:

```bash
# من نفس جهاز السيرفر (localhost) يمكن الاستدعاء مباشرة
curl -X POST http://127.0.0.1:8000/seed-demo
```

للنداء من جهاز آخر اضبط في `.env`:

```bash
SEED_DEMO_KEY=replace-with-strong-random-key
```

ثم أرسل الهيدر:

```bash
curl -X POST http://127.0.0.1:8000/seed-demo -H "X-Seed-Demo-Key: replace-with-strong-random-key"
```

## هيكل المشروع

- `backend/app/main.py` - نقاط النهاية الأساسية
- `backend/app/models.py` - نماذج قاعدة البيانات
- `backend/app/schemas.py` - مخططات الإدخال والإخراج
- `backend/app/database.py` - إعداد الاتصال بقاعدة البيانات
- `backend/app/security.py` - JWT + كلمة المرور + الصلاحيات
- `backend/app/payments.py` - طبقة مزود الدفع
- `mobile_app/main.py` - واجهة العميل (موبايل/تابلت)
- `backend/app/web_ui/` - صفحات الويب: `impl_state.py`، `public_routes.py` (يجمع وحدات `public_*`)، `admin_routes.py` (يجمع `admin_auth`، `admin_dashboard`، `admin_org_*`، `admin_center`)، `admin_dashboard_context.py` و`admin_dashboard_blocks.py` (بناء سياق `GET /admin`: غرف/جلسات/مستخدمين/مدفوعات/منشورات، KPI، أمن، ترقيم)، `admin_reports_html.py` (واجهة لـ `admin_reports_html_sessions_revenue`، `insights`، `rest`) مع `admin_reports_*` الأخرى، و`impl.py` يجمّع الـ `router`؛ التصدير من `__init__.py`
- `backend/static/css/admin-dashboard.css` - يستورد `admin-dashboard-reports`، `shell`، `main`، `extras` (التقسيم للصيانة دون تغيير مسار الربط في القوالب)
- `backend/templates/` - قوالب HTML (لوحة الإدارة + الفهرس العام)

## Smoke Checks (سريعة)

للتأكد السريع بعد أي refactor:

```bash
.\.venv\Scripts\python scripts/smoke_backend.py
.\.venv\Scripts\python scripts/smoke_admin.py
.\.venv\Scripts\python scripts/smoke_mobile_api.py
```

اختبارات `pytest` (أنسب للـ CI):

```bash
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
.\.venv\Scripts\python -m pytest -q tests
```

## خارطة التوسع (مثل Mindbody)

- دعم الصلاحيات المتقدمة (مالك مركز، موظف استقبال، مدرب، عميل)
- تكامل حقيقي مع بوابات الدفع
- إشعارات Push و WhatsApp/SMS
- جدول مدربين متقدم + انتظار (waitlist)
- التقارير المالية والتشغيلية
- Marketplace لخدمات إضافية لكل مركز

## Stripe Checkout + Webhook

- أنشئ Checkout Session عبر:
  - `POST /payments/checkout-session`
- Stripe يعيد المستخدم إلى `success_url` أو `cancel_url`.
- Webhook endpoint:
  - `POST /payments/webhook/stripe`
- مثال محلي باستخدام Stripe CLI:

```bash
stripe listen --forward-to http://127.0.0.1:8000/payments/webhook/stripe
```

## سجل المدفوعات في التطبيق

- توجد الآن لوحة تحكم رئيسية في أعلى التطبيق تعرض:
  - عدد العملاء
  - عدد الجلسات
  - عدد الحجوزات
  - عدد الخطط النشطة
  - إيراد اليوم والإيراد الكلي
  - عدد المدفوعات قيد الانتظار
- API الخاص بها:
  - `GET /dashboard/summary`
- واجهة الموبايل تعرض الآن سجل المدفوعات.
- يمكن الفلترة حسب:
  - الحالة (`paid` / `pending` / `failed`)
  - بريد العميل (من حقل البريد نفسه في الشاشة)
- API المستخدم:
  - `GET /payments?client_id=<id>&status=<status>`
- تصدير CSV:
  - من التطبيق: زر `تصدير CSV` (يصدر السجل الحالي إلى مجلد Downloads).
  - من الـ API مباشرة:
    - `GET /payments/export/csv?client_id=<id>&status=<status>`
- تصدير Excel (`.xlsx`):
  - من التطبيق: زر `تصدير Excel` (يصدر السجل الحالي إلى مجلد Downloads).
  - من الـ API مباشرة:
    - `GET /payments/export/xlsx?client_id=<id>&status=<status>`
