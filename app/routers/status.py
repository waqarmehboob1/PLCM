from typing import List
from fastapi import APIRouter, HTTPException, Depends
from sqlmodel import Session, select
from app.database import get_session
from app.models.tables import (Status)
from app.schemas import schemas

router = APIRouter()

# ===================== STATUS ENDPOINTS =====================
@router.post("/statuses/", response_model=schemas.StatusRead, tags=["statuses"])
def create_status(status: schemas.StatusCreate, session: Session = Depends(get_session)):
    db_status = Status(**status.model_dump())
    session.add(db_status)
    session.commit()
    session.refresh(db_status)
    return db_status

@router.get("/statuses/", response_model=List[schemas.StatusRead], tags=["statuses"])
def list_statuses(session: Session = Depends(get_session)):
    return session.exec(select(Status)).all()

@router.get("/statuses/{status_id}/", response_model=schemas.StatusRead, tags=["statuses"])
def get_status(status_id: int, session: Session = Depends(get_session)):
    status = session.get(Status, status_id)
    if not status:
        raise HTTPException(status_code=404, detail="Status not found")
    return status

@router.put("/statuses/{status_id}/", response_model=schemas.StatusRead, tags=["statuses"])
def update_status(status_id: int, status: schemas.StatusUpdate, session: Session = Depends(get_session)):
    db_status = session.get(Status, status_id)
    if not db_status:
        raise HTTPException(status_code=404, detail="Status not found")
    for k, v in status.model_dump(exclude_unset=True).items():
        setattr(db_status, k, v)
    session.add(db_status)
    session.commit()
    session.refresh(db_status)
    return db_status

@router.delete("/statuses/{status_id}/", tags=["statuses"])
def delete_status(status_id: int, session: Session = Depends(get_session)):
    status = session.get(Status, status_id)
    if not status:
        raise HTTPException(status_code=404, detail="Status not found")
    session.delete(status)
    session.commit()
    return {"ok": True}