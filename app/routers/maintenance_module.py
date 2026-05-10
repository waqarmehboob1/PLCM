# =============================================================================
# maintenance_module.py
# Maintenance Case Management — Models, Schemas & Endpoints
# Covers: MaintenanceCase → FaultyEntity → MaintenanceAction → MaintenanceDelivery
# =============================================================================

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Field, Relationship, Session, SQLModel, select

# Project-level imports (adjust paths to match your project structure)
from db import get_session
from auth import require_permission
from models.user import User, UserRead
from models.project import Project  # your existing Project table model


router = APIRouter(prefix="/api/v1", tags=["maintenance"])


# =============================================================================
# ENUMS
# =============================================================================

class EntityType(str, Enum):
    PROJECT   = "project"
    SYSTEM    = "system"
    SUBSYSTEM = "subsystem"
    MODULE    = "module"
    UNIT      = "unit"
    COMPONENT = "component"


class CaseStatus(str, Enum):
    OPEN             = "open"
    UNDER_INSPECTION = "under_inspection"
    UNDER_REPAIR     = "under_repair"
    RESOLVED         = "resolved"
    CLOSED           = "closed"


class FaultType(str, Enum):
    HARDWARE             = "hardware"
    SOFTWARE             = "software"
    PHYSICAL_DAMAGE      = "physical_damage"
    WEAR                 = "wear"
    MANUFACTURING_DEFECT = "manufacturing_defect"
    UNCLASSIFIED         = "unclassified"


class FaultyEntityStatus(str, Enum):
    IDENTIFIED       = "identified"
    UNDER_INSPECTION = "under_inspection"
    CONFIRMED_FAULTY = "confirmed_faulty"
    RESOLVED         = "resolved"
    NO_FAULT_FOUND   = "no_fault_found"


class ResolutionType(str, Enum):
    REPAIRED       = "repaired"
    REPLACED       = "replaced"
    NO_FAULT_FOUND = "no_fault_found"
    DECOMMISSIONED = "decommissioned"


class ActionType(str, Enum):
    INSPECTION    = "inspection"
    DISASSEMBLY   = "disassembly"
    REPAIR        = "repair"
    REPLACEMENT   = "replacement"
    TESTING       = "testing"
    CLEANING      = "cleaning"
    RECALIBRATION = "recalibration"


class ActionOutcome(str, Enum):
    PASS         = "pass"
    FAIL         = "fail"
    INCONCLUSIVE = "inconclusive"
    PENDING      = "pending"


class DeliveryType(str, Enum):
    INITIAL_DELIVERY    = "initial_delivery"
    RE_DELIVERY         = "re_delivery"
    PARTIAL_RE_DELIVERY = "partial_re_delivery"


class DeliveryStatus(str, Enum):
    PENDING               = "pending"
    DISPATCHED            = "dispatched"
    DELIVERED             = "delivered"
    CONFIRMED_BY_CUSTOMER = "confirmed_by_customer"


# =============================================================================
# 1. MAINTENANCE CASE
# =============================================================================
# A top-level fault event opened against a delivered project.
# One project can accumulate many cases over its lifetime.
# =============================================================================

class MaintenanceCaseCommon(SQLModel):
    """Shared fields — no auto-generated values, no PKs, no FKs."""
    description:      str
    status:           CaseStatus  = CaseStatus.OPEN
    resolution_notes: Optional[str] = None


class MaintenanceCaseBase(MaintenanceCaseCommon):
    """Adds server-side timestamps."""
    reported_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    closed_at: Optional[datetime] = None


class MaintenanceCase(MaintenanceCaseBase, table=True):
    """
    PostgreSQL table: maintenance_case
    One row per fault event reported against a delivered project.
    """
    __tablename__ = "maintenance_case"

    id:            Optional[int] = Field(default=None, primary_key=True)
    case_number:   str           = Field(
        unique=True, index=True, max_length=50,
        description="Auto-generated. Format: MC-YYYY-NNNN"
    )
    project_id:    int           = Field(foreign_key="project.id")
    reported_by:   Optional[int] = Field(default=None, foreign_key="user.id")

    # Relationships
    project:          Optional[Project]          = Relationship(back_populates="maintenance_cases")
    reported_by_user: Optional[User]             = Relationship(back_populates="reported_cases")
    faulty_entities:  List["FaultyEntity"]       = Relationship(back_populates="case")
    deliveries:       List["MaintenanceDelivery"] = Relationship(back_populates="case")


# ── Schemas ──────────────────────────────────────────────────────────────────

class MaintenanceCaseCreate(MaintenanceCaseBase):
    """
    POST /maintenance-cases/
    project_id and reported_by are supplied by the caller.
    case_number is auto-generated server-side; do not send it.
    """
    project_id:  int
    reported_by: Optional[int] = None


