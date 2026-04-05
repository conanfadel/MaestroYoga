# تطبيق أندرويد أصلي — Maestro Yoga

مشروع **Kotlin** يتصل بـ **`GET /api/v1/meta`** عبر Retrofit/OkHttp مع رؤوس **`X-App-Version`** و **`X-Request-ID`**.

## المتطلبات

- [Android Studio](https://developer.android.com/studio) Hedgehog | 2023.1.1 أو أحدث (يدعم Gradle 8 و JDK 17).

## الإعداد

1. افتح المجلد **`android/`** في Android Studio (File → Open).
2. أنشئ **`local.properties`** في مجلد `android/` (أو انسخ من `local.properties.example`):

   ```properties
   MAESTRO_API_BASE_URL=https://your-production-host.com
   ```

   للمحاكي مع خادم يعمل على جهازك على المنفذ 8000:

   ```properties
   MAESTRO_API_BASE_URL=http://10.0.2.2:8000
   ```

3. **Sync Gradle** ثم شغّل على محاكي أو جهاز.

## البناء

- **Debug APK:** Build → Build Bundle(s) / APK(s) → Build APK(s).
- **توقيع الإصدار (Play):** Build → Generate Signed Bundle / APK واتبع معالج المتجر.

## الخطوات التالية للتطوير

- شاشة تسجيل دخول تستدعي `POST /api/v1/auth/login`.
- تخزين الرمز المميز بأمان (مثل EncryptedSharedPreferences).
- استبدال أيقونة `res/drawable/ic_launcher.xml` بأصول متجر حقيقية.

## ملاحظة

`applicationId` الحالي: `com.maestroyoga.app` (و`com.maestroyoga.app.debug` في debug). غيّره قبل النشر النهائي إن لزم.
