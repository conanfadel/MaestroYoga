"""Staff authentication and user management routes."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from . import deps as _d


def register_routes(router: APIRouter) -> None:
    @router.post("/auth/register", response_model=_d.schemas.TokenOut)
    def register_owner(payload: _d.schemas.UserRegister, db: Session = Depends(_d.get_db)):
        exists = db.query(_d.models.User).filter(_d.models.User.email == payload.email).first()
        if exists:
            raise HTTPException(status_code=409, detail="Email already registered")

        center = _d.models.Center(name=payload.center_name, city=payload.city)
        db.add(center)
        db.flush()

        owner = _d.models.User(
            center_id=center.id,
            full_name=payload.full_name,
            email=payload.email.lower(),
            password_hash=_d.hash_password(payload.password),
            role="center_owner",
        )
        db.add(owner)
        db.commit()
        db.refresh(owner)

        token = _d.create_access_token(owner.id)
        return {"access_token": token, "user": owner}

    @router.post("/auth/login", response_model=_d.schemas.TokenOut)
    def login(payload: _d.schemas.UserLogin, db: Session = Depends(_d.get_db)):
        user = db.query(_d.models.User).filter(_d.models.User.email == payload.email.lower()).first()
        if not user or not _d.verify_password(payload.password, user.password_hash):
            raise HTTPException(status_code=401, detail="Incorrect credentials")
        if not user.is_active:
            raise HTTPException(status_code=403, detail="User is inactive")
        token = _d.create_access_token(user.id)
        return {"access_token": token, "user": user}

    @router.get("/auth/me", response_model=_d.schemas.UserOut)
    def me(user: _d.models.User = Depends(_d.get_current_user)):
        return user

    @router.post("/auth/users", response_model=_d.schemas.UserOut)
    def create_user_by_owner(
        payload: _d.schemas.UserCreateByOwner,
        db: Session = Depends(_d.get_db),
        user: _d.models.User = Depends(_d.require_roles("center_owner")),
    ):
        exists = db.query(_d.models.User).filter(_d.models.User.email == payload.email.lower()).first()
        if exists:
            raise HTTPException(status_code=409, detail="Email already registered")
        perm_json: str | None = None
        if payload.role == "custom_staff" and payload.permission_ids:
            perm_json = json.dumps(payload.permission_ids, ensure_ascii=False)
        new_user = _d.models.User(
            center_id=user.center_id,
            full_name=payload.full_name,
            email=payload.email.lower(),
            password_hash=_d.hash_password(payload.password),
            role=payload.role,
            custom_role_label=payload.custom_role_label if payload.role == "custom_staff" else None,
            permissions_json=perm_json,
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        return new_user