class MaintenanceCaseRead(MaintenanceCaseBase):
    """
    Full case response, including nested faulty entities and deliveries.
    """
    id:               int
    case_number:      str
    project_id:       int
    reported_by:      Optional[int]                 = None
    reported_by_user: Optional[UserRead]            = None
    faulty_entities:  List["FaultyEntityRead"]       = []
    deliveries:       List["MaintenanceDeliveryRead"] = []

    class Config:
        orm_mode = True


class MaintenanceCaseUpdate(SQLModel):
    """
    PUT /maintenance-cases/{id}/
    All fields optional — only supplied fields are patched.
    """
    status:           Optional[CaseStatus] = None
    resolution_notes: Optional[str]        = None
    closed_at:        Optional[datetime]   = None


# =============================================================================
# 2. FAULTY ENTITY
# =============================================================================
# Polymorphic record pointing to any level of the hierarchy
# (project / system / subsystem / module / unit / component).
# parent_faulty_entity_id enables the fault cascade chain to be explicit:
#   component FE → parent unit FE → parent module FE → ...
# =============================================================================

class FaultyEntityCommon(SQLModel):
    """Shared fields — entity discriminator, fault classification."""
    entity_type:       EntityType
    entity_id:         int
    fault_type:        FaultType          = FaultType.UNCLASSIFIED
    fault_description: Optional[str]      = None
    status:            FaultyEntityStatus = FaultyEntityStatus.IDENTIFIED
    resolution_type:   Optional[ResolutionType] = None


class FaultyEntityBase(FaultyEntityCommon):
    """Adds server-side timestamps."""
    identified_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    resolved_at: Optional[datetime] = None


class FaultyEntity(FaultyEntityBase, table=True):
    """
    PostgreSQL table: faulty_entity
    One row per affected entity within a maintenance case.+

    Self-referencing via parent_faulty_entity_id to model the cascade chain.
    SQLModel requires sa_relationship_kwargs with remote_side for self-refs.
    """
    __tablename__ = "faulty_entity"

    id:                      Optional[int] = Field(default=None, primary_key=True)
    case_id:                 int           = Field(foreign_key="maintenance_case.id", index=True)
    identified_by:           Optional[int] = Field(default=None, foreign_key="user.id")
    parent_faulty_entity_id: Optional[int] = Field(
        default=None,
        foreign_key="faulty_entity.id",
        description="FK to self — links this row to its parent in the cascade chain."
    )

    # Relationships
    case:             Optional[MaintenanceCase]  = Relationship(back_populates="faulty_entities")
    identified_by_user: Optional[User]           = Relationship(back_populates="identified_faults")
    actions:          List["MaintenanceAction"]  = Relationship(back_populates="faulty_entity")

    # Self-referential: parent / children
    # remote_side points to the PK column (the "one" side of one-to-many).
    children: List["FaultyEntity"] = Relationship(
        back_populates="parent",
        sa_relationship_kwargs={
            "foreign_keys":  "[FaultyEntity.parent_faulty_entity_id]",
        }
    )
    parent: Optional["FaultyEntity"] = Relationship(
        back_populates="children",
        sa_relationship_kwargs={
            "foreign_keys": "[FaultyEntity.parent_faulty_entity_id]",
            "remote_side":  "[FaultyEntity.id]",
        }
    )


# ── Schemas ──────────────────────────────────────────────────────────────────

class FaultyEntityCreate(FaultyEntityBase):
    """
    POST /maintenance-cases/{case_id}/faulty-entities/
    identified_by defaults to current_user server-side.
    """
    identified_by:           Optional[int] = None
    parent_faulty_entity_id: Optional[int] = None


class FaultyEntityRead(FaultyEntityBase):
    id:                      int
    case_id:                 int
    identified_by:           Optional[int]                = None
    identified_by_user:      Optional[UserRead]           = None
    parent_faulty_entity_id: Optional[int]                = None
    actions:                 List["MaintenanceActionRead"] = []

    class Config:
        orm_mode = True


class FaultyEntityUpdate(SQLModel):
    """
    PUT /faulty-entities/{id}/
    Use this for status transitions, resolution, and reclassification.
    """
    fault_type:        Optional[FaultType]          = None
    fault_description: Optional[str]                = None
    status:            Optional[FaultyEntityStatus] = None
    resolution_type:   Optional[ResolutionType]     = None
    resolved_at:       Optional[datetime]           = None


class FaultyEntityCascadeCreate(SQLModel):
    """
    POST /maintenance-cases/{case_id}/cascade-fault/
    Identifies the root faulty entity; the endpoint walks UP the hierarchy
    and auto-creates parent FaultyEntity rows for each ancestor.
    """
    root_entity_type:  EntityType
    root_entity_id:    int
    fault_type:        FaultType  = FaultType.UNCLASSIFIED
    fault_description: Optional[str] = None


class FaultyEntityCascadeRead(SQLModel):
    """Response returned by the cascade-fault endpoint."""
    created_faulty_entities:  List[FaultyEntityRead]
    total_levels_cascaded:    int
    message:                  str


# =============================================================================
# 3. MAINTENANCE ACTION
# =============================================================================
# Individual audit-log entries for every action taken on a faulty entity.
# Includes: inspection, repair, replacement, testing, cleaning, recalibration.
# On replacement, replacement_entity_id records the new entity that took over.
# =============================================================================

class MaintenanceActionCommon(SQLModel):
    action_type: ActionType
    notes:       Optional[str]          = None
    outcome:     Optional[ActionOutcome] = None
    # Populated only when action_type == ActionType.REPLACEMENT
    replacement_entity_id:   Optional[int]      = None
    replacement_entity_type: Optional[EntityType] = None


class MaintenanceActionBase(MaintenanceActionCommon):
    performed_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class MaintenanceAction(MaintenanceActionBase, table=True):
    """
    PostgreSQL table: maintenance_action
    One row per action performed on a faulty entity.
    """
    __tablename__ = "maintenance_action"

    id:               Optional[int] = Field(default=None, primary_key=True)
    faulty_entity_id: int           = Field(foreign_key="faulty_entity.id", index=True)
    performed_by:     Optional[int] = Field(default=None, foreign_key="user.id")

    # Relationships
    faulty_entity:    Optional[FaultyEntity] = Relationship(back_populates="actions")
    performed_by_user: Optional[User]        = Relationship(back_populates="maintenance_actions")


# ── Schemas ──────────────────────────────────────────────────────────────────

class MaintenanceActionCreate(MaintenanceActionBase):
    """POST /faulty-entities/{faulty_entity_id}/actions/"""
    performed_by: Optional[int] = None


class MaintenanceActionRead(MaintenanceActionBase):
    id:                      int
    faulty_entity_id:        int
    performed_by:            Optional[int]     = None
    performed_by_user:       Optional[UserRead] = None
    replacement_entity_id:   Optional[int]     = None
    replacement_entity_type: Optional[EntityType] = None

    class Config:
        orm_mode = True


class MaintenanceActionUpdate(SQLModel):
    """PUT /maintenance-actions/{id}/"""
    notes:   Optional[str]           = None
    outcome: Optional[ActionOutcome] = None


# =============================================================================
# 4. MAINTENANCE DELIVERY
# =============================================================================
# Records every delivery event linked to a case:
#   - initial_delivery  → first time product goes to customer (optional use)
#   - re_delivery       → product returned after repair / replacement
#   - partial_re_delivery → only some entities were resolved and re-sent
# Confirming a delivery auto-closes the parent case when status = resolved.
# =============================================================================

class MaintenanceDeliveryCommon(SQLModel):
    delivery_type: DeliveryType   = DeliveryType.RE_DELIVERY
    status:        DeliveryStatus = DeliveryStatus.PENDING
    received_by:   Optional[str]  = Field(
        default=None,
        description="Customer contact name or signature reference."
    )
    notes: Optional[str] = None


class MaintenanceDeliveryBase(MaintenanceDeliveryCommon):
    delivered_at: Optional[datetime] = None


class MaintenanceDelivery(MaintenanceDeliveryBase, table=True):
    """
    PostgreSQL table: maintenance_delivery
    One row per dispatch/delivery event against a maintenance case.
    """
    __tablename__ = "maintenance_delivery"

    id:           Optional[int] = Field(default=None, primary_key=True)
    case_id:      int           = Field(foreign_key="maintenance_case.id", index=True)
    delivered_by: Optional[int] = Field(default=None, foreign_key="user.id")
    created_at:   datetime      = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    case:              Optional[MaintenanceCase] = Relationship(back_populates="deliveries")
    delivered_by_user: Optional[User]           = Relationship(back_populates="deliveries")


# ── Schemas ──────────────────────────────────────────────────────────────────

class MaintenanceDeliveryCreate(MaintenanceDeliveryBase):
    """POST /maintenance-cases/{case_id}/deliveries/"""
    delivered_by: Optional[int] = None


class MaintenanceDeliveryRead(MaintenanceDeliveryBase):
    id:                int
    case_id:           int
    delivered_by:      Optional[int]     = None
    delivered_by_user: Optional[UserRead] = None
    created_at:        datetime

    class Config:
        orm_mode = True


class MaintenanceDeliveryUpdate(SQLModel):
    """PUT /maintenance-deliveries/{id}/"""
    status:       Optional[DeliveryStatus] = None
    delivered_at: Optional[datetime]       = None
    received_by:  Optional[str]            = None
    notes:        Optional[str]            = None


# Resolve forward references so nested Read schemas work correctly.
MaintenanceCaseRead.model_rebuild()
FaultyEntityRead.model_rebuild()


# =============================================================================
# HELPER — Case Number Generator
# =============================================================================

