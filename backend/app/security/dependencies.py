"""FastAPI dependencies: OAuth2, cookie+bearer, role and permission guards."""

from __future__ import annotations

from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer, OAuth2PasswordBearer
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from .staff_tokens import get_user_from_token_string

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")
http_bearer_optional = HTTPBearer(auto_error=False)


def get_current_user_cookie_or_bearer(
    request: Request,
    creds: Optional[HTTPAuthorizationCredentials] = Depends(http_bearer_optional),
    db: Session = Depends(get_db),
) -> models.User:
    token = creds.credentials if creds else None
    if not token:
        token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return get_user_from_token_string(token, db)


def require_roles_cookie_or_bearer(*roles: str):
    def checker(user: models.User = Depends(get_current_user_cookie_or_bearer)) -> models.User:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user

    return checker


def require_permissions_cookie_or_bearer(*permission_ids: str):
    """يجب أن يمتلك المستخدم جميع الصلاحيات المذكورة (المالك يملك الكل عبر rbac)."""

    def checker(user: models.User = Depends(get_current_user_cookie_or_bearer)) -> models.User:
        from ..rbac import user_has_all_permissions

        if not user_has_all_permissions(user, permission_ids):
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user

    return checker


def require_any_permission_cookie_or_bearer(*permission_ids: str):
    """امتلاك أي صلاحية من القائمة يكفي."""

    def checker(user: models.User = Depends(get_current_user_cookie_or_bearer)) -> models.User:
        from ..rbac import user_has_any_permission

        if not user_has_any_permission(user, permission_ids):
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user

    return checker


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> models.User:
    return get_user_from_token_string(token, db)


def require_roles(*roles: str):
    def checker(user: models.User = Depends(get_current_user)) -> models.User:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user

    return checker


def require_permissions(*permission_ids: str):
    def checker(user: models.User = Depends(get_current_user)) -> models.User:
        from ..rbac import user_has_all_permissions

        if not user_has_all_permissions(user, permission_ids):
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user

    return checker


def require_any_permission(*permission_ids: str):
    def checker(user: models.User = Depends(get_current_user)) -> models.User:
        from ..rbac import user_has_any_permission

        if not user_has_any_permission(user, permission_ids):
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user

    return checker
