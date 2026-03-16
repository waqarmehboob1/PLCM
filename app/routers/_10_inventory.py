from typing import List
from fastapi import APIRouter, HTTPException, Depends
from sqlmodel import Session, select
from app.database import get_session
from app.models.tables import (Inventory)
from app.schemas import schemas
from app.services.create_entity import New_entity
from app.services.create_entitystatusHistory import create_status_history
from app.services.update_entity import update_entity_status
from app.config.entities import ENTITY_CONFIG
entity_config = ENTITY_CONFIG.get("project")

router = APIRouter()



# ===================== INVENTORY ENDPOINTS =====================
@router.post("/inventory/", response_model=schemas.InventoryRead, tags=["inventory"])
def create_inventory(inventory: schemas.InventoryCreate, session: Session = Depends(get_session)):
    db_inventory = Inventory(**inventory.model_dump())
    session.add(db_inventory)
    session.flush()

# Create
#    1.  Entity status
#    2.  Entity Status History
# --------------------------------------------------------------------------------------------------------------------------------------------
    New_entity(session=session, entity=db_inventory, entity_name = ENTITY_CONFIG["display_name"])
# --------------------------------------------------------------------------------------------------------------------------------------------

    session.commit()
    session.refresh(db_inventory)
    return db_inventory

@router.get("/inventory/", response_model=List[schemas.InventoryRead], tags=["inventory"])
def list_inventory(skip: int = 0, limit: int = 100, session: Session = Depends(get_session)):
    return session.exec(select(Inventory).offset(skip).limit(limit)).all()

@router.get("/inventory/{inventory_id}/", response_model=schemas.InventoryRead, tags=["inventory"])
def get_inventory(inventory_id: int, session: Session = Depends(get_session)):
    inventory = session.get(Inventory, inventory_id)
    if not inventory:
        raise HTTPException(status_code=404, detail="Inventory not found")
    return inventory

@router.put("/inventory/{inventory_id}/", response_model=schemas.InventoryRead, tags=["inventory"])
def update_inventory(inventory_id: int, inventory: schemas.InventoryUpdate, session: Session = Depends(get_session)):
    db_inventory = session.get(Inventory, inventory_id)
    if not db_inventory:
        raise HTTPException(status_code=404, detail="Inventory not found")
    for k, v in inventory.model_dump(exclude_unset=True).items():
        setattr(db_inventory, k, v)
    session.add(db_inventory)
    session.flush()

# Update Entity status and Create Entity Status History
# --------------------------------------------------------------------------------------------------------------------------------------------
    update_entity_status(session=session, entity= db_inventory, entity_name = "order")

    session.commit()
    session.refresh(db_inventory)
    return db_inventory

@router.delete("/inventory/{inventory_id}/", tags=["inventory"])
def delete_inventory(inventory_id: int, session: Session = Depends(get_session)):
    inventory = session.get(Inventory, inventory_id)
    if not inventory:
        raise HTTPException(status_code=404, detail="Inventory not found")
    session.delete(inventory)
    session.commit()
    return {"ok": True}
