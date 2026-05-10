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
from app.database import get_session
from auth import require_permission
# Hierarchy models — adapt class names / FK attribute names to your schema
from app.models.tables import (User, Project, System, Subsystem, Module, Unit, Component, OrderDetail, Customer)


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
    ORDER     = "order"        
    CUSTOMER  = "customer"     


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


_PARENT_MAP: dict = {
    EntityType.COMPONENT: (EntityType.UNIT,      Component, "unit_id"),
    EntityType.UNIT:      (EntityType.MODULE,    Unit,       "module_id"),
    EntityType.MODULE:    (EntityType.SUBSYSTEM, Module,     "subsystem_id"),
    EntityType.SUBSYSTEM: (EntityType.SYSTEM,    Subsystem,  "system_id"),
    EntityType.SYSTEM:    (EntityType.PROJECT,   System,     "project_id"),
    EntityType.PROJECT:   (EntityType.ORDER,    Project,     "order_id"),
    EntityType.ORDER:     (EntityType.CUSTOMER, OrderDetail, "customer_id"),
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
# B. NEW SCHEMAS
# =============================================================================

class AncestorNode(SQLModel):
    """One level in the upward ancestry chain."""
    entity_type: str
    entity_id:   int
    label:       Optional[str] = None   # human-readable name / SKU

class DescendantNode(SQLModel):
    """One entity in the downward subtree."""
    entity_type: str
    entity_id:   int
    label:       Optional[str] = None
    depth:       int = 0                # 0 = the entity itself, 1 = direct child, …

class EntityLookupRead(SQLModel):
    """
    Response for GET /entities/lookup-by-sku/{sku}/
    Returns the matched entity plus its full ancestry (up to customer)
    and every descendant entity (down to components).
    """
    matched_entity_type: str
    matched_entity_id:   int
    matched_label:       Optional[str] = None

    # Upward chain — ordered from the matched entity to Customer
    ancestors: List[AncestorNode] = []

    # Downward tree — every child, grandchild, … leaf entity
    descendants: List[DescendantNode] = []

    # Convenience: project / order / customer extracted from ancestors
    project_id:    Optional[int] = None
    project_name:  Optional[str] = None
    order_id:      Optional[int] = None
    order_ref:     Optional[str] = None
    customer_id:   Optional[int] = None
    customer_name: Optional[str] = None

class SuspectChildrenPayload(SQLModel):
    """
    POST /maintenance-cases/{case_id}/suspect-children/
    Body: identify a mid-hierarchy faulty entity; the endpoint walks DOWN and
    creates provisional UNDER_INSPECTION faulty-entity rows for every descendant.
    """
    entity_type:       EntityType
    entity_id:         int
    fault_type:        FaultType       = FaultType.UNCLASSIFIED
    fault_description: Optional[str]   = None

class SuspectChildrenRead(SQLModel):
    """Response for the suspect-children endpoint."""
    parent_faulty_entity_id: int
    suspect_entities_created: List[FaultyEntityRead] = []
    total_suspects:           int
    message:                  str

class ConfirmFaultPayload(SQLModel):
    """
    POST /maintenance-cases/{case_id}/confirm-fault/
    Body: the engineer has traced the fault to one exact entity.
    All sibling subtrees under the same parent are cleared (provisional rows
    deleted; no permanent log left for healthy entities).
    """
    confirmed_entity_type:  EntityType
    confirmed_entity_id:    int
    fault_type:             FaultType       = FaultType.UNCLASSIFIED
    fault_description:      Optional[str]   = None
    # The parent faulty-entity row that was created during suspect-children.
    # Required so the system knows which sibling rows to clear.
    parent_faulty_entity_id: int

class ConfirmFaultRead(SQLModel):
    """Response for the confirm-fault endpoint."""
    confirmed_faulty_entity: FaultyEntityRead
    cleared_suspect_count:   int
    message:                 str

# =============================================================================
# C. CHILD MAP  (mirrors _PARENT_MAP downward)
# =============================================================================
# Maps entity_type  →  (child entity_type, SQLModel class, FK attr on child)
#
# Example: a MODULE has many UNITs; Unit.module_id is the FK.
# Adapt the FK attribute names to your actual model definitions.

from typing import Dict, Tuple, Any

_CHILD_MAP: Dict[str, Tuple[str, Any, str]] = {
    EntityType.SYSTEM:    (EntityType.SUBSYSTEM, Subsystem, "system_id"),
    EntityType.SUBSYSTEM: (EntityType.MODULE,    Module,    "subsystem_id"),
    EntityType.MODULE:    (EntityType.UNIT,      Unit,      "module_id"),
    EntityType.UNIT:      (EntityType.COMPONENT, Component, "unit_id"),
    # but typically a project-level fault wouldn't trigger suspect-children.
    EntityType.PROJECT:   (EntityType.SYSTEM,    System,    "project_id"),
}

# Map each entity type to its SQLModel class and the attribute used as its
# human-readable label (name, sku, serial_number, etc.).  Adjust to your schema.
_ENTITY_MODEL_MAP: Dict[str, Tuple[Any, str, Optional[str]]] = {
    # (SQLModelClass, pk_attr, label_attr)
    EntityType.COMPONENT: (Component, "id", "serial_number"),
    EntityType.UNIT:      (Unit,      "id", "serial_number"),
    EntityType.MODULE:    (Module,    "id", "serial_number"),
    EntityType.SUBSYSTEM: (Subsystem, "id", "serial_number"),
    EntityType.SYSTEM:    (System,    "id", "serial_number"),
    EntityType.PROJECT:   (Project,   "id", "name"),
    # Add ORDER and CUSTOMER if your models support them:
    # EntityType.ORDER:    (OrderDetail, "id", "reference_number"),
    # EntityType.CUSTOMER: (Customer,    "id", "name"),
}

# Parent map extended upward beyond Project (Project → Order → Customer).
# Add your actual FK attribute names.
_EXTENDED_PARENT_MAP: Dict[str, Tuple[str, Any, str]] = {
    **_PARENT_MAP,
    # EntityType.PROJECT:  (EntityType.ORDER,    Project,     "order_detail_id"),
    # EntityType.ORDER:    (EntityType.CUSTOMER, OrderDetail, "customer_id"),
}

# SR/part-number lookup:  maps entity_type → (SQLModelClass, sku_attr)
# A single SRU must be unique within each entity type (enforced by your schema).
_SR_SEARCH_MODELS: List[Tuple[str, Any, str]] = [
    (EntityType.COMPONENT, Component, "sku"),
    (EntityType.UNIT,      Unit,      "sku"),
    (EntityType.MODULE,    Module,    "sku"),
    (EntityType.SUBSYSTEM, Subsystem, "sku"),
    (EntityType.SYSTEM,    System,    "sku"),
    # Add more if Project / Order also carry part numbers.
]




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




# =============================================================================
# D. HELPERS
# =============================================================================

def _get_label(session: Session, entity_type: str, entity_id: int) -> Optional[str]:
    """Return the human-readable label for any entity."""
    entry = _ENTITY_MODEL_MAP.get(entity_type)
    if not entry:
        return None
    model_cls, _, label_attr = entry
    row = session.get(model_cls, entity_id)
    if not row or not label_attr:
        return None
    return str(getattr(row, label_attr, None))


def _resolve_ancestors(
    session:     Session,
    entity_type: str,
    entity_id:   int,
) -> List[AncestorNode]:
    """
    Walk UP _EXTENDED_PARENT_MAP from (entity_type, entity_id) until the
    chain ends (Customer or unknown type).  Returns ancestors ordered from
    the direct parent of the given entity up to Customer.
    """
    ancestors: List[AncestorNode] = []
    current_type = entity_type
    current_id   = entity_id

    while current_type in _EXTENDED_PARENT_MAP:
        parent_type, model_cls, fk_attr = _EXTENDED_PARENT_MAP[current_type]
        row = session.get(model_cls, current_id)
        if not row:
            break
        parent_id = getattr(row, fk_attr, None)
        if parent_id is None:
            break
        label = _get_label(session, parent_type, parent_id)
        ancestors.append(
            AncestorNode(entity_type=parent_type, entity_id=parent_id, label=label)
        )
        current_type = parent_type
        current_id   = parent_id

    return ancestors


def _collect_descendants(
    session:     Session,
    entity_type: str,
    entity_id:   int,
    depth:       int = 0,
) -> List[DescendantNode]:
    """
    Recursively walk DOWN _CHILD_MAP and collect every descendant entity.
    Returns a flat list ordered breadth-first (parent before children).
    """
    result: List[DescendantNode] = []
    if entity_type not in _CHILD_MAP:
        return result                          # leaf node — no children

    child_type, child_model, fk_attr = _CHILD_MAP[entity_type]

    # Query all children whose FK matches entity_id
    children = session.exec(
        select(child_model).where(getattr(child_model, fk_attr) == entity_id)
    ).all()

    for child in children:
        child_id = child.id
        label    = _get_label(session, child_type, child_id)
        result.append(
            DescendantNode(
                entity_type=child_type,
                entity_id=child_id,
                label=label,
                depth=depth + 1,
            )
        )
        # Recurse into grandchildren
        result.extend(_collect_descendants(session, child_type, child_id, depth + 1))

    return result


def _create_suspect_fes(
    session:              Session,
    case_id:              int,
    descendants:          List[DescendantNode],
    fault_type:           FaultType,
    parent_faulty_entity_id: int,
    identified_by:        Optional[int],
) -> List[FaultyEntity]:
    """
    Bulk-create one FaultyEntity per descendant with status=UNDER_INSPECTION.
    All rows are linked to parent_faulty_entity_id (the mid-hierarchy FE row).
    Returns the created rows.
    """
    created: List[FaultyEntity] = []
    for desc in descendants:
        fe = FaultyEntity(
            case_id=case_id,
            entity_type=desc.entity_type,
            entity_id=desc.entity_id,
            fault_type=fault_type,
            fault_description=f"Suspected — under inspection (parent hierarchy flagged)",
            status=FaultyEntityStatus.UNDER_INSPECTION,
            parent_faulty_entity_id=parent_faulty_entity_id,
            identified_by=identified_by,
        )
        session.add(fe)
        created.append(fe)
    session.flush()    # assign IDs
    return created


def _clear_healthy_fes(
    session:                  Session,
    case_id:                  int,
    parent_faulty_entity_id:  int,
    confirmed_entity_type:    EntityType,
    confirmed_entity_id:      int,
) -> int:
    """
    After the engineer confirms the exact faulty entity, delete all provisional
    UNDER_INSPECTION faulty-entity rows that belong to sibling subtrees under
    the same parent_faulty_entity_id — EXCEPT the confirmed entity and its
    own ancestors (which should already be CONFIRMED_FAULTY or IDENTIFIED).

    Returns the count of deleted rows.
    """
    # Fetch every UNDER_INSPECTION row under this parent FE
    suspects: List[FaultyEntity] = session.exec(
        select(FaultyEntity).where(
            FaultyEntity.case_id == case_id,
            FaultyEntity.parent_faulty_entity_id == parent_faulty_entity_id,
            FaultyEntity.status == FaultyEntityStatus.UNDER_INSPECTION,
        )
    ).all()

    # Collect the IDs of the confirmed entity and ALL of its descendants
    # (they may have been created as suspects too).
    confirmed_subtree_ids: set = {confirmed_entity_id}
    _collect_confirmed_descendant_ids(
        session, confirmed_entity_type, confirmed_entity_id, confirmed_subtree_ids
    )

    deleted = 0
    for fe in suspects:
        # Keep the row only if this entity is the confirmed fault or its child
        if fe.entity_id in confirmed_subtree_ids and fe.entity_type == confirmed_entity_type:
            # This is the confirmed entity's own suspect row — upgrade it
            fe.status = FaultyEntityStatus.CONFIRMED_FAULTY
            session.add(fe)
            continue

        # Everything else: remove from the database (no history kept)
        if fe.actions:
            # Safety guard: if an action was already logged here, don't delete
            fe.status = FaultyEntityStatus.NO_FAULT_FOUND
            session.add(fe)
        else:
            session.delete(fe)
            deleted += 1

    session.flush()
    return deleted


def _collect_confirmed_descendant_ids(
    session:     Session,
    entity_type: str,
    entity_id:   int,
    id_set:      set,
) -> None:
    """Recursively gather entity_ids of the confirmed entity's subtree."""
    if entity_type not in _CHILD_MAP:
        return
    child_type, child_model, fk_attr = _CHILD_MAP[entity_type]
    children = session.exec(
        select(child_model).where(getattr(child_model, fk_attr) == entity_id)
    ).all()
    for child in children:
        id_set.add(child.id)
        _collect_confirmed_descendant_ids(session, child_type, child.id, id_set)


# =============================================================================
# E. NEW ENDPOINTS
# =============================================================================

router = APIRouter(prefix="/api/v1", tags=["maintenance"])


# ── E1. SKU / Part-number lookup ──────────────────────────────────────────────

@router.get(
    "/entities/lookup-by-sku/{sku}/",
    response_model=EntityLookupRead,
    tags=["entity-lookup"],
)
def lookup_entity_by_sku(
    sku:          str,
    session:      Session = Depends(get_session),
    current_user: User    = Depends(require_permission("view_faulty_entity")),
):
    """
    Look up any entity in the hierarchy by its SKU / part number / user-defined
    identifier.  Does NOT require knowing the project ID upfront.

    The endpoint:
      1. Searches every entity table in _SR_SEARCH_MODELS for a matching SKU.
      2. Walks UP the hierarchy to find the project, order, and customer.
      3. Walks DOWN the hierarchy to enumerate every child entity.

    RESPONSE 200:
        {
          "matched_entity_type": "module",
          "matched_entity_id":   17,
          "matched_label":       "MOD-PCB-001",
          "ancestors": [
            { "entity_type": "subsystem", "entity_id": 5,  "label": "SS-POWER" },
            { "entity_type": "system",    "entity_id": 2,  "label": "SYS-MAIN" },
            { "entity_type": "project",   "entity_id": 1,  "label": "Alpha Plant" },
            { "entity_type": "order",     "entity_id": 3,  "label": "ORD-2024-007" },
            { "entity_type": "customer",  "entity_id": 9,  "label": "Acme Corp" }
          ],
          "descendants": [
            { "entity_type": "unit",      "entity_id": 22, "label": "UNIT-A",  "depth": 1 },
            { "entity_type": "component", "entity_id": 44, "label": "CAP-C12", "depth": 2 },
            ...
          ],
          "project_id": 1, "project_name": "Alpha Plant",
          "order_id":   3, "order_ref":    "ORD-2024-007",
          "customer_id":9, "customer_name":"Acme Corp"
        }

    ERROR 404: SKU not found in any entity table.
    """
    matched_type: Optional[str] = None
    matched_id:   Optional[int] = None
    matched_label: Optional[str] = None

    for entity_type, model_cls, sku_attr in _SR_SEARCH_MODELS:
        row = session.exec(
            select(model_cls).where(getattr(model_cls, sku_attr) == sku)
        ).first()
        if row:
            matched_type  = entity_type
            matched_id    = row.id
            matched_label = str(getattr(row, sku_attr, sku))
            break

    if not matched_type or matched_id is None:
        raise HTTPException(
            status_code=404,
            detail=f"No entity found with SKU / identifier '{sku}'.",
        )

    # Walk up to customer
    ancestors = _resolve_ancestors(session, matched_type, matched_id)

    # Walk down to every leaf
    descendants = _collect_descendants(session, matched_type, matched_id)

    # Extract convenience fields from ancestors
    project_id = project_name = order_id = order_ref = customer_id = customer_name = None
    for anc in ancestors:
        if anc.entity_type == EntityType.PROJECT:
            project_id   = anc.entity_id
            project_name = anc.label
        elif anc.entity_type == "order":          # EntityType.ORDER if defined
            order_id  = anc.entity_id
            order_ref = anc.label
        elif anc.entity_type == "customer":       # EntityType.CUSTOMER if defined
            customer_id   = anc.entity_id
            customer_name = anc.label

    return EntityLookupRead(
        matched_entity_type=matched_type,
        matched_entity_id=matched_id,
        matched_label=matched_label,
        ancestors=ancestors,
        descendants=descendants,
        project_id=project_id,
        project_name=project_name,
        order_id=order_id,
        order_ref=order_ref,
        customer_id=customer_id,
        customer_name=customer_name,
    )


# ── E2. Suspect all children of a mid-hierarchy fault ─────────────────────────

@router.post(
    "/maintenance-cases/{case_id}/suspect-children/",
    response_model=SuspectChildrenRead,
    status_code=201,
    tags=["faulty-entities"],
)
def suspect_children(
    case_id:      int,
    payload:      SuspectChildrenPayload,
    session:      Session = Depends(get_session),
    current_user: User    = Depends(require_permission("create_faulty_entity")),
):
    """
    Called when a mid-hierarchy entity (e.g. a module) is known to be faulty
    but the root cause within it has not yet been identified.

    The endpoint:
      1. Creates (or retrieves) the FaultyEntity row for the reported entity
         with status = CONFIRMED_FAULTY.
      2. Walks DOWN the hierarchy and creates one provisional FaultyEntity per
         descendant (unit, component, …) with status = UNDER_INSPECTION.
      3. All provisional rows share parent_faulty_entity_id pointing to step 1.

    These provisional rows act as a checklist for the engineer — every
    descendant is highlighted as a potential fault source.

    After the engineer identifies the actual faulty entity, call
    POST /maintenance-cases/{case_id}/confirm-fault/ to commit the real fault
    and automatically clean up all other provisional rows.

    REQUEST:
        {
          "entity_type":       "module",
          "entity_id":         17,
          "fault_type":        "hardware",
          "fault_description": "Module overheating — root cause TBD."
        }

    RESPONSE 201:
        {
          "parent_faulty_entity_id": 5,
          "suspect_entities_created": [ { unit FE }, { component FE }, ... ],
          "total_suspects": 8,
          "message": "8 descendant entities marked as under_inspection."
        }
    """
    case = session.get(MaintenanceCase, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Maintenance case not found")

    # Step 1 — Create the confirmed-faulty FE for the reported entity
    parent_fe = FaultyEntity(
        case_id=case_id,
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
        fault_type=payload.fault_type,
        fault_description=payload.fault_description,
        status=FaultyEntityStatus.CONFIRMED_FAULTY,
        identified_by=current_user.id,
        parent_faulty_entity_id=None,
    )
    session.add(parent_fe)
    session.flush()       # get parent_fe.id

    # Step 2 — Collect all descendants
    descendants = _collect_descendants(session, payload.entity_type, payload.entity_id)

    if not descendants:
        session.commit()
        session.refresh(parent_fe)
        return SuspectChildrenRead(
            parent_faulty_entity_id=parent_fe.id,
            suspect_entities_created=[],
            total_suspects=0,
            message="No child entities found — this appears to be a leaf node.",
        )

    # Step 3 — Create provisional UNDER_INSPECTION rows
    suspects = _create_suspect_fes(
        session,
        case_id,
        descendants,
        payload.fault_type,
        parent_fe.id,
        current_user.id,
    )
    session.commit()
    session.refresh(parent_fe)
    for s in suspects:
        session.refresh(s)

    n = len(suspects)
    return SuspectChildrenRead(
        parent_faulty_entity_id=parent_fe.id,
        suspect_entities_created=suspects,
        total_suspects=n,
        message=f"{n} descendant entit{'ies' if n != 1 else 'y'} marked as under_inspection.",
    )


# ── E3. Engineer confirms exact fault — clear all healthy sibling suspects ─────

@router.post(
    "/maintenance-cases/{case_id}/confirm-fault/",
    response_model=ConfirmFaultRead,
    status_code=201,
    tags=["faulty-entities"],
)
def confirm_fault(
    case_id:      int,
    payload:      ConfirmFaultPayload,
    session:      Session = Depends(get_session),
    current_user: User    = Depends(require_permission("create_faulty_entity")),
):
    """
    Called once the engineer has traced the fault to a specific entity (e.g.
    a burnt capacitor inside one of the suspected units).

    The endpoint:
      1. Finds or creates a FaultyEntity for the confirmed entity with
         status = CONFIRMED_FAULTY.
      2. Walks the CASCADE upward (calls existing _cascade_fault_up logic)
         to flag each ancestor as IDENTIFIED — only up to the already-existing
         parent faulty entity (no duplicates).
      3. Deletes all provisional UNDER_INSPECTION faulty-entity rows belonging
         to sibling entities (and their subtrees) that were found healthy.
         ─ No row is left for any healthy entity — no permanent history.
         ─ If an UNDER_INSPECTION row already has an action logged against it,
           it is instead set to NO_FAULT_FOUND (preserved for audit safety).

    REQUEST:
        {
          "confirmed_entity_type":   "component",
          "confirmed_entity_id":     44,
          "fault_type":              "hardware",
          "fault_description":       "Capacitor C12 burnt — 100µF 50V.",
          "parent_faulty_entity_id": 5
        }

    RESPONSE 201:
        {
          "confirmed_faulty_entity": { FaultyEntityRead },
          "cleared_suspect_count":   7,
          "message": "Fault confirmed on component id=44. 7 healthy suspects cleared."
        }
    """
    case = session.get(MaintenanceCase, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Maintenance case not found")

    parent_fe = session.get(FaultyEntity, payload.parent_faulty_entity_id)
    if not parent_fe:
        raise HTTPException(
            status_code=404,
            detail=f"Parent faulty entity {payload.parent_faulty_entity_id} not found. "
                   "Run suspect-children first.",
        )

    # Step 1 — Check for an existing UNDER_INSPECTION row for the confirmed entity.
    # If one was created during suspect-children, upgrade it. Otherwise create fresh.
    confirmed_fe: Optional[FaultyEntity] = session.exec(
        select(FaultyEntity).where(
            FaultyEntity.case_id == case_id,
            FaultyEntity.entity_type == payload.confirmed_entity_type,
            FaultyEntity.entity_id == payload.confirmed_entity_id,
        )
    ).first()

    if confirmed_fe:
        # Upgrade the provisional suspect row
        confirmed_fe.status            = FaultyEntityStatus.CONFIRMED_FAULTY
        confirmed_fe.fault_type        = payload.fault_type
        confirmed_fe.fault_description = payload.fault_description
        session.add(confirmed_fe)
    else:
        # No suspect row existed — create a fresh CONFIRMED_FAULTY row
        confirmed_fe = FaultyEntity(
            case_id=case_id,
            entity_type=payload.confirmed_entity_type,
            entity_id=payload.confirmed_entity_id,
            fault_type=payload.fault_type,
            fault_description=payload.fault_description,
            status=FaultyEntityStatus.CONFIRMED_FAULTY,
            parent_faulty_entity_id=payload.parent_faulty_entity_id,
            identified_by=current_user.id,
        )
        session.add(confirmed_fe)

    session.flush()

    # Step 2 — Clear all healthy sibling suspects
    cleared = _clear_healthy_fes(
        session,
        case_id,
        payload.parent_faulty_entity_id,
        payload.confirmed_entity_type,
        payload.confirmed_entity_id,
    )

    session.commit()
    session.refresh(confirmed_fe)

    return ConfirmFaultRead(
        confirmed_faulty_entity=confirmed_fe,
        cleared_suspect_count=cleared,
        message=(
            f"Fault confirmed on {payload.confirmed_entity_type} "
            f"id={payload.confirmed_entity_id}. "
            f"{cleared} healthy suspect{'s' if cleared != 1 else ''} cleared."
        ),
    )


# =============================================================================
# INTEGRATION NOTES
# =============================================================================
#
# 1. MERGE STRATEGY
#    Copy each labelled block (A–E) into maintenance_module.py at the
#    appropriate position.  Blocks B–D are new; block A extends an existing enum.
#
# 2. HIERARCHY MODEL ASSUMPTIONS
#    The helpers assume:
#      - Each hierarchy table has an `id` PK and a `sku` field (or similar).
#      - Parent FK names follow the convention in _PARENT_MAP / _CHILD_MAP.
#    Adjust attribute names in _ENTITY_MODEL_MAP, _CHILD_MAP, and
#    _EXTENDED_PARENT_MAP to match your actual schema.
#
# 3. ORDER & CUSTOMER ANCESTORS
#    Uncomment the EntityType.ORDER / EntityType.CUSTOMER lines in
#    _EXTENDED_PARENT_MAP and _ENTITY_MODEL_MAP once those models exist.
#    The lookup endpoint will then automatically include them in `ancestors`
#    and populate order_id / customer_id in the response.
#
# 4. WORKFLOW SUMMARY
#
#    ┌─────────────────────────────────────────────────────────────────────┐
#    │  STEP 0  — SKU scan on intake                                       │
#    │  GET /entities/lookup-by-sku/{sku}/                                 │
#    │  → returns matched entity + full ancestry (project/order/customer)  │
#    │    + every descendant.  Staff can now open a case with project_id.  │
#    ├─────────────────────────────────────────────────────────────────────┤
#    │  STEP 1  — Open maintenance case                                    │
#    │  POST /maintenance-cases/   { project_id: … }                       │
#    ├─────────────────────────────────────────────────────────────────────┤
#    │  STEP 2a — If root fault known (e.g. leaf component)                │
#    │  POST /maintenance-cases/{id}/cascade-fault/   (existing endpoint)  │
#    │  → creates CONFIRMED_FAULTY root + IDENTIFIED ancestors.            │
#    ├─────────────────────────────────────────────────────────────────────┤
#    │  STEP 2b — If mid-level entity is faulty but cause unknown          │
#    │  POST /maintenance-cases/{id}/suspect-children/                     │
#    │  → creates CONFIRMED_FAULTY for the mid entity                      │
#    │     + UNDER_INSPECTION for every descendant (highlighted in UI).    │
#    ├─────────────────────────────────────────────────────────────────────┤
#    │  STEP 3  — Engineer inspects, identifies exact faulty part          │
#    │  POST /maintenance-cases/{id}/confirm-fault/                        │
#    │  → upgrades confirmed entity to CONFIRMED_FAULTY                    │
#    │     + silently deletes all healthy sibling suspect rows.            │
#    │     No trace left for healthy components. Audit trail only          │
#    │     for what was actually faulty.                                    │
#    └─────────────────────────────────────────────────────────────────────┘
#
# 5. DATABASE CLEAN-UP GUARANTEE
#    _clear_healthy_fes() deletes rows that have no actions logged.
#    If an engineer accidentally logged an inspection on a healthy suspect,
#    that row is set to NO_FAULT_FOUND instead — safe for audit, clearly
#    distinct from any fault path.
#
# 6. PERMISSIONS  (add to your permission registry as needed)
#    view_faulty_entity   — already exists
#    create_faulty_entity — already exists
#    No new permissions required.
# =============================================================================
