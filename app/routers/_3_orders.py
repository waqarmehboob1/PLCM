from typing import List
from fastapi import APIRouter, HTTPException, Depends
from sqlmodel import Session, select
from app.database import get_session
from app.models.tables import (Order)
from app.schemas import schemas
from app.services.create_entity import New_entity
from app.services.create_entitystatusHistory import create_status_history
router = APIRouter()

# ===================== ORDER ENDPOINTS =====================
@router.post("/orders/", response_model=schemas.OrderRead, tags=["orders"])
def create_order(order: schemas.OrderCreate, session: Session = Depends(get_session)):
    db_order = Order(**order.model_dump())
    session.add(db_order)
    session.flush()

    entity = New_entity(
            session=session,
            entity_data=schemas.EntityCreate(
                name=f"Order-{db_order.id}",
                display_name=f"Order-{db_order.id}",
                entity_type="order",
                entity_pk=db_order.id,
                status_id=db_order.status_id
            ))

    create_status_history(
        session=session,
        history_data=schemas.EntityStatusHistoryCreate(
            entity_id=entity.id,
            status_id=entity.status_id,
            changed_by=5
        )
    )
    session.commit()
    session.refresh(db_order)
    # Attach status_name for response


    
    status_name = db_order.status.name if db_order.status else None

    return schemas.OrderRead(
        **db_order.model_dump(),
        status_name=status_name,
        projects=db_order.projects
    )

@router.get("/orders/", response_model=List[schemas.OrderRead], tags=["orders"])
def list_orders(skip: int = 0, limit: int = 100, session: Session = Depends(get_session)):
    orders = session.exec(select(Order).offset(skip).limit(limit)).all()
    result = []
    for order in orders:
        status_name = order.status.name if order.status else None
        result.append(schemas.OrderRead(
            **order.model_dump(),
            status_name=status_name,
            projects=order.projects
        ))
    return result

@router.get("/orders/{order_id}/", response_model=schemas.OrderRead, tags=["orders"])
def get_order(order_id: int, session: Session = Depends(get_session)):
    order = session.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    status_name = order.status.name if order.status else None
    return schemas.OrderRead(
        **order.model_dump(),
        status_name=status_name,
        projects=order.projects
    )

@router.put("/orders/{order_id}/", response_model=schemas.OrderRead, tags=["orders"])
def update_order(order_id: int, order: schemas.OrderUpdate, session: Session = Depends(get_session)):
    db_order = session.get(Order, order_id)
    if not db_order:
        raise HTTPException(status_code=404, detail="Order not found")
    for k, v in order.model_dump(exclude_unset=True).items():
        setattr(db_order, k, v)
    session.add(db_order)
    session.commit()
    session.refresh(db_order)
    status_name = db_order.status.name if db_order.status else None
    return schemas.OrderRead(
        **db_order.model_dump(),
        status_name=status_name,
        projects=db_order.projects
    )

@router.delete("/orders/{order_id}/", tags=["orders"])
def delete_order(order_id: int, session: Session = Depends(get_session)):
    order = session.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    session.delete(order)
    session.commit()
    return {"ok": True}

@router.get("/orders/{order_id}/projects/", response_model=List[schemas.ProjectRead], tags=["orders"])
def list_order_projects(order_id: int, session: Session = Depends(get_session)):
    order = session.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order.projects
