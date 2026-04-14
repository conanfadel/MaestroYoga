# Payment Policy (Post-Checkout)

هذه السياسة معتمدة لتدفق الدفع للحجز والاشتراك في Maestro Yoga.

## 1) مصدر الحقيقة

- **Webhook من مزود الدفع هو مصدر الحقيقة الوحيد** لتغيير حالة العملية إلى نجاح/فشل.
- العودة إلى `success_url` أو `cancel_url` تُستخدم **للعرض فقط**، ولا يجب أن تؤكد الدفع بمفردها.

## 2) حالات البداية قبل الإرسال للبوابة

- الجلسات:
  - `Booking.status = pending_payment`
  - `Payment.status = pending`
- الاشتراك:
  - `ClientSubscription.status = pending`
  - `Payment.status = pending`

## 3) عند النجاح (Webhook Success)

- الجلسات:
  - `Payment -> paid`
  - `Booking -> confirmed`
- الاشتراك:
  - `Payment -> paid`
  - `ClientSubscription -> active`
- إرسال إشعار نجاح (بريد) عند التفعيل.

## 4) عند الرفض/الفشل (Webhook Failure)

- الجلسات:
  - `Payment -> failed`
  - `Booking -> cancelled`
- الاشتراك:
  - `Payment -> failed`
  - `ClientSubscription -> cancelled`

## 5) عند الإلغاء من صفحة الدفع

- الإلغاء في redirect لا يكفي وحده للحسم.
- إن كانت الحالة في DB ما زالت `pending`، تُعرض للمستخدم كـ "بانتظار التأكيد" إلى أن يصل webhook أو تنتهي المهلة.

## 6) المهلات والتنظيف

- أي `pending` قديم يُنظَّف بواسطة sweeper:
  - `PENDING_PAYMENT_EXPIRE_MINUTES`
  - `STALE_PAYMENT_SWEEP_INTERVAL_SEC`
- نتيجة التنظيف:
  - `pending_payment` booking -> `cancelled`
  - `pending` payment -> `failed`

## 7) الحماية من التكرار

- تُستخدم مفاتيح idempotency عند إنشاء checkout sessions.
- دوال التسوية (`finalize_*`) يجب أن تكون آمنة ضد إعادة الاستدعاء (idempotent).

## 8) تجربة المستخدم

- `pending`: "ننتظر إشعار البوابة (Webhook)"
- `failed/cancelled`: "لم يُقبل الدفع / تم الإلغاء"
- `paid`: "تم الدفع بنجاح"