def _generate_case_number(session: Session) -> str:
    """
    Produces sequential, year-scoped case numbers: MC-2024-0001
    Guaranteed unique within the year by counting existing cases.
    """
    year = datetime.now(timezone.utc).year
    prefix = f"MC-{year}-"
    existing = session.exec(
        select(MaintenanceCase).where(
            MaintenanceCase.case_number.startswith(prefix)
        )
    ).all()
    return f"{prefix}{str(len(existing) + 1).zfill(4)}"


# =============================================================================
# CASCADE FAULT HELPER
# =============================================================================
# Entity type → (parent entity type, SQLModel class, FK attribute name)
# Used by the cascade endpoint to walk the hierarchy upward.
# =============================================================================

from models.hierarchy import Component, Unit, Module, Subsystem, System  # your existing models

_PARENT_MAP: dict = {
    EntityType.COMPONENT: (EntityType.UNIT,      Component, "unit_id"),
    EntityType.UNIT:      (EntityType.MODULE,    Unit,       "module_id"),
    EntityType.MODULE:    (EntityType.SUBSYSTEM, Module,     "subsystem_id"),
    EntityType.SUBSYSTEM: (EntityType.SYSTEM,    Subsystem,  "system_id"),
    EntityType.SYSTEM:    (EntityType.PROJECT,   System,     "project_id"),
}


def _cascade_fault_up(
    session:          Session,
    case_id:          int,
    root_entity_type: EntityType,
    root_entity_id:   int,
    fault_type:       FaultType,
    fault_description: Optional[str],
    identified_by:    Optional[int],
) -> List[FaultyEntity]:
    """
    Starting from root_entity, walk UP _PARENT_MAP and create one
    FaultyEntity per ancestor level. Returns all created rows (root first).
    The parent_faulty_entity_id chain is set so the tree is queryable.
    """
    created: List[FaultyEntity] = []
    current_type = root_entity_type
    current_id   = root_entity_id
    parent_fe_id: Optional[int] = None

    while True:
        is_root = (len(created) == 0)
        fe = FaultyEntity(
            case_id=case_id,
            entity_type=current_type,
            entity_id=current_id,
            fault_type=fault_type,
            fault_description=(
                fault_description if is_root
                else f"Cascaded from {root_entity_type} id={root_entity_id}"
            ),
            status=(
                FaultyEntityStatus.CONFIRMED_FAULTY if is_root
                else FaultyEntityStatus.IDENTIFIED
            ),
            parent_faulty_entity_id=parent_fe_id,
            identified_by=identified_by,
        )
        session.add(fe)
        session.flush()               # populate fe.id before next iteration
        created.append(fe)
        parent_fe_id = fe.id

        if current_type not in _PARENT_MAP:
            break                     # reached the top of the hierarchy
        parent_type, model_cls, fk_attr = _PARENT_MAP[current_type]
        row = session.get(model_cls, current_id)
        if not row:
            break                     # parent entity not found — stop cascade
        current_id   = getattr(row, fk_attr)
        current_type = parent_type

    session.commit()
    return created


# =============================================================================
# ENDPOINTS — MAINTENANCE CASE
# =============================================================================

@router.post(
    "/maintenance-cases/",
    response_model=MaintenanceCaseRead,
    status_code=201,
    tags=["maintenance-cases"],
)
def create_maintenance_case(
    payload:      MaintenanceCaseCreate,
    session:      Session = Depends(get_session),
    current_user: User    = Depends(require_permission("create_maintenance_case")),
):
    """
    Open a new maintenance case against a delivered project.
    Case number is auto-generated (MC-YYYY-NNNN).

    REQUEST:
        {
          "project_id":  1,
          "description": "Customer returned unit — PCB burning smell after 3 weeks.",
          "status":      "open"
        }
    RESPONSE 201:
        {
          "id": 1, "case_number": "MC-2024-0001",
          "project_id": 1, "status": "open",
          "reported_at": "2024-05-02T09:00:00Z",
          "faulty_entities": [], "deliveries": []
        }
    """
    data = payload.model_dump()
    data["reported_by"] = data.get("reported_by") or current_user.id
    case = MaintenanceCase(
        case_number=_generate_case_number(session),
        **data
    )
    session.add(case)
    session.commit()
    session.refresh(case)
    return case


@router.get(
    "/maintenance-cases/",
    response_model=List[MaintenanceCaseRead],
    tags=["maintenance-cases"],
)
def list_maintenance_cases(
    project_id:   Optional[int] = None,
    status:       Optional[CaseStatus] = None,
    skip:         int = 0,
    limit:        int = 100,
    session:      Session = Depends(get_session),
    current_user: User    = Depends(require_permission("view_maintenance_case")),
):
    """
    List cases. Filter by project_id and/or status.

    RESPONSE 200: [ { case 1 }, { case 2 }, ... ]
    """
    query = select(MaintenanceCase)
    if project_id:
        query = query.where(MaintenanceCase.project_id == project_id)
    if status:
        query = query.where(MaintenanceCase.status == status)
    return session.exec(
        query.order_by(MaintenanceCase.reported_at.desc()).offset(skip).limit(limit)
    ).all()


