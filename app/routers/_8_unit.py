from typing import List
from fastapi import APIRouter, HTTPException, Depends
from sqlmodel import Session, select
from app.database import get_session
from app.models.tables import (Unit)
from app.schemas import schemas

router = APIRouter()

# ===================== UNIT ENDPOINTS =====================
@router.post("/units/", response_model=schemas.UnitRead, tags=["units"])
def create_unit(unit: schemas.UnitCreate, session: Session = Depends(get_session)):
    db_unit = Unit(**unit.model_dump())
    session.add(db_unit)
    session.commit()
    session.refresh(db_unit)
    status_name = db_unit.status.name if db_unit.status else None
    return schemas.UnitRead(
        **db_unit.model_dump(),
        status_name=status_name,
        components=db_unit.components
    )

@router.get("/units/", response_model=List[schemas.UnitRead], tags=["units"])
def list_units(skip: int = 0, limit: int = 100, session: Session = Depends(get_session)):
    units = session.exec(select(Unit).offset(skip).limit(limit)).all()
    result = []
    for unit in units:
        status_name = unit.status.name if unit.status else None
        result.append(schemas.UnitRead(
            **unit.model_dump(),
            status_name=status_name,
            components=unit.components
        ))
    return result

@router.get("/units/{unit_id}/", response_model=schemas.UnitRead, tags=["units"])
def get_unit(unit_id: int, session: Session = Depends(get_session)):
    unit = session.get(Unit, unit_id)
    if not unit:
        raise HTTPException(status_code=404, detail="Unit not found")
    status_name = unit.status.name if unit.status else None
    return schemas.UnitRead(
        **unit.model_dump(),
        status_name=status_name,
        components=unit.components
    )

@router.put("/units/{unit_id}/", response_model=schemas.UnitRead, tags=["units"])
def update_unit(unit_id: int, unit: schemas.UnitUpdate, session: Session = Depends(get_session)):
    db_unit = session.get(Unit, unit_id)
    if not db_unit:
        raise HTTPException(status_code=404, detail="Unit not found")
    for k, v in unit.model_dump(exclude_unset=True).items():
        setattr(db_unit, k, v)
    session.add(db_unit)
    session.commit()
    session.refresh(db_unit)
    status_name = db_unit.status.name if db_unit.status else None
    return schemas.UnitRead(
        **db_unit.model_dump(),
        status_name=status_name,
        components=db_unit.components
    )

@router.delete("/units/{unit_id}/", tags=["units"])
def delete_unit(unit_id: int, session: Session = Depends(get_session)):
    unit = session.get(Unit, unit_id)
    if not unit:
        raise HTTPException(status_code=404, detail="Unit not found")
    session.delete(unit)
    session.commit()
    return {"ok": True}

@router.get("/units/{unit_id}/components/", response_model=List[schemas.ComponentRead], tags=["units"])
def list_unit_components(unit_id: int, session: Session = Depends(get_session)):
    unit = session.get(Unit, unit_id)
    if not unit:
        raise HTTPException(status_code=404, detail="Unit not found")
    return unit.components
