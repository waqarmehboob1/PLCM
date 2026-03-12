from app.models.tables import (Entity)
from sqlmodel import Field
from datetime import datetime, timezone
from app.schemas import schemas
from app.services import create_entitystatusHistory


def New_entity(session, entity_data=schemas.EntityCreate) -> Entity:
    entity = Entity(**entity_data.model_dump())
    session.add(entity)
    session.flush()
    return entity