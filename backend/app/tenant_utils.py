from fastapi import HTTPException

from . import models


def require_user_center_id(user: models.User) -> int:
    if not user.center_id:
        raise HTTPException(status_code=403, detail="User is not assigned to a center")
    return user.center_id
