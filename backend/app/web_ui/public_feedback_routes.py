"""Public feedback form POST (issues / suggestions to admin email)."""

from __future__ import annotations

from fastapi import APIRouter

from . import impl_state as _s


def register_public_feedback_routes(router: APIRouter) -> None:
    @router.post("/public/feedback")
    async def public_feedback_submit(
        request: _s.Request,
        center_id: int = _s.Form(1),
        category: str = _s.Form(...),
        message: str = _s.Form(...),
        contact_name: str = _s.Form(""),
        contact_phone: str = _s.Form(""),
        images: list[_s.UploadFile] | None = _s.File(None),
        db: _s.Session = _s.Depends(_s.get_db),
    ):
        """إرسال مشكلة / شكوى / اقتراح من الواجهة العامة إلى بريد الإدارة (مع صور اختيارية)."""
        pu = _s._current_public_user(request, db)
        if not pu:
            return _s.redirect_public_index_with_params(center_id=center_id, msg="feedback_auth_required")

        dest = _s.feedback_destination_email()
        ok_cfg, _why = _s.validate_mailer_settings()
        if not dest or not ok_cfg:
            return _s.redirect_public_index_with_params(center_id=center_id, msg="feedback_unavailable")

        center = _s.get_seeded_center_or_404(db, center_id)
        app_name = _s.os.getenv("APP_NAME", "Maestro Yoga")
        prepared, prepare_error = await _s.prepare_feedback_submission(
            request=request,
            center_id=center_id,
            center_name=center.name,
            category=category,
            message=message,
            contact_name=contact_name,
            contact_phone=contact_phone,
            account_email=pu.email,
            images=images,
            category_labels=_s.PUBLIC_FEEDBACK_CATEGORY_LABELS,
            allowed_image_types=_s.PUBLIC_FEEDBACK_ALLOWED_IMAGE_TYPES,
            max_image_bytes=_s.PUBLIC_FEEDBACK_MAX_IMAGE_BYTES,
            max_images=_s.PUBLIC_FEEDBACK_MAX_IMAGES,
            max_lockout_seconds=_s.MAX_LOCKOUT_SECONDS,
            request_key_fn=_s._request_key,
            allow_fn=_s.rate_limiter.allow,
            log_security_event_fn=_s.log_security_event,
            client_ip_fn=_s.get_client_ip,
            app_name=app_name,
            is_valid_message_fn=_s.is_valid_feedback_message,
            is_valid_contact_name_fn=_s.is_valid_feedback_contact_name,
            is_valid_email_fn=_s.is_valid_feedback_email,
        )
        if prepare_error:
            return _s.redirect_public_index_with_params(center_id=center_id, msg=prepare_error)
        assert prepared is not None

        sent_ok, send_reason = _s.send_mail_with_attachments(
            dest,
            prepared["subject"],
            prepared["body"],
            html_body=prepared["html_body"],
            attachments=prepared["attachments"] or None,
        )
        result_msg = _s.feedback_send_result_message(
            sent_ok=sent_ok,
            send_reason=send_reason,
            request=request,
            email=prepared["email"],
            log_security_event_fn=_s.log_security_event,
        )
        return _s.redirect_public_index_with_params(center_id=center_id, msg=result_msg)
