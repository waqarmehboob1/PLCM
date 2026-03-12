# 2️⃣ Service: Update Entity Status
# This updates current status in the entity table.

from app.models.tables import (Entity)
from sqlmodel import Session, select
from typing import Optional


def update_entity_status(
    session: Session,
    entity_type: Optional[str],
    entity_pk: Optional[int],
    new_status_id: Optional[int]
):

    entity = session.exec(
        select(Entity).where(
            Entity.entity_type == entity_type,
            Entity.entity_pk == entity_pk
        )
    ).first()

    if not entity:
        return None

    entity.status_id = new_status_id

    session.add(entity)
    session.flush()
    session.refresh(entity)

    return entity