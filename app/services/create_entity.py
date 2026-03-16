from app.models.tables import (Entity)
from sqlmodel import Field
from datetime import datetime, timezone
from app.schemas import schemas
from app.services.create_entitystatusHistory import create_status_history


def New_entity(session, entity:any, entity_name:str) -> Entity:

    entity_data=schemas.EntityCreate(
            name=f"{entity_name}-{entity.id}",
            display_name=f"{entity_name}-{entity.id}",
            entity_type=entity_name,
            entity_pk=entity.id,
            status_id=entity.status_id
        )


    entity = Entity(**entity_data.model_dump())
    session.add(entity)
    session.flush()

    create_status_history(
        session=session,
        history_data=schemas.EntityStatusHistoryCreate(
            entity_id=entity.id,
            status_id=entity.status_id,
            changed_by=5
        )
    )
    return entity