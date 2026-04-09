"""Branded HTML fragments for transactional email."""

from __future__ import annotations

import os


def _brand_email_html(
    *,
    app_name: str,
    title: str,
    recipient_name: str,
    intro: str,
    cta_label: str,
    cta_url: str,
    foot_note: str | None = None,
) -> str:
    support_email = os.getenv("SMTP_FROM", "support@maestroyoga.local").strip()
    note_block = ""
    if foot_note:
        note_block = f'<p style="margin:0 0 16px;font-size:13px;color:#475569;line-height:1.65;">{foot_note}</p>'
    return f"""
<div dir="rtl" style="margin:0;background:#f8fafc;padding:24px 12px;">
  <div style="max-width:640px;margin:0 auto;background:#ffffff;border:1px solid #d1fae5;border-radius:14px;overflow:hidden;">
    <div style="padding:18px 22px;background:linear-gradient(135deg,#0f766e,#10b981);color:#ffffff;">
      <div style="font-family:Arial,sans-serif;font-size:12px;opacity:.9;letter-spacing:.8px;text-transform:uppercase;">Maestro Yoga</div>
      <div style="font-family:Arial,sans-serif;font-size:21px;font-weight:700;line-height:1.3;margin-top:4px;">{title}</div>
    </div>
    <div style="padding:22px 22px 16px;font-family:Arial,sans-serif;color:#0f172a;line-height:1.7;">
      <p style="margin:0 0 10px;">مرحبًا {recipient_name}،</p>
      <p style="margin:0 0 16px;">{intro}</p>
      {note_block}
      <p style="margin:0 0 18px;">
        <a href="{cta_url}" style="display:inline-block;background:#0f766e;color:#ffffff;text-decoration:none;padding:11px 18px;border-radius:8px;font-weight:700;">
          {cta_label}
        </a>
      </p>
      <p style="margin:0 0 6px;font-size:13px;color:#475569;">إذا لم يعمل الزر، استخدم هذا الرابط:</p>
      <p style="margin:0 0 14px;font-size:13px;word-break:break-all;"><a href="{cta_url}" style="color:#0f766e;">{cta_url}</a></p>
      <div style="margin-top:14px;padding-top:12px;border-top:1px solid #e2e8f0;font-size:12px;color:#64748b;">
        <div>{app_name}</div>
        <div>الدعم: {support_email}</div>
      </div>
    </div>
  </div>
</div>
""".strip()
