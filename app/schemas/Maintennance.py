from sqlmodel import SQLModel, Field
from app.models.base import (MaintenanceCaseBase, FaultyEntityBase, MaintenanceActionBase, MaintenanceDeliveryBase)
from typing import List, Optional
from app.models.base import EntityType, FaultType, CaseStatus, FaultyEntityStatus, ResolutionType, ActionOutcome, DeliveryStatus
from .schemas import UserRead
from datetime import datetime

# =============================================================================
# B. NEW SCHEMAS
# =============================================================================

class AncestorNode(SQLModel):
    """One level in the upward ancestry chain."""
    entity_type: str
    entity_id:   int
    label:       Optional[str] = None   # human-readable name / PN

class DescendantNode(SQLModel):
    """One entity in the downward subtree."""
    entity_type: str
    entity_id:   int
    label:       Optional[str] = None
    depth:       int = 0                # 0 = the entity itself, 1 = direct child, …

class EntityLookupRead(SQLModel):
    """
    Response for GET /entities/lookup-by-PN/{PN}/
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
    entity_name:       Optional[str]   = None  # for FE label; optional but saves a lookup
    entity_name : Optional[str]   = None
    serial_number : Optional[str]   = None
    part_number : Optional[str]   = None

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
# 1. MAINTENANCE CASE
# =============================================================================
# A top-level fault event opened against a delivered project.
# One project can accumulate many cases over its lifetime.
# =============================================================================


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

# ── Schemas ──────────────────────────────────────────────────────────────────

# =============================================================================
# 2. FAULTY ENTITY
# =============================================================================
# Polymorphic record pointing to any level of the hierarchy
# (project / system / subsystem / module / unit / component).
# parent_faulty_entity_id enables the fault cascade chain to be explicit:
#   component FE → parent unit FE → parent module FE → ...
# =============================================================================

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
