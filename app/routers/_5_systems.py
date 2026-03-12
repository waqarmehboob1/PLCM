from typing import List
from fastapi import APIRouter, HTTPException, Depends
from sqlmodel import Session, select
from app.database import get_session
from app.models.tables import (System)
from app.schemas import schemas

router = APIRouter()

# ===================== SYSTEM ENDPOINTS =====================
@router.post("/systems/", response_model=schemas.SystemRead, tags=["systems"])
def create_system(system: schemas.SystemCreate, session: Session = Depends(get_session)):
    db_system = System(**system.dict())
    session.add(db_system)
    session.commit()
    session.refresh(db_system)
    status_name = db_system.status.name if db_system.status else None
    return schemas.SystemRead(
        **db_system.model_dump(),
        status_name=status_name,
        subsystems=db_system.subsystems
    )

@router.get("/systems/", response_model=List[schemas.SystemRead], tags=["systems"])
def list_systems(skip: int = 0, limit: int = 100, session: Session = Depends(get_session)):
    systems = session.exec(select(System).offset(skip).limit(limit)).all()
    result = []
    for system in systems:
        status_name = system.status.name if system.status else None
        result.append(schemas.SystemRead(
            **system.model_dump(),
            status_name=status_name,
            subsystems=system.subsystems
        ))
    return result

@router.get("/systems/{system_id}/", response_model=schemas.SystemRead, tags=["systems"])
def get_system(system_id: int, session: Session = Depends(get_session)):
    system = session.get(System, system_id)
    if not system:
        raise HTTPException(status_code=404, detail="System not found")
    status_name = system.status.name if system.status else None
    return schemas.SystemRead(
        **system.model_dump(),
        status_name=status_name,
        subsystems=system.subsystems
    )

@router.put("/systems/{system_id}/", response_model=schemas.SystemRead, tags=["systems"])
def update_system(system_id: int, system: schemas.SystemUpdate, session: Session = Depends(get_session)):
    db_system = session.get(System, system_id)
    if not db_system:
        raise HTTPException(status_code=404, detail="System not found")
    for k, v in system.model_dump(exclude_unset=True).items():
        setattr(db_system, k, v)
    session.add(db_system)
    session.commit()
    session.refresh(db_system)
    status_name = db_system.status.name if db_system.status else None
    return schemas.SystemRead(
        **db_system.model_dump(),
        status_name=status_name,
        subsystems=db_system.subsystems
    )

@router.delete("/systems/{system_id}/", tags=["systems"])
def delete_system(system_id: int, session: Session = Depends(get_session)):
    system = session.get(System, system_id)
    if not system:
        raise HTTPException(status_code=404, detail="System not found")
    session.delete(system)
    session.commit()
    return {"ok": True}

@router.get("/systems/{system_id}/subsystems/", response_model=List[schemas.SubsystemRead], tags=["systems"])
def list_system_subsystems(system_id: int, session: Session = Depends(get_session)):
    system = session.get(System, system_id)
    if not system:
        raise HTTPException(status_code=404, detail="System not found")
    return system.subsystems
