import asyncio
import csv
from datetime import datetime
import os
from pathlib import Path
from typing import Any

import flet as ft
import httpx
from openpyxl import Workbook

API_BASE = "http://127.0.0.1:8000"
SUCCESS_URL = "https://example.com/maestro/success"
CANCEL_URL = "https://example.com/maestro/cancel"


class ApiUnavailableError(Exception):
    pass


async def api_get(path: str, token: str, params: dict[str, Any] | None = None):
    async with httpx.AsyncClient(timeout=20.0) as client:
        try:
            response = await client.get(
                f"{API_BASE}{path}",
                params=params,
                headers={"Authorization": f"Bearer {token}"},
            )
        except httpx.RequestError as exc:
            raise ApiUnavailableError("تعذر الاتصال بخادم Maestro Yoga API") from exc
        if response.status_code >= 400:
            try:
                detail = response.json().get("detail", response.text)
            except Exception:
                detail = response.text
            raise RuntimeError(str(detail))
        return response.json()


async def api_post(
    path: str,
    payload: dict[str, Any],
    token: str | None = None,
    extra_headers: dict[str, str] | None = None,
):
    async with httpx.AsyncClient(timeout=20.0) as client:
        headers: dict[str, str] = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if extra_headers:
            headers.update(extra_headers)
        try:
            response = await client.post(f"{API_BASE}{path}", json=payload, headers=headers or None)
        except httpx.RequestError as exc:
            raise ApiUnavailableError("تعذر الاتصال بخادم Maestro Yoga API") from exc
        if response.status_code >= 400:
            try:
                detail = response.json().get("detail", response.text)
            except Exception:
                detail = response.text
            raise RuntimeError(str(detail))
        return response.json()


def main(page: ft.Page):
    page.title = "Maestro Yoga"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.window_width = 420
    page.window_height = 780
    page.padding = 20

    token: str | None = None
    active_payment_id: int | None = None
    is_polling_payment = False
    latest_payments: list[dict[str, Any]] = []
    dashboard_data: dict[str, Any] = {}
    sessions_column = ft.Column(spacing=12)
    payments_column = ft.Column(spacing=10)
    dashboard_cards = ft.Column(spacing=10)
    client_name = ft.TextField(label="اسم العميل")
    client_email = ft.TextField(label="البريد الإلكتروني")
    session_id_field = ft.TextField(label="رقم الجلسة للحجز")
    drop_in_amount = ft.TextField(label="مبلغ الدفع", value="60")
    payment_status_filter = ft.Dropdown(
        label="فلترة الحالة",
        value="all",
        options=[
            ft.dropdown.Option("all", "الكل"),
            ft.dropdown.Option("paid", "مدفوع"),
            ft.dropdown.Option("pending", "قيد الانتظار"),
            ft.dropdown.Option("failed", "فاشل"),
        ],
    )
    status_text = ft.Text("")
    reconnect_button = ft.ElevatedButton(
        "إعادة الاتصال بالخادم",
        visible=False,
        on_click=lambda _: asyncio.create_task(init()),
    )

    def metric_card(title: str, value: str, color: str = ft.Colors.BLUE_50) -> ft.Container:
        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Text(title, size=12, color=ft.Colors.GREY_700),
                    ft.Text(value, size=20, weight=ft.FontWeight.BOLD),
                ],
                spacing=4,
            ),
            padding=12,
            border_radius=12,
            bgcolor=color,
            border=ft.border.all(1, ft.Colors.GREY_300),
        )

    async def wait_for_api(max_attempts: int = 6, delay_seconds: int = 2) -> bool:
        for _ in range(max_attempts):
            try:
                await api_get("/", token="")
                return True
            except Exception:
                await asyncio.sleep(delay_seconds)
        return False

    async def ensure_demo_data():
        seed_key = os.getenv("SEED_DEMO_KEY", "").strip()
        headers = {"X-Seed-Demo-Key": seed_key} if seed_key else None
        try:
            await api_post("/seed-demo", {}, extra_headers=headers)
            return
        except ApiUnavailableError:
            raise
        except Exception:
            # Seed endpoint errors (forbidden, unavailable, etc.) should not stop app startup.
            return

    async def login_demo_owner():
        nonlocal token
        auth = await api_post(
            "/auth/login",
            {"email": "owner@maestroyoga.local", "password": "Admin@12345"},
        )
        token = auth["access_token"]

    async def load_sessions():
        if not token:
            status_text.value = "المصادقة غير جاهزة بعد"
            page.update()
            return
        sessions_column.controls.clear()
        try:
            data = await api_get("/sessions", token=token)
            if not data:
                sessions_column.controls.append(ft.Text("لا توجد جلسات حاليا"))
            else:
                for item in data:
                    sessions_column.controls.append(
                        ft.Container(
                            content=ft.Column(
                                controls=[
                                    ft.Text(f"#{item['id']} - {item['title']}", weight=ft.FontWeight.BOLD),
                                    ft.Text(f"المدرب: {item['trainer_name']}"),
                                    ft.Text(f"المستوى: {item['level']}"),
                                    ft.Text(f"السعر: {item['price_drop_in']} SAR"),
                                    ft.Text(f"الوقت: {item['starts_at']}"),
                                ],
                                spacing=4,
                            ),
                            border=ft.border.all(1, ft.Colors.GREY_300),
                            border_radius=12,
                            padding=12,
                        )
                    )
        except Exception as exc:
            sessions_column.controls.append(ft.Text(f"خطأ في تحميل الجلسات: {exc}"))
        page.update()

    async def load_dashboard():
        nonlocal dashboard_data
        if not token:
            return
        dashboard_cards.controls.clear()
        try:
            dashboard_data = await api_get("/dashboard/summary", token=token)
            row_1 = ft.Row(
                controls=[
                    metric_card("العملاء", str(dashboard_data.get("clients_count", 0))),
                    metric_card("الجلسات", str(dashboard_data.get("sessions_count", 0))),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            )
            row_2 = ft.Row(
                controls=[
                    metric_card("الحجوزات", str(dashboard_data.get("bookings_count", 0))),
                    metric_card("الخطط النشطة", str(dashboard_data.get("active_plans_count", 0))),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            )
            row_3 = ft.Row(
                controls=[
                    metric_card("إيراد اليوم", f"{dashboard_data.get('revenue_today', 0):.2f} SAR", ft.Colors.GREEN_50),
                    metric_card("إيراد إجمالي", f"{dashboard_data.get('revenue_total', 0):.2f} SAR", ft.Colors.AMBER_50),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            )
            row_4 = ft.Row(
                controls=[
                    metric_card("مدفوعات قيد الانتظار", str(dashboard_data.get("pending_payments_count", 0)), ft.Colors.ORANGE_50),
                ]
            )
            dashboard_cards.controls.extend([row_1, row_2, row_3, row_4])
        except Exception as exc:
            dashboard_cards.controls.append(ft.Text(f"تعذر تحميل لوحة التحكم: {exc}"))
        page.update()

    async def register_and_book(_):
        if not token:
            status_text.value = "المصادقة غير جاهزة بعد"
            page.update()
            return
        if not client_name.value or not client_email.value or not session_id_field.value:
            status_text.value = "يرجى تعبئة الاسم والإيميل ورقم الجلسة"
            page.update()
            return
        try:
            client = await api_post(
                "/clients",
                {
                    "full_name": client_name.value,
                    "email": client_email.value,
                    "phone": "",
                },
                token=token,
            )
            booking = await api_post(
                "/bookings",
                {
                    "session_id": int(session_id_field.value),
                    "client_id": client["id"],
                },
                token=token,
            )
            status_text.value = f"تم الحجز بنجاح. رقم الحجز: {booking['id']}"
            await load_dashboard()
        except Exception as exc:
            status_text.value = f"تعذر تنفيذ الحجز: {exc}"
        page.update()

    async def pay_in_app(_):
        nonlocal active_payment_id, is_polling_payment
        if not token:
            status_text.value = "المصادقة غير جاهزة بعد"
            page.update()
            return
        if not client_name.value or not client_email.value:
            status_text.value = "أنشئ عميل أولا عبر الحجز"
            page.update()
            return
        try:
            clients = await api_get("/clients", token=token)
            match = next(
                (c for c in clients if c["email"].lower() == client_email.value.lower()),
                None,
            )
            if not match:
                status_text.value = "العميل غير موجود، قم بالحجز أولا"
                page.update()
                return

            amount = float(drop_in_amount.value)

            try:
                checkout = await api_post(
                    "/payments/checkout-session",
                    {
                        "client_id": match["id"],
                        "amount": amount,
                        "currency": "sar",
                        "success_url": SUCCESS_URL,
                        "cancel_url": CANCEL_URL,
                    },
                    token=token,
                )
                active_payment_id = checkout["payment_id"]
                status_text.value = "تم فتح صفحة الدفع، جاري انتظار تأكيد العملية..."
                page.launch_url(checkout["checkout_url"])
                page.update()

                if not is_polling_payment:
                    is_polling_payment = True
                    asyncio.create_task(poll_payment_status())
            except Exception:
                # Fallback for mock provider.
                payment = await api_post(
                    "/payments",
                    {
                        "client_id": match["id"],
                        "amount": amount,
                        "currency": "SAR",
                        "payment_method": "in_app_mock",
                    },
                    token=token,
                )
                status_text.value = f"تم الدفع بنجاح. المرجع: {payment['provider_ref']}"
                await load_dashboard()
        except Exception as exc:
            status_text.value = f"فشل الدفع: {exc}"
        page.update()

    async def poll_payment_status():
        nonlocal active_payment_id, is_polling_payment
        try:
            for _ in range(24):  # around 2 minutes
                if not token or not active_payment_id:
                    return
                payment = await api_get(f"/payments/{active_payment_id}", token=token)
                current_status = payment.get("status", "unknown")
                if current_status == "paid":
                    status_text.value = f"تم تأكيد الدفع بنجاح. المرجع: {payment.get('provider_ref', '-')}"
                    await load_dashboard()
                    await load_payments()
                    page.update()
                    active_payment_id = None
                    return
                if current_status == "failed":
                    status_text.value = "فشلت عملية الدفع أو انتهت صلاحية الجلسة"
                    page.update()
                    active_payment_id = None
                    return
                status_text.value = "بانتظار تأكيد الدفع من Stripe..."
                page.update()
                await asyncio.sleep(5)
            status_text.value = "لم يصل تأكيد الدفع بعد. يمكنك إعادة التحقق لاحقا."
            page.update()
        finally:
            is_polling_payment = False

    async def load_payments():
        nonlocal latest_payments
        if not token:
            status_text.value = "المصادقة غير جاهزة بعد"
            page.update()
            return
        payments_column.controls.clear()
        try:
            client_id_filter = None
            if client_email.value:
                clients = await api_get("/clients", token=token)
                match = next(
                    (c for c in clients if c["email"].lower() == client_email.value.lower()),
                    None,
                )
                if match:
                    client_id_filter = match["id"]
                else:
                    payments_column.controls.append(ft.Text("لا يوجد عميل مطابق للبريد الإلكتروني"))
                    page.update()
                    return

            params: dict[str, Any] = {}
            if client_id_filter is not None:
                params["client_id"] = client_id_filter
            if payment_status_filter.value and payment_status_filter.value != "all":
                params["status"] = payment_status_filter.value

            payments = await api_get("/payments", token=token, params=params)
            latest_payments = payments
            if not payments:
                payments_column.controls.append(ft.Text("لا توجد مدفوعات حسب الفلاتر الحالية"))
            else:
                for item in payments:
                    payments_column.controls.append(
                        ft.Container(
                            content=ft.Column(
                                controls=[
                                    ft.Text(
                                        f"دفعة #{item['id']} - {item['amount']} {item['currency']}",
                                        weight=ft.FontWeight.BOLD,
                                    ),
                                    ft.Text(f"الحالة: {item['status']}"),
                                    ft.Text(f"الطريقة: {item['payment_method']}"),
                                    ft.Text(f"المرجع: {item.get('provider_ref') or '-'}"),
                                    ft.Text(f"وقت الدفع: {item['paid_at']}"),
                                ],
                                spacing=3,
                            ),
                            border=ft.border.all(1, ft.Colors.GREY_300),
                            border_radius=12,
                            padding=10,
                        )
                    )
        except Exception as exc:
            latest_payments = []
            payments_column.controls.append(ft.Text(f"تعذر تحميل المدفوعات: {exc}"))
        page.update()

    async def export_payments_csv(_):
        if not latest_payments:
            status_text.value = "لا توجد بيانات مدفوعات للتصدير"
            page.update()
            return
        try:
            downloads_dir = Path.home() / "Downloads"
            downloads_dir.mkdir(parents=True, exist_ok=True)
            filename = f"maestro_payments_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            target = downloads_dir / filename

            with target.open("w", newline="", encoding="utf-8-sig") as file:
                writer = csv.writer(file)
                writer.writerow(
                    [
                        "payment_id",
                        "center_id",
                        "client_id",
                        "amount",
                        "currency",
                        "payment_method",
                        "provider_ref",
                        "status",
                        "paid_at",
                    ]
                )
                for item in latest_payments:
                    writer.writerow(
                        [
                            item.get("id", ""),
                            item.get("center_id", ""),
                            item.get("client_id", ""),
                            item.get("amount", ""),
                            item.get("currency", ""),
                            item.get("payment_method", ""),
                            item.get("provider_ref", ""),
                            item.get("status", ""),
                            item.get("paid_at", ""),
                        ]
                    )
            status_text.value = f"تم تصدير CSV بنجاح: {target}"
        except Exception as exc:
            status_text.value = f"فشل تصدير CSV: {exc}"
        page.update()

    async def export_payments_xlsx(_):
        if not latest_payments:
            status_text.value = "لا توجد بيانات مدفوعات للتصدير"
            page.update()
            return
        try:
            downloads_dir = Path.home() / "Downloads"
            downloads_dir.mkdir(parents=True, exist_ok=True)
            filename = f"maestro_payments_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
            target = downloads_dir / filename

            workbook = Workbook()
            sheet = workbook.active
            sheet.title = "Payments"
            sheet.append(
                [
                    "payment_id",
                    "center_id",
                    "client_id",
                    "amount",
                    "currency",
                    "payment_method",
                    "provider_ref",
                    "status",
                    "paid_at",
                ]
            )
            for item in latest_payments:
                sheet.append(
                    [
                        item.get("id", ""),
                        item.get("center_id", ""),
                        item.get("client_id", ""),
                        item.get("amount", ""),
                        item.get("currency", ""),
                        item.get("payment_method", ""),
                        item.get("provider_ref", ""),
                        item.get("status", ""),
                        item.get("paid_at", ""),
                    ]
                )
            workbook.save(target)
            status_text.value = f"تم تصدير Excel بنجاح: {target}"
        except Exception as exc:
            status_text.value = f"فشل تصدير Excel: {exc}"
        page.update()

    async def init():
        reconnect_button.visible = False
        status_text.value = "جاري الاتصال بخادم Maestro Yoga..."
        page.update()

        is_api_ready = await wait_for_api()
        if not is_api_ready:
            status_text.value = (
                "الخادم غير متاح. شغّل API بالأمر:\n"
                "uvicorn backend.app.main:app --reload"
            )
            reconnect_button.visible = True
            page.update()
            return

        try:
            await ensure_demo_data()
            await login_demo_owner()
            await load_dashboard()
            await load_sessions()
            await load_payments()
            status_text.value = "تم الاتصال بالخادم بنجاح"
        except ApiUnavailableError:
            status_text.value = (
                "تعذر الاتصال بالخادم أثناء التهيئة. تأكد أن API يعمل ثم اضغط إعادة الاتصال."
            )
            reconnect_button.visible = True
        except Exception as exc:
            status_text.value = f"حدث خطأ أثناء التهيئة: {exc}"
            reconnect_button.visible = True
        page.update()

    page.add(
        ft.Text("Maestro Yoga", size=28, weight=ft.FontWeight.BOLD),
        ft.Text("احجز جلساتك وادفع من داخل التطبيق", color=ft.Colors.GREY_700),
        ft.Divider(),
        ft.Row(
            controls=[
                ft.Text("لوحة التحكم الرئيسية", weight=ft.FontWeight.BOLD),
                ft.OutlinedButton("تحديث اللوحة", on_click=lambda _: asyncio.create_task(load_dashboard())),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        ),
        dashboard_cards,
        ft.Divider(),
        ft.Row(
            controls=[
                ft.ElevatedButton("تحديث الجلسات", on_click=lambda _: asyncio.create_task(load_sessions())),
            ]
        ),
        ft.Text("الجلسات المتاحة", weight=ft.FontWeight.BOLD),
        sessions_column,
        ft.Divider(),
        ft.Text("الحجز", weight=ft.FontWeight.BOLD),
        client_name,
        client_email,
        session_id_field,
        ft.ElevatedButton("تسجيل عميل + حجز جلسة", on_click=lambda e: asyncio.create_task(register_and_book(e))),
        ft.Divider(),
        ft.Text("الدفع داخل التطبيق", weight=ft.FontWeight.BOLD),
        drop_in_amount,
        ft.ElevatedButton("دفع", on_click=lambda e: asyncio.create_task(pay_in_app(e))),
        ft.Divider(),
        ft.Text("سجل المدفوعات", weight=ft.FontWeight.BOLD),
        payment_status_filter,
        ft.Row(
            controls=[
                ft.ElevatedButton("تحديث سجل المدفوعات", on_click=lambda _: asyncio.create_task(load_payments())),
                ft.OutlinedButton("تصدير CSV", on_click=lambda e: asyncio.create_task(export_payments_csv(e))),
                ft.OutlinedButton("تصدير Excel", on_click=lambda e: asyncio.create_task(export_payments_xlsx(e))),
            ]
        ),
        payments_column,
        reconnect_button,
        status_text,
    )

    asyncio.create_task(init())


if __name__ == "__main__":
    ft.app(target=main)
