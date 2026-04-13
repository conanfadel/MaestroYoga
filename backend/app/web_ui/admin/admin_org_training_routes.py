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
            )
            + "#section-training-management",
            status_code=303,
        )

    @router.post("/admin/training/exercises/delete")
    def admin_delete_training_exercise(
        exercise_id: int = _s.Form(...),
        muscle_key: str = _s.Form("core"),
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
            )
            + "#section-training-management",
            status_code=303,
        )
