from typing import List
from fastapi import APIRouter, HTTPException, Depends
from sqlmodel import Session, select
from app.database import get_session
from app.models.tables import (Customer, User)
from app.schemas import schemas
from app.routers.auth import require_permission

router = APIRouter()

# ===================== CUSTOMER ENDPOINTS =====================
@router.post("/customers/", response_model=schemas.CustomerRead, tags=["customers"])
def create_customer(customer: schemas.CustomerCreate, session: Session = Depends(get_session), current_user: User = Depends(require_permission("create_customers"))):
    db_customer = Customer(**customer.model_dump())
    session.add(db_customer)
    session.commit()
    session.refresh(db_customer)
    return db_customer

@router.get("/customers/", response_model=List[schemas.CustomerRead], tags=["customers"])
def list_customers(skip: int = 0, limit: int = 100, session: Session = Depends(get_session), current_user: User = Depends(require_permission("view_customers"))):
    return session.exec(select(Customer).offset(skip).limit(limit)).all()

@router.get("/customers/{customer_id}/", response_model=schemas.CustomerRead, tags=["customers"])
def get_customer(customer_id: int, session: Session = Depends(get_session), current_user: User = Depends(require_permission("view_customers"))):
    customer = session.get(Customer, customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    return customer

@router.put("/customers/{customer_id}/", response_model=schemas.CustomerRead, tags=["customers"])
def update_customer(customer_id: int, customer: schemas.CustomerUpdate, session: Session = Depends(get_session), current_user: User = Depends(require_permission("edit_customers"))):
    db_customer = session.get(Customer, customer_id)
    if not db_customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    for k, v in customer.model_dump(exclude_unset=True).items():
        setattr(db_customer, k, v)
    session.add(db_customer)
    session.commit()
    session.refresh(db_customer)
    return db_customer

@router.delete("/customers/{customer_id}/", tags=["customers"])
def delete_customer(customer_id: int, session: Session = Depends(get_session), current_user: User = Depends(require_permission("delete_customers"))):
    customer = session.get(Customer, customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    session.delete(customer)
    session.commit()
    return {"ok": True}

@router.get("/customers/{customer_id}/orders/", response_model=List[schemas.OrderRead], tags=["customers"])
def list_customer_orders(customer_id: int, session: Session = Depends(get_session)):
    customer = session.get(Customer, customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    return customer.orders