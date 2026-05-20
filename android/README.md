# تطبيق أندرويد — واجهة المستخدمين (Maestro Yoga)

تطبيق **Kotlin هجين** للعملاء: **WebView** لصفحات الموقع (حجز، دفع، تسجيل) + **شريط تنقل أصلي** (حجز · دخول · تسجيل · حسابي). لوحة الإدارة ليست جزءاً من هذا التطبيق.

## المتطلبات

- [Android Studio](https://developer.android.com/studio) Hedgehog (2023.1.1) أو أحدث
- JDK 17

## فتح المشروع

1. **File → Open** واختر المجلد **`android/`** (وليس جذر MaestroYoga بالكامل).
2. انتظر **Sync Gradle** (يُنشئ `gradlew` تلقائياً عند الحاجة).
3. أنشئ **`android/local.properties`** (انسخ من `local.properties.example`):

```properties
sdk.dir=C\:\\Users\\YOUR_USER\\AppData\\Local\\Android\\Sdk
MAESTRO_API_BASE_URL=http://10.0.2.2:8000
MAESTRO_PUBLIC_HOME_PATH=index?center_id=1
```

| المتغير | المعنى |
|---------|--------|
| `MAESTRO_API_BASE_URL` | عنوان الخادم مع `/` في النهاية (مثال محاكي: `http://10.0.2.2:8000/`) |
| `MAESTRO_PUBLIC_HOME_PATH` | مسار الواجهة العامة بدون `/` أولى (افتراضي: `index?center_id=1`) |

4. شغّل الخادم محلياً (مثال): `uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000`
5. **Run** على محاكي — أيقونة **«Maestro Yoga»** → واجهة الحجز مع شريط سفلي للتنقل السريع.

قائمة إطلاق: [`docs/android-launch-checklist.md`](../docs/android-launch-checklist.md)

## بناء Debug / Release

- **APK:** Build → Build Bundle(s) / APK(s) → Build APK(s)
- **توقيع Play:** Build → Generate Signed Bundle / APK

`applicationId`: `com.maestroyoga.app` (وفي debug: `com.maestroyoga.app.debug`)

## شاشة التطوير (REST إدارة)

في بناء **debug** تظهر أيقونة ثانية **«Maestro API (تطوير)»** لاختبار `GET /api/v1/meta` وتسجيل دخول **موظفي** لوحة الإدارة — لا تستخدمها للعملاء.

## الخطوات التالية

1. تجربة كاملة: تسجيل عميل، حجز جلسة، دفع (من WebView).
2. لاحقاً: REST JSON للعملاء (`/api/v1/public/...`) وشاشات أصلية بدل WebView.
3. أيقونة ولقطات متجر، سياسة خصوصية، keystore للنشر.

راجع أيضاً: [`docs/android-first-steps.md`](../docs/android-first-steps.md)
