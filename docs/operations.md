# تشغيل Maestro Yoga — إنتاج، جوال، وألواح ذكية

## متغيرات بيئة مفيدة

| المتغير | الوصف |
|--------|--------|
| `MAINTENANCE_MODE` | عند `1` أو `true`: تعطيل الواجهة للمستخدمين مع الإبقاء على `/health` و`/health/ready` و`/static/*` ومسارات webhook الدفع (`/payments/webhook/*`). يُعاد `503` مع `Retry-After`. |
| `CORS_ORIGINS` | قائمة مفصولة بفواصل لأصول مسموح بها (مثال: `https://app.example.com,https://www.example.com`). مطلوبة إذا كان **متصفح** أو **WebView** يستدعي الـ API من نطاق مختلف. تطبيق أندرويد أصلي (OkHttp) لا يخضع لـ CORS. |
| `LOG_LEVEL` | مستوى السجل الافتراضي للخادم (مثل `INFO`, `WARNING`). |
| `PUBLIC_BASE_URL` | قاعدة الروابط العامة (تحقق بريد، دفع، روابط إشعارات). |

المسار الافتراضي للصفحة العامة مُعرَّف في الكود كـ `PUBLIC_INDEX_DEFAULT_PATH` في `backend/app/web_shared.py` (ليس متغير بيئة).

كل استجابة HTTP تتضمن الرأس **`X-Request-ID`** (أو يُعاد استخدام **`X-Request-ID`** / **`X-Correlation-ID`** القادم من العميل). **يُنصح** بتمريره في سجلات تطبيق أندرويد عند الإبلاغ عن أخطاء.

### واجهة REST موحّدة (`/api/v1`)

- جميع مسارات JSON التي كانت على الجذر (مثل `/health`، `/auth/login`، `/sessions`، …) متاحة أيضاً تحت البادئة **`/api/v1`** (مثال: **`GET /api/v1/health`**، **`POST /api/v1/auth/login`**).
- **`GET /api/v1/meta`**: معلومات إصدار الـ API وروابط OpenAPI — نقطة انطلاق مناسبة لتطبيق أندرويد.
- مسارات **webhook** الدفع (`/payments/webhook/stripe` و `/payments/webhook/moyasar`) تبقى **بدون** تكرار تحت `/api/v1` لأن مزودي الدفع يُعدّون عناوين ثابتة.
- الرؤوس **`X-API-Version: 1`** و **`X-App-Version-Accepted`** (عند إرسال **`X-App-Version`** من العميل) تساعد على مطابقة إصدارات التطبيق والخادم.

## مسارات الصحة

- **`GET /health`**: خفيف، بدون قاعدة بيانات — مناسب لـ load balancer سريع.
- **`GET /health/ready`**: يتحقق من اتصال قاعدة البيانات — استخدمه بعد النشر أو في فحوصات أعمق.

## الويب كتطبيق على الهاتف والتابلت

- تمت إضافة **`manifest.json`** و**`viewport-fit=cover`** و**`theme-color`** ودعم **مناطق الشاشة الآمنة** (`safe-area-inset-*`) لتقليل التداخل مع الشقوق والزوايا المستديرة.
- يمكن للمستخدمين «**إضافة إلى الشاشة الرئيسية**» من المتصفح (Chrome على أندرويد / Safari على iOS) كاختصار يشبه التطبيق.
- لتطبيق أندرويد أصلي لاحقاً: استخدم نفس الـ API مع **HTTPS**؛ خزّن الرمز المميز بأمان (EncryptedSharedPreferences / Keystore) ولا تضع أسرار الخادم في التطبيق.

## السكربتات

- `scripts/healthcheck_prod.sh`: يفحص `/` و`/admin/login` و`/health/ready` والصفحة العامة بعد ضبط `BASE_URL`.
- `scripts/verify_production_readiness.py`: يتحقق من `/health`، `/health/ready`، `/api/v1/health`، `/api/v1/meta` ورؤوس `X-API-Version` / `X-App-Version` (يتطلب `httpx`). مثال: `BASE_URL=https://your-host py scripts/verify_production_readiness.py`

## أول خطوات تطبيق أندرويد

- ملخص عملي: [`android-first-steps.md`](android-first-steps.md).

## CI

- يعمل سير عمل GitHub Actions في `.github/workflows/ci.yml` على تشغيل `pytest` عند الدفع وطلبات الدمج.
