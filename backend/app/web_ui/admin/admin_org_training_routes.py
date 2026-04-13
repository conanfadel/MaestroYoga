"""Admin org: training-exercise management by muscle group."""

from __future__ import annotations

from fastapi import APIRouter

from .. import impl_state as _s


def _normalize_muscle_key(raw: str) -> str:
    key = (raw or "").strip().lower()
    if key in _s.TRAINING_MUSCLE_KEY_SET:
        return key
    return "core"


def register_admin_org_training_routes(router: APIRouter) -> None:
    """Manage training exercises assigned to target muscles."""

    @router.post("/admin/training/exercises/add")
    def admin_add_training_exercise(
        muscle_key: str = _s.Form(...),
        exercise_name: str = _s.Form(...),
        notes: str = _s.Form(""),
        training_client_q: str = _s.Form(""),
        training_client_id: int = _s.Form(0),
        scroll_y: str = _s.Form(default=""),
        return_section: str = _s.Form("section-training-management"),
        db: _s.Session = _s.Depends(_s.get_db),
        user: _s.models.User = _s.Depends(
            _s.require_permissions_cookie_or_bearer("sessions.manage")
        ),
    ):
        cid = _s.require_user_center_id(user)
        normalized_muscle = _normalize_muscle_key(muscle_key)
        name_clean = (exercise_name or "").strip()[:180]
        notes_clean = (notes or "").strip()[:3000]
        if not name_clean:
            return _s._admin_redirect(
                _s.ADMIN_MSG_TRAINING_EXERCISE_INVALID,
                scroll_y,
                return_section,
            )
        row = _s.models.TrainingExercise(
            center_id=cid,
            muscle_key=normalized_muscle,
            exercise_name=name_clean,
            notes=notes_clean or None,
        )
        db.add(row)
        db.commit()
        return _s.RedirectResponse(
            url=_s._url_with_params(
                "/admin",
                msg=_s.ADMIN_MSG_TRAINING_EXERCISE_ADDED,
                scroll_y=scroll_y,
                training_muscle=normalized_muscle,
                training_client_q=(training_client_q or "").strip(),
                training_client_id=str(max(0, int(training_client_id or 0))),
            )
            + "#section-training-management",
            status_code=303,
        )

    @router.post("/admin/training/exercises/delete")
    def admin_delete_training_exercise(
        exercise_id: int = _s.Form(...),
        muscle_key: str = _s.Form("core"),
        training_client_q: str = _s.Form(""),
        training_client_id: int = _s.Form(0),
        scroll_y: str = _s.Form(default=""),
        return_section: str = _s.Form("section-training-management"),
        db: _s.Session = _s.Depends(_s.get_db),
        user: _s.models.User = _s.Depends(
            _s.require_permissions_cookie_or_bearer("sessions.manage")
        ),
    ):
        cid = _s.require_user_center_id(user)
        normalized_muscle = _normalize_muscle_key(muscle_key)
        row = db.get(_s.models.TrainingExercise, exercise_id)
        if not row or row.center_id != cid:
            return _s._admin_redirect(
                _s.ADMIN_MSG_TRAINING_EXERCISE_NOT_FOUND, scroll_y, return_section
            )
        db.delete(row)
        db.commit()
        return _s.RedirectResponse(
            url=_s._url_with_params(
                "/admin",
                msg=_s.ADMIN_MSG_TRAINING_EXERCISE_DELETED,
                scroll_y=scroll_y,
                training_muscle=normalized_muscle,
                training_client_q=(training_client_q or "").strip(),
                training_client_id=str(max(0, int(training_client_id or 0))),
            )
            + "#section-training-management",
            status_code=303,
        )

    @router.post("/admin/training/exercises/seed-yoga")
    def admin_seed_yoga_exercises(
        training_muscle: str = _s.Form("core"),
        training_client_q: str = _s.Form(""),
        training_client_id: int = _s.Form(0),
        scroll_y: str = _s.Form(default=""),
        db: _s.Session = _s.Depends(_s.get_db),
        user: _s.models.User = _s.Depends(
            _s.require_permissions_cookie_or_bearer("sessions.manage")
        ),
    ):
        cid = _s.require_user_center_id(user)
        existing_rows = (
            db.query(_s.models.TrainingExercise.muscle_key, _s.models.TrainingExercise.exercise_name)
            .filter(_s.models.TrainingExercise.center_id == cid)
            .all()
        )
        existing_pairs = {
            (
                (mk or "").strip().lower(),
                (nm or "").strip().lower(),
            )
            for mk, nm in existing_rows
            if (mk or "").strip() and (nm or "").strip()
        }
        for muscle_key, ex_list in _s.YOGA_EXERCISES_BY_MUSCLE.items():
            if muscle_key not in _s.TRAINING_MUSCLE_KEY_SET:
                continue
            for ex in ex_list:
                ex_name = (ex.get("name") or "").strip()[:180]
                ex_notes = (ex.get("notes") or "").strip()[:3000]
                if not ex_name:
                    continue
                pair = (muscle_key, ex_name.lower())
                if pair in existing_pairs:
                    continue
                db.add(
                    _s.models.TrainingExercise(
                        center_id=cid,
                        muscle_key=muscle_key,
                        exercise_name=ex_name,
                        notes=ex_notes or None,
                    )
                )
                existing_pairs.add(pair)
        db.commit()
        return _s.RedirectResponse(
            url=_s._url_with_params(
                "/admin",
                msg=_s.ADMIN_MSG_TRAINING_YOGA_SEEDED,
                scroll_y=scroll_y,
                training_muscle=_normalize_muscle_key(training_muscle),
                training_client_q=(training_client_q or "").strip(),
                training_client_id=str(max(0, int(training_client_id or 0))),
            )
            + "#section-training-management",
            status_code=303,
        )

    @router.post("/admin/training/assignments/create")
    def admin_create_training_assignment(
        client_id: int = _s.Form(...),
        selected_exercise_ids: list[int] = _s.Form(default=[]),
        title: str = _s.Form(""),
        notes: str = _s.Form(""),
        starts_at: str = _s.Form(""),
        ends_at: str = _s.Form(""),
        sets_count: int = _s.Form(3),
        reps_text: str = _s.Form("10-12"),
        duration_minutes: int = _s.Form(0),
        rest_seconds: int = _s.Form(60),
        intensity_text: str = _s.Form("متوسط"),
        training_muscle: str = _s.Form("core"),
        training_client_q: str = _s.Form(""),
        scroll_y: str = _s.Form(default=""),
        db: _s.Session = _s.Depends(_s.get_db),
        user: _s.models.User = _s.Depends(
            _s.require_permissions_cookie_or_bearer("sessions.manage")
        ),
    ):
        cid = _s.require_user_center_id(user)
        selected_ids: list[int] = []
        for raw_id in selected_exercise_ids:
            try:
                v = int(raw_id)
            except (TypeError, ValueError):
                continue
            if v > 0:
                selected_ids.append(v)
        if client_id <= 0 or not selected_ids:
            return _s.RedirectResponse(
                url=_s._url_with_params(
                    "/admin",
                    msg=_s.ADMIN_MSG_TRAINING_ASSIGNMENT_INVALID,
                    scroll_y=scroll_y,
                    training_muscle=_normalize_muscle_key(training_muscle),
                    training_client_q=(training_client_q or "").strip(),
                    training_client_id=str(max(0, int(client_id or 0))),
                )
                + "#section-training-management",
                status_code=303,
            )
        client = (
            db.query(_s.models.Client)
            .filter(_s.models.Client.id == client_id, _s.models.Client.center_id == cid)
            .first()
        )
        if not client:
            return _s.RedirectResponse(
                url=_s._url_with_params(
                    "/admin",
                    msg=_s.ADMIN_MSG_TRAINING_ASSIGNMENT_INVALID,
                    scroll_y=scroll_y,
                    training_muscle=_normalize_muscle_key(training_muscle),
                    training_client_q=(training_client_q or "").strip(),
                    training_client_id=str(max(0, int(client_id or 0))),
                )
                + "#section-training-management",
                status_code=303,
            )
        exercise_rows = (
            db.query(_s.models.TrainingExercise)
            .filter(
                _s.models.TrainingExercise.center_id == cid,
                _s.models.TrainingExercise.id.in_(selected_ids),
            )
            .order_by(_s.models.TrainingExercise.id.asc())
            .all()
        )
        if not exercise_rows:
            return _s.RedirectResponse(
                url=_s._url_with_params(
                    "/admin",
                    msg=_s.ADMIN_MSG_TRAINING_ASSIGNMENT_INVALID,
                    scroll_y=scroll_y,
                    training_muscle=_normalize_muscle_key(training_muscle),
                    training_client_q=(training_client_q or "").strip(),
                    training_client_id=str(max(0, int(client_id or 0))),
                )
                + "#section-training-management",
                status_code=303,
            )
        start_dt = _s._parse_optional_date_str(starts_at)
        end_dt = _s._parse_optional_date_str(ends_at)
        if start_dt and end_dt and end_dt < start_dt:
            return _s.RedirectResponse(
                url=_s._url_with_params(
                    "/admin",
                    msg=_s.ADMIN_MSG_TRAINING_ASSIGNMENT_INVALID,
                    scroll_y=scroll_y,
                    training_muscle=_normalize_muscle_key(training_muscle),
                    training_client_q=(training_client_q or "").strip(),
                    training_client_id=str(max(0, int(client_id or 0))),
                )
                + "#section-training-management",
                status_code=303,
            )
        title_clean = (title or "").strip()[:180]
        notes_clean = (notes or "").strip()[:3000]
        reps_clean = (reps_text or "").strip()[:64]
        intensity_clean = (intensity_text or "").strip()[:64]
        try:
            sets_clean = int(sets_count or 0)
        except (TypeError, ValueError):
            sets_clean = 0
        try:
            duration_clean = int(duration_minutes or 0)
        except (TypeError, ValueError):
            duration_clean = 0
        try:
            rest_clean = int(rest_seconds or 0)
        except (TypeError, ValueError):
            rest_clean = 0
        batch = _s.models.TrainingAssignmentBatch(
            center_id=cid,
            client_id=client.id,
            assigned_by_user_id=user.id,
            title=title_clean or f"خطة تدريب للمتدرب {client.full_name}",
            notes=notes_clean or None,
            starts_at=start_dt,
            ends_at=end_dt,
            status="active",
        )
        db.add(batch)
        db.flush()
        for idx, ex in enumerate(exercise_rows):
            db.add(
                _s.models.TrainingAssignmentItem(
                    center_id=cid,
                    batch_id=batch.id,
                    client_id=client.id,
                    exercise_id=ex.id,
                    muscle_key=ex.muscle_key,
                    exercise_name=ex.exercise_name,
                    sets_count=(sets_clean if sets_clean > 0 else None),
                    reps_text=(reps_clean or None),
                    duration_minutes=(duration_clean if duration_clean > 0 else None),
                    rest_seconds=(rest_clean if rest_clean > 0 else None),
                    intensity_text=(intensity_clean or None),
                    notes=ex.notes,
                    sort_order=idx,
                )
            )
        db.commit()
        return _s.RedirectResponse(
            url=_s._url_with_params(
                "/admin",
                msg=_s.ADMIN_MSG_TRAINING_ASSIGNMENT_CREATED,
                scroll_y=scroll_y,
                training_muscle=_normalize_muscle_key(training_muscle),
                training_client_q=(training_client_q or "").strip(),
                training_client_id=str(client.id),
            )
            + "#section-training-management",
            status_code=303,
        )

    @router.post("/admin/training/assignments/cancel")
    def admin_cancel_training_assignment(
        batch_id: int = _s.Form(...),
        training_muscle: str = _s.Form("core"),
        training_client_q: str = _s.Form(""),
        training_client_id: int = _s.Form(0),
        scroll_y: str = _s.Form(default=""),
        db: _s.Session = _s.Depends(_s.get_db),
        user: _s.models.User = _s.Depends(
            _s.require_permissions_cookie_or_bearer("sessions.manage")
        ),
    ):
        cid = _s.require_user_center_id(user)
        batch = (
            db.query(_s.models.TrainingAssignmentBatch)
            .filter(_s.models.TrainingAssignmentBatch.id == batch_id)
            .first()
        )
        if not batch or batch.center_id != cid:
            return _s.RedirectResponse(
                url=_s._url_with_params(
                    "/admin",
                    msg=_s.ADMIN_MSG_TRAINING_ASSIGNMENT_NOT_FOUND,
                    scroll_y=scroll_y,
                    training_muscle=_normalize_muscle_key(training_muscle),
                    training_client_q=(training_client_q or "").strip(),
                    training_client_id=str(max(0, int(training_client_id or 0))),
                )
                + "#section-training-management",
                status_code=303,
            )
        batch.status = "cancelled"
        db.commit()
        return _s.RedirectResponse(
            url=_s._url_with_params(
                "/admin",
                msg=_s.ADMIN_MSG_TRAINING_ASSIGNMENT_CANCELLED,
                scroll_y=scroll_y,
                training_muscle=_normalize_muscle_key(training_muscle),
                training_client_q=(training_client_q or "").strip(),
                training_client_id=str(batch.client_id),
            )
            + "#section-training-management",
            status_code=303,
        )

    @router.post("/admin/training/medical/save")
    def admin_save_training_medical_profile(
        client_id: int = _s.Form(...),
        chronic_conditions: str = _s.Form(""),
        current_medications: str = _s.Form(""),
        allergies: str = _s.Form(""),
        injuries_history: str = _s.Form(""),
        surgeries_history: str = _s.Form(""),
        contraindications: str = _s.Form(""),
        emergency_contact_name: str = _s.Form(""),
        emergency_contact_phone: str = _s.Form(""),
        coach_notes: str = _s.Form(""),
        training_muscle: str = _s.Form("core"),
        training_client_q: str = _s.Form(""),
        scroll_y: str = _s.Form(default=""),
        db: _s.Session = _s.Depends(_s.get_db),
        user: _s.models.User = _s.Depends(
            _s.require_permissions_cookie_or_bearer("sessions.manage")
        ),
    ):
        cid = _s.require_user_center_id(user)
        if client_id <= 0:
            return _s.RedirectResponse(
                url=_s._url_with_params(
                    "/admin",
                    msg=_s.ADMIN_MSG_TRAINING_MEDICAL_HISTORY_INVALID,
                    scroll_y=scroll_y,
                    training_muscle=_normalize_muscle_key(training_muscle),
                    training_client_q=(training_client_q or "").strip(),
                    training_client_id=str(max(0, int(client_id or 0))),
                )
                + "#section-training-management",
                status_code=303,
            )
        client = (
            db.query(_s.models.Client)
            .filter(_s.models.Client.id == client_id, _s.models.Client.center_id == cid)
            .first()
        )
        if not client:
            return _s.RedirectResponse(
                url=_s._url_with_params(
                    "/admin",
                    msg=_s.ADMIN_MSG_TRAINING_MEDICAL_HISTORY_INVALID,
                    scroll_y=scroll_y,
                    training_muscle=_normalize_muscle_key(training_muscle),
                    training_client_q=(training_client_q or "").strip(),
                    training_client_id=str(max(0, int(client_id or 0))),
                )
                + "#section-training-management",
                status_code=303,
            )
        profile = (
            db.query(_s.models.ClientMedicalProfile)
            .filter(
                _s.models.ClientMedicalProfile.center_id == cid,
                _s.models.ClientMedicalProfile.client_id == client_id,
            )
            .first()
        )
        now = _s.utcnow_naive()
        if not profile:
            profile = _s.models.ClientMedicalProfile(
                center_id=cid,
                client_id=client_id,
                created_at=now,
            )
            db.add(profile)
        profile.chronic_conditions = (chronic_conditions or "").strip()[:4000] or None
        profile.current_medications = (current_medications or "").strip()[:4000] or None
        profile.allergies = (allergies or "").strip()[:4000] or None
        profile.injuries_history = (injuries_history or "").strip()[:4000] or None
        profile.surgeries_history = (surgeries_history or "").strip()[:4000] or None
        profile.contraindications = (contraindications or "").strip()[:4000] or None
        profile.emergency_contact_name = (emergency_contact_name or "").strip()[:120] or None
        profile.emergency_contact_phone = (emergency_contact_phone or "").strip()[:40] or None
        profile.coach_notes = (coach_notes or "").strip()[:4000] or None
        profile.updated_at = now
        db.commit()
        return _s.RedirectResponse(
            url=_s._url_with_params(
                "/admin",
                msg=_s.ADMIN_MSG_TRAINING_MEDICAL_PROFILE_SAVED,
                scroll_y=scroll_y,
                training_muscle=_normalize_muscle_key(training_muscle),
                training_client_q=(training_client_q or "").strip(),
                training_client_id=str(client_id),
            )
            + "#section-training-management",
            status_code=303,
        )

    @router.post("/admin/training/medical/history/add")
    def admin_add_training_medical_history_entry(
        client_id: int = _s.Form(...),
        category: str = _s.Form("condition"),
        title: str = _s.Form(""),
        details: str = _s.Form(""),
        event_date: str = _s.Form(""),
        severity: str = _s.Form(""),
        training_muscle: str = _s.Form("core"),
        training_client_q: str = _s.Form(""),
        scroll_y: str = _s.Form(default=""),
        db: _s.Session = _s.Depends(_s.get_db),
        user: _s.models.User = _s.Depends(
            _s.require_permissions_cookie_or_bearer("sessions.manage")
        ),
    ):
        cid = _s.require_user_center_id(user)
        title_clean = (title or "").strip()[:180]
        category_clean = (category or "").strip().lower()[:40] or "condition"
        if client_id <= 0 or not title_clean:
            return _s.RedirectResponse(
                url=_s._url_with_params(
                    "/admin",
                    msg=_s.ADMIN_MSG_TRAINING_MEDICAL_HISTORY_INVALID,
                    scroll_y=scroll_y,
                    training_muscle=_normalize_muscle_key(training_muscle),
                    training_client_q=(training_client_q or "").strip(),
                    training_client_id=str(max(0, int(client_id or 0))),
                )
                + "#section-training-management",
                status_code=303,
            )
        client = (
            db.query(_s.models.Client)
            .filter(_s.models.Client.id == client_id, _s.models.Client.center_id == cid)
            .first()
        )
        if not client:
            return _s.RedirectResponse(
                url=_s._url_with_params(
                    "/admin",
                    msg=_s.ADMIN_MSG_TRAINING_MEDICAL_HISTORY_INVALID,
                    scroll_y=scroll_y,
                    training_muscle=_normalize_muscle_key(training_muscle),
                    training_client_q=(training_client_q or "").strip(),
                    training_client_id=str(max(0, int(client_id or 0))),
                )
                + "#section-training-management",
                status_code=303,
            )
        event_dt = _s._parse_optional_date_str(event_date)
        row = _s.models.ClientMedicalHistoryEntry(
            center_id=cid,
            client_id=client_id,
            category=category_clean or "condition",
            title=title_clean,
            details=(details or "").strip()[:4000] or None,
            event_date=event_dt,
            severity=(severity or "").strip()[:32] or None,
            created_by_user_id=user.id,
        )
        db.add(row)
        db.commit()
        return _s.RedirectResponse(
            url=_s._url_with_params(
                "/admin",
                msg=_s.ADMIN_MSG_TRAINING_MEDICAL_HISTORY_ADDED,
                scroll_y=scroll_y,
                training_muscle=_normalize_muscle_key(training_muscle),
                training_client_q=(training_client_q or "").strip(),
                training_client_id=str(client_id),
            )
            + "#section-training-management",
            status_code=303,
        )

    @router.post("/admin/training/medical/history/delete")
    def admin_delete_training_medical_history_entry(
        history_id: int = _s.Form(...),
        training_muscle: str = _s.Form("core"),
        training_client_q: str = _s.Form(""),
        training_client_id: int = _s.Form(0),
        scroll_y: str = _s.Form(default=""),
        db: _s.Session = _s.Depends(_s.get_db),
        user: _s.models.User = _s.Depends(
            _s.require_permissions_cookie_or_bearer("sessions.manage")
        ),
    ):
        cid = _s.require_user_center_id(user)
        row = db.get(_s.models.ClientMedicalHistoryEntry, history_id)
        if not row or row.center_id != cid:
            return _s.RedirectResponse(
                url=_s._url_with_params(
                    "/admin",
                    msg=_s.ADMIN_MSG_TRAINING_MEDICAL_HISTORY_INVALID,
                    scroll_y=scroll_y,
                    training_muscle=_normalize_muscle_key(training_muscle),
                    training_client_q=(training_client_q or "").strip(),
                    training_client_id=str(max(0, int(training_client_id or 0))),
                )
                + "#section-training-management",
                status_code=303,
            )
        target_client_id = row.client_id
        db.delete(row)
        db.commit()
        return _s.RedirectResponse(
            url=_s._url_with_params(
                "/admin",
                msg=_s.ADMIN_MSG_TRAINING_MEDICAL_HISTORY_DELETED,
                scroll_y=scroll_y,
                training_muscle=_normalize_muscle_key(training_muscle),
                training_client_q=(training_client_q or "").strip(),
                training_client_id=str(target_client_id),
            )
            + "#section-training-management",
            status_code=303,
        )
