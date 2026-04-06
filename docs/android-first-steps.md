# خطوات أولى — تطبيق أندرويد وربطه بـ Maestro Yoga

ما يمكن تجهيزه **داخل المستودع** مقابل ما يبقى عندك في الحسابات الخارجية.

## داخل المستودع (جاهز أو قابل للتوسيع)

| العنصر | الوصف |
|--------|--------|
| **REST تحت `/api/v1`** | نفس المسارات السابقة مع بادئة موحّدة للعميل. |
| **`GET /api/v1/meta`** | نقطة انطلاق: إصدار API وروابط التوثيق. |
| **رؤوس** `X-Request-ID`، `X-API-Version`، `X-App-Version` | للتتبع ومطابقة إصدارات التطبيق. |
| **`android/`** | مشروع **Kotlin** أصلي (Retrofit) يستدعي `/api/v1/meta`؛ زر «فتح وثائق API» يفتح `{API_BASE_URL}/docs` في المتصفح (إن عطّل الخادم الوثائق في الإنتاج فسيظهر 404). راجع [`android/README.md`](../android/README.md). |
| **`scripts/verify_production_readiness.py`** | بعد نشر الخادم، شغّله مع `BASE_URL` للتحقق من الصحة و`/api/v1`. |
| **`scripts/healthcheck_prod.sh`** | فحوصات سريعة من سطر الأوامر (Linux/macOS/Git Bash). |
| **واجهة ويب متجاوبة + manifest** | تجربة «مثل التطبيق» من المتصفح قبل بناء APK. |

## خارج المستودع (لا يُنشَأ تلقائياً من الكود)

- حساب **Google Play Console**، سياسة خصوصية، أيقونات ولقطات، **توقيع التطبيق** (keystore).
- **استضافة** الخادم (مثلاً Render) مع `DATABASE_URL` و`PUBLIC_BASE_URL` وأسرار الدفع/البريد.
- **Gradle Wrapper** (`gradlew` / `gradlew.bat`): يُولَّد تلقائياً عند أول فتح لمشروع **`android/`** في Android Studio (أو عند تشغيل `gradle wrapper` إن وُجد Gradle محلياً).

## ترتيب عملي مقترح

1. انشر الخادم واحصل على **`https://your-domain`** ثابتاً.
2. شغّل: `BASE_URL=https://your-domain py scripts/verify_production_readiness.py`
3. قرّر: **تطبيق أصلي** (يوصى به للمتجر) أو **WebView** للسرعة.
4. أنشئ مشروعاً في Android Studio يستدعي `GET /api/v1/meta` ثم تدفق تسجيل الدخول عبر `/api/v1/auth/login`.

تفاصيل المتغيرات والصيانة: [`operations.md`](operations.md).