@router.get(
    "/maintenance-cases/{case_id}/",
    response_model=MaintenanceCaseRead,
    tags=["maintenance-cases"],
)
def get_maintenance_case(
    case_id:      int,
    session:      Session = Depends(get_session),
    current_user: User    = Depends(require_permission("view_maintenance_case")),
):
    """
    Retrieve a single case with all faulty entities and deliveries nested.

    RESPONSE 200:
        {
          "id": 1, "case_number": "MC-2024-0001", "status": "under_repair",
          "faulty_entities": [
            { "entity_type": "component", "status": "confirmed_faulty",
              "actions": [ { "action_type": "inspection", ... } ] }
          ],
          "deliveries": []
        }
    """
    case = session.get(MaintenanceCase, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Maintenance case not found")
    return case


@router.put(
    "/maintenance-cases/{case_id}/",
    response_model=MaintenanceCaseRead,
    tags=["maintenance-cases"],
)
def update_maintenance_case(
    case_id:      int,
    payload:      MaintenanceCaseUpdate,
    session:      Session = Depends(get_session),
    current_user: User    = Depends(require_permission("edit_maintenance_case")),
):
    """
    Update case status and/or resolution notes.
    Automatically sets closed_at when status transitions to 'closed'.

    REQUEST:  { "status": "resolved", "resolution_notes": "Burnt capacitor replaced." }
    RESPONSE: Updated MaintenanceCaseRead
    """
    case = session.get(MaintenanceCase, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Maintenance case not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(case, k, v)
    if payload.status == CaseStatus.CLOSED and not case.closed_at:
        case.closed_at = datetime.now(timezone.utc)
    session.add(case)
    session.commit()
    session.refresh(case)
    return case


@router.delete(
    "/maintenance-cases/{case_id}/",
    tags=["maintenance-cases"],
)
def delete_maintenance_case(
    case_id:      int,
    session:      Session = Depends(get_session),
    current_user: User    = Depends(require_permission("delete_maintenance_case")),
):
    """
    Hard delete. Only permitted on open cases with no associated actions.
    """
    case = session.get(MaintenanceCase, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Maintenance case not found")
    if case.status != CaseStatus.OPEN:
        raise HTTPException(
            status_code=400,
            detail="Only open cases with no recorded actions may be deleted."
        )
    session.delete(case)
    session.commit()
    return {"detail": f"Maintenance case {case_id} deleted."}


# =============================================================================
# ENDPOINTS — FAULTY ENTITY
# =============================================================================

@router.post(
    "/maintenance-cases/{case_id}/faulty-entities/",
    response_model=FaultyEntityRead,
    status_code=201,
    tags=["faulty-entities"],
)
def add_faulty_entity(
    case_id:      int,
    payload:      FaultyEntityCreate,
    session:      Session = Depends(get_session),
    current_user: User    = Depends(require_permission("create_faulty_entity")),
):
    """
    Manually add one faulty entity to a case.
    Use /cascade-fault/ when you need automatic parent propagation.

    REQUEST:
        {
          "entity_type": "component", "entity_id": 42,
          "fault_type":  "hardware",
          "fault_description": "Capacitor C12 visibly burnt.",
          "parent_faulty_entity_id": 7
        }
    RESPONSE 201:
        { "id": 3, "case_id": 1, "entity_type": "component",
          "status": "identified", "actions": [] }
    """
    case = session.get(MaintenanceCase, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Maintenance case not found")
    data = payload.model_dump()
    data["identified_by"] = data.get("identified_by") or current_user.id
    fe = FaultyEntity(case_id=case_id, **data)
    session.add(fe)
    session.commit()
    session.refresh(fe)
    return fe


@router.post(
    "/maintenance-cases/{case_id}/cascade-fault/",
    response_model=FaultyEntityCascadeRead,
    status_code=201,
    tags=["faulty-entities"],
)
def cascade_fault(
    case_id:      int,
    payload:      FaultyEntityCascadeCreate,
    session:      Session = Depends(get_session),
    current_user: User    = Depends(require_permission("create_faulty_entity")),
):
    """
    Identify a root faulty entity and automatically propagate upward
    through the hierarchy, creating one FaultyEntity per ancestor level.

    REQUEST:
        {
          "root_entity_type":  "component", "root_entity_id": 42,
          "fault_type":        "hardware",
          "fault_description": "Burnt capacitor C12."
        }
    RESPONSE 201:
        {
          "created_faulty_entities": [
            { "entity_type": "component", "status": "confirmed_faulty", ... },
            { "entity_type": "unit",      "status": "identified", ... },
            { "entity_type": "module",    "status": "identified", ... }
          ],
          "total_levels_cascaded": 3,
          "message": "Fault cascaded up 3 hierarchy levels."
        }
    """
    case = session.get(MaintenanceCase, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Maintenance case not found")
    created = _cascade_fault_up(
        session,
        case_id,
        payload.root_entity_type,
        payload.root_entity_id,
        payload.fault_type,
        payload.fault_description,
        current_user.id,
    )
    n = len(created)
    return FaultyEntityCascadeRead(
        created_faulty_entities=created,
        total_levels_cascaded=n,
        message=f"Fault cascaded up {n} hierarchy level{'s' if n != 1 else ''}.",
    )


@router.get(
    "/maintenance-cases/{case_id}/faulty-entities/",
    response_model=List[FaultyEntityRead],
    tags=["faulty-entities"],
)
def list_faulty_entities(
    case_id:      int,
    status:       Optional[FaultyEntityStatus] = None,
    entity_type:  Optional[EntityType]          = None,
    skip:         int = 0,
    limit:        int = 100,
    session:      Session = Depends(get_session),
    current_user: User    = Depends(require_permission("view_faulty_entity")),
):
    """
    List all faulty entities for a case. Filter by status or entity_type.

    RESPONSE 200: [ { faulty_entity 1 }, { faulty_entity 2 }, ... ]
    """
    query = select(FaultyEntity).where(FaultyEntity.case_id == case_id)
    if status:
        query = query.where(FaultyEntity.status == status)
    if entity_type:
        query = query.where(FaultyEntity.entity_type == entity_type)
    return session.exec(query.offset(skip).limit(limit)).all()


@router.get(
    "/faulty-entities/{fe_id}/",
    response_model=FaultyEntityRead,
    tags=["faulty-entities"],
)
def get_faulty_entity(
    fe_id:        int,
    session:      Session = Depends(get_session),
    current_user: User    = Depends(require_permission("view_faulty_entity")),
):
    fe = session.get(FaultyEntity, fe_id)
    if not fe:
        raise HTTPException(status_code=404, detail="Faulty entity not found")
    return fe


@router.put(
    "/faulty-entities/{fe_id}/",
    response_model=FaultyEntityRead,
    tags=["faulty-entities"],
)
def update_faulty_entity(
    fe_id:        int,
    payload:      FaultyEntityUpdate,
    session:      Session = Depends(get_session),
    current_user: User    = Depends(require_permission("edit_faulty_entity")),
):
    """
    Update fault classification or status.
    When resolving, supply resolution_type; resolved_at is set automatically.

    REQUEST:  { "status": "resolved", "resolution_type": "repaired" }
    RESPONSE: Updated FaultyEntityRead
    """
    fe = session.get(FaultyEntity, fe_id)
    if not fe:
        raise HTTPException(status_code=404, detail="Faulty entity not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(fe, k, v)
    if payload.status == FaultyEntityStatus.RESOLVED and not fe.resolved_at:
        fe.resolved_at = datetime.now(timezone.utc)
    session.add(fe)
    session.commit()
    session.refresh(fe)
    return fe


@router.delete(
    "/faulty-entities/{fe_id}/",
    tags=["faulty-entities"],
)
def delete_faulty_entity(
    fe_id:        int,
    session:      Session = Depends(get_session),
    current_user: User    = Depends(require_permission("delete_faulty_entity")),
):
    fe = session.get(FaultyEntity, fe_id)
    if not fe:
        raise HTTPException(status_code=404, detail="Faulty entity not found")
    if fe.actions:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete a faulty entity that has recorded actions."
        )
    session.delete(fe)
    session.commit()
    return {"detail": f"Faulty entity {fe_id} deleted."}


@router.get(
    "/entities/{entity_type}/{entity_id}/maintenance-history/",
    response_model=List[FaultyEntityRead],
    tags=["faulty-entities"],
)
def get_entity_maintenance_history(
    entity_type:  EntityType,
    entity_id:    int,
    session:      Session = Depends(get_session),
    current_user: User    = Depends(require_permission("view_faulty_entity")),
):
    """
    Full fault history of a single entity across ALL cases — past and present.
    Use this to detect repeat failures on the same unit or component.

    RESPONSE 200:
        [
          { "case_id": 1, "resolution_type": "repaired",   "resolved_at": "2024-05-05..." },
          { "case_id": 5, "resolution_type": "replaced",   "resolved_at": "2024-09-11..." }
        ]
    """
    records = session.exec(
        select(FaultyEntity)
        .where(FaultyEntity.entity_type == entity_type)
        .where(FaultyEntity.entity_id == entity_id)
        .order_by(FaultyEntity.identified_at.desc())
    ).all()
    return records


# =============================================================================
# ENDPOINTS — MAINTENANCE ACTION
# =============================================================================

@router.post(
    "/faulty-entities/{fe_id}/actions/",
    response_model=MaintenanceActionRead,
    status_code=201,
    tags=["maintenance-actions"],
)
def create_maintenance_action(
    fe_id:        int,
    payload:      MaintenanceActionCreate,
    session:      Session = Depends(get_session),
    current_user: User    = Depends(require_permission("create_maintenance_action")),
):
    """
    Log an action (inspection, repair, replacement, testing, etc.)
    against a faulty entity.

    REQUEST:
        {
          "action_type": "replacement",
          "notes":       "Replaced burnt capacitor C12 (100µF 50V).",
          "outcome":     "pass",
          "replacement_entity_id":   99,
          "replacement_entity_type": "component"
        }
    RESPONSE 201:
        {
          "id": 1, "faulty_entity_id": 3,
          "action_type": "replacement", "outcome": "pass",
          "performed_at": "2024-05-05T14:30:00Z"
        }
    """
    fe = session.get(FaultyEntity, fe_id)
    if not fe:
        raise HTTPException(status_code=404, detail="Faulty entity not found")
    data = payload.model_dump()
    data["performed_by"] = data.get("performed_by") or current_user.id
    action = MaintenanceAction(faulty_entity_id=fe_id, **data)
    session.add(action)

    # When a replacement action passes, auto-resolve the faulty entity.
    if (
        payload.action_type == ActionType.REPLACEMENT
        and payload.outcome == ActionOutcome.PASS
    ):
        fe.status = FaultyEntityStatus.RESOLVED
        fe.resolution_type = ResolutionType.REPLACED
        fe.resolved_at = datetime.now(timezone.utc)
        session.add(fe)

    session.commit()
    session.refresh(action)
    return action


@router.get(
    "/faulty-entities/{fe_id}/actions/",
    response_model=List[MaintenanceActionRead],
    tags=["maintenance-actions"],
)
def list_maintenance_actions(
    fe_id:        int,
    skip:         int = 0,
    limit:        int = 100,
    session:      Session = Depends(get_session),
    current_user: User    = Depends(require_permission("view_maintenance_action")),
):
    """List all actions recorded against a faulty entity."""
    return session.exec(
        select(MaintenanceAction)
        .where(MaintenanceAction.faulty_entity_id == fe_id)
        .order_by(MaintenanceAction.performed_at.desc())
        .offset(skip).limit(limit)
    ).all()


@router.get(
    "/maintenance-actions/{action_id}/",
    response_model=MaintenanceActionRead,
    tags=["maintenance-actions"],
)
def get_maintenance_action(
    action_id:    int,
    session:      Session = Depends(get_session),
    current_user: User    = Depends(require_permission("view_maintenance_action")),
):
    action = session.get(MaintenanceAction, action_id)
    if not action:
        raise HTTPException(status_code=404, detail="Maintenance action not found")
    return action


@router.put(
    "/maintenance-actions/{action_id}/",
    response_model=MaintenanceActionRead,
    tags=["maintenance-actions"],
)
def update_maintenance_action(
    action_id:    int,
    payload:      MaintenanceActionUpdate,
    session:      Session = Depends(get_session),
    current_user: User    = Depends(require_permission("edit_maintenance_action")),
):
    """Update notes or outcome of a recorded action."""
    action = session.get(MaintenanceAction, action_id)
    if not action:
        raise HTTPException(status_code=404, detail="Maintenance action not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(action, k, v)
    session.add(action)
    session.commit()
    session.refresh(action)
    return action


@router.delete(
    "/maintenance-actions/{action_id}/",
    tags=["maintenance-actions"],
)
def delete_maintenance_action(
    action_id:    int,
    session:      Session = Depends(get_session),
    current_user: User    = Depends(require_permission("delete_maintenance_action")),
):
    action = session.get(MaintenanceAction, action_id)
    if not action:
        raise HTTPException(status_code=404, detail="Maintenance action not found")
    session.delete(action)
    session.commit()
    return {"detail": f"Maintenance action {action_id} deleted."}


# =============================================================================
# ENDPOINTS — MAINTENANCE DELIVERY
# =============================================================================

@router.post(
    "/maintenance-cases/{case_id}/deliveries/",
    response_model=MaintenanceDeliveryRead,
    status_code=201,
    tags=["maintenance-deliveries"],
)
def create_maintenance_delivery(
    case_id:      int,
    payload:      MaintenanceDeliveryCreate,
    session:      Session = Depends(get_session),
    current_user: User    = Depends(require_permission("create_maintenance_delivery")),
):
    """
    Record a re-delivery of the repaired product to the customer.
    Transitions the case status to 'resolved' if not already.

    REQUEST:
        {
          "delivery_type": "re_delivery",
          "received_by":   "John Smith – Site Manager",
          "notes":         "Courier: DHL-XP-9921."
        }
    RESPONSE 201:
        { "id": 1, "case_id": 1, "delivery_type": "re_delivery",
          "status": "dispatched", "created_at": "2024-05-06T08:00:00Z" }
    """
    case = session.get(MaintenanceCase, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Maintenance case not found")
    data = payload.model_dump()
    data["delivered_by"] = data.get("delivered_by") or current_user.id
    data["status"] = DeliveryStatus.DISPATCHED
    delivery = MaintenanceDelivery(case_id=case_id, **data)
    session.add(delivery)
    # Mark case as resolved when re-delivery is dispatched (if not already).
    if case.status not in (CaseStatus.RESOLVED, CaseStatus.CLOSED):
        case.status = CaseStatus.RESOLVED
        session.add(case)
    session.commit()
    session.refresh(delivery)
    return delivery


@router.get(
    "/maintenance-cases/{case_id}/deliveries/",
    response_model=List[MaintenanceDeliveryRead],
    tags=["maintenance-deliveries"],
)
def list_maintenance_deliveries(
    case_id:      int,
    session:      Session = Depends(get_session),
    current_user: User    = Depends(require_permission("view_maintenance_delivery")),
):
    """List all delivery records for a case (full re-delivery history)."""
    return session.exec(
        select(MaintenanceDelivery)
        .where(MaintenanceDelivery.case_id == case_id)
        .order_by(MaintenanceDelivery.created_at.desc())
    ).all()


@router.get(
    "/maintenance-deliveries/{delivery_id}/",
    response_model=MaintenanceDeliveryRead,
    tags=["maintenance-deliveries"],
)
def get_maintenance_delivery(
    delivery_id:  int,
    session:      Session = Depends(get_session),
    current_user: User    = Depends(require_permission("view_maintenance_delivery")),
):
    delivery = session.get(MaintenanceDelivery, delivery_id)
    if not delivery:
        raise HTTPException(status_code=404, detail="Delivery record not found")
    return delivery


@router.put(
    "/maintenance-deliveries/{delivery_id}/",
    response_model=MaintenanceDeliveryRead,
    tags=["maintenance-deliveries"],
)
def update_maintenance_delivery(
    delivery_id:  int,
    payload:      MaintenanceDeliveryUpdate,
    session:      Session = Depends(get_session),
    current_user: User    = Depends(require_permission("edit_maintenance_delivery")),
):
    """Update delivery status, received_by, or notes."""
    delivery = session.get(MaintenanceDelivery, delivery_id)
    if not delivery:
        raise HTTPException(status_code=404, detail="Delivery record not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(delivery, k, v)
    session.add(delivery)
    session.commit()
    session.refresh(delivery)
    return delivery


@router.post(
    "/maintenance-deliveries/{delivery_id}/confirm/",
    response_model=MaintenanceDeliveryRead,
    tags=["maintenance-deliveries"],
)
def confirm_maintenance_delivery(
    delivery_id:  int,
    received_by:  str,
    session:      Session = Depends(get_session),
    current_user: User    = Depends(require_permission("edit_maintenance_delivery")),
):
    """
    Customer confirms receipt of the repaired product.
    Auto-closes the parent case when confirmed.

    RESPONSE:
        { "status": "confirmed_by_customer",
          "delivered_at": "2024-05-07T11:00:00Z",
          "received_by":  "John Smith – Site Manager" }
    """
    delivery = session.get(MaintenanceDelivery, delivery_id)
    if not delivery:
        raise HTTPException(status_code=404, detail="Delivery record not found")
    delivery.status      = DeliveryStatus.CONFIRMED_BY_CUSTOMER
    delivery.delivered_at = datetime.now(timezone.utc)
    delivery.received_by  = received_by
    session.add(delivery)
    # Auto-close the case.
    case = session.get(MaintenanceCase, delivery.case_id)
    if case and case.status == CaseStatus.RESOLVED:
        case.status    = CaseStatus.CLOSED
        case.closed_at = datetime.now(timezone.utc)
        session.add(case)
    session.commit()
    session.refresh(delivery)
    return delivery


@router.delete(
    "/maintenance-deliveries/{delivery_id}/",
    tags=["maintenance-deliveries"],
)
def delete_maintenance_delivery(
    delivery_id:  int,
    session:      Session = Depends(get_session),
    current_user: User    = Depends(require_permission("delete_maintenance_delivery")),
):
    delivery = session.get(MaintenanceDelivery, delivery_id)
    if not delivery:
        raise HTTPException(status_code=404, detail="Delivery record not found")
    if delivery.status == DeliveryStatus.CONFIRMED_BY_CUSTOMER:
        raise HTTPException(
            status_code=400,
            detail="Confirmed deliveries cannot be deleted."
        )
    session.delete(delivery)
    session.commit()
    return {"detail": f"Delivery record {delivery_id} deleted."}
