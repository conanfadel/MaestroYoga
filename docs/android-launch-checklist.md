# قائمة إطلاق سريع — تطبيق العملاء (هجين WebView)

## 1. الخادم

```powershell
cd MaestroYoga
.\.venv\Scripts\python -m uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

تحقق: `http://127.0.0.1:8000/index?center_id=1` و `/public/register`

### تذكيرات بريد (اختياري — cron)

```powershell
python scripts/send_session_reminders.py
```

متغيرات: `SESSION_REMINDER_HOURS=24`، `SMTP_*` أو `MAIL_PROVIDER`، `PUBLIC_BASE_URL`

## 2. Android Studio

1. Open → مجلد `android/`
2. `local.properties`:

```properties
sdk.dir=...
MAESTRO_API_BASE_URL=http://10.0.2.2:8000/
MAESTRO_PUBLIC_HOME_PATH=index?center_id=1
```

3. Run على محاكي — جرّب الشريط السفلي: **الحجز | دخول | تسجيل | حسابي**

## 3. قبل المتجر

- [ ] `MAESTRO_API_BASE_URL` = HTTPS إنتاج
- [ ] أيقونة PNG (استبدال `ic_launcher.xml`)
- [ ] سياسة خصوصية + رابط على المتجر
- [ ] Keystore + Build → Signed APK/AAB
- [ ] جرّب: تسجيل → حجز → دفع → بريد تأكيد

## 4. لاحقاً (بعد الإطلاق)

- Firebase FCM + Push
- API JSON لتسجيل أصلي
- تذكير 2 ساعة + إشعارات داخل التطبيق
