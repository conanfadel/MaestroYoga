# خطوات أولى — تطبيق أندرويد (واجهة المستخدمين)

## الهدف

تطبيق المتجر = **تجربة العملاء** (حجز، اشتراك، حساب). **لوحة الإدارة** تبقى على الويب.

## جاهز في المستودع

| العنصر | الوصف |
|--------|--------|
| **`android/`** | هجين: WebView + شريط **حجز · دخول · تسجيل · حسابي** — [`android-launch-checklist.md`](android-launch-checklist.md) |
| **واجهة ويب عامة** | `/index`, `/public/register`, `/public/login` — داخل التطبيق |
| **`scripts/send_session_reminders.py`** | تذكير بريد ~24 ساعة قبل الجلسة (cron) |
| **`scripts/verify_production_readiness.py`** | تحقق من الخادم بعد النشر |

## البدء في Android Studio

1. انشر الخادم أو شغّله محلياً على المنفذ 8000.
2. افتح مجلد **`android/`** في Android Studio.
3. أنشئ `local.properties` كما في [`android/README.md`](../android/README.md).
4. Run على محاكي — العنوان `10.0.2.2` = `localhost` على جهازك.

## محاكي + خادم محلي

```
MAESTRO_API_BASE_URL=http://10.0.2.2:8000/
MAESTRO_PUBLIC_HOME_PATH=index?center_id=1
```

تأكد أن بيانات العرض التوضيحية موجودة (`ensure_demo_data`) وأن `center_id=1` صالح.

## إنتاج

```
MAESTRO_API_BASE_URL=https://your-domain.com/
MAESTRO_PUBLIC_HOME_PATH=index?center_id=YOUR_CENTER_ID
```

ثم:

```bash
BASE_URL=https://your-domain.com python scripts/verify_production_readiness.py
```

## خارطة طريق

| المرحلة | المحتوى |
|---------|---------|
| **الآن** | WebView = نفس الموقع، أسرع إطلاق |
| **لاحقاً** | API JSON للعملاء + شاشات Compose أصلية |
| **خارج Git** | Play Console، keystore، سياسة خصوصية |

تفاصيل التشغيل: [`operations.md`](operations.md).
