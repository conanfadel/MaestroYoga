from sqlalchemy.orm import Session

from . import models


def get_or_sync_public_client(db: Session, *, center_id: int, public_user) -> models.Client:
    email = (public_user.email or "").strip().lower()
    client = (
        db.query(models.Client)
        .filter(models.Client.center_id == center_id, models.Client.email == email)
        .first()
    )
    if not client:
        client = models.Client(
            center_id=center_id,
            full_name=public_user.full_name,
            email=email,
            phone=public_user.phone,
        )
        db.add(client)
        db.flush()
        return client

    client.full_name = public_user.full_name
    if public_user.phone:
        client.phone = public_user.phone
    return client
