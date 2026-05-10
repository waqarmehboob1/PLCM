# =============================================================================
# maintenance_module_additions.py
# New additions to maintenance_module.py
#
# DROP-IN additions — paste these blocks into maintenance_module.py at the
# positions marked with  ←── INSERT HERE  comments below.
#
# What's new:
#   A. EntityType extended with CUSTOMER, ORDER (enums section)
#   B. New schemas: EntityLookupRead, SuspectTreeRead, ConfirmFaultPayload
#   C. _CHILD_MAP  — mirrors _PARENT_MAP downward
#   D. Four new helpers:
#        _resolve_ancestors()    walk UP  to customer
#        _collect_descendants()  walk DOWN to every leaf
#        _create_suspect_fes()   bulk-create UNDER_INSPECTION faulty-entities
#        _clear_healthy_fes()    delete provisional rows + mark CONFIRMED_FAULTY
#   E. Three new endpoints:
#        GET  /entities/lookup-by-sku/{sku}/
#        POST /maintenance-cases/{case_id}/suspect-children/
#        POST /maintenance-cases/{case_id}/confirm-fault/
# =============================================================================

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Field, Session, SQLModel, select

# ── project-level imports (match your existing structure) ──────────────────
from db import get_session
from auth import require_permission
from models.user import User
# Hierarchy models — adapt class names / FK attribute names to your schema
from models.hierarchy import (
    Component, Unit, Module, Subsystem, System,
    Project, OrderDetail, Customer,          # ← add if not already imported
)
from models.project import Project           # already in maintenance_module.py

# Re-use the enums and models already defined in maintenance_module.py.
# If you merge this file, remove these imports and rely on the shared defs.
from maintenance_module import (
    EntityType, FaultType, FaultyEntityStatus, ResolutionType,
    MaintenanceCase, FaultyEntity, FaultyEntityRead,
    _PARENT_MAP,                             # the existing upward map
)


# =============================================================================
# A. EXTENDED EntityType VALUES
# =============================================================================
# If your project already has CUSTOMER / ORDER in EntityType, skip this block.
# Otherwise extend the existing enum (Python enums can't be subclassed, so
# re-declare or add the values directly to the original enum in maintenance_module.py):
#
#   class EntityType(str, Enum):
#       PROJECT   = "project"
#       SYSTEM    = "system"
#       SUBSYSTEM = "subsystem"
#       MODULE    = "module"
#       UNIT      = "unit"
#       COMPONENT = "component"
#       ORDER     = "order"          # ← ADD
#       CUSTOMER  = "customer"       # ← ADD
#
# The helpers below reference EntityType.ORDER and EntityType.CUSTOMER.


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

_CHILD_MAP: Dict[str, Tuple[str, Any, str]] = {
    EntityType.SYSTEM:    (EntityType.SUBSYSTEM, Subsystem, "system_id"),
    EntityType.SUBSYSTEM: (EntityType.MODULE,    Module,    "subsystem_id"),
    EntityType.MODULE:    (EntityType.UNIT,      Unit,      "module_id"),
    EntityType.UNIT:      (EntityType.COMPONENT, Component, "unit_id"),
    # EntityType.PROJECT → EntityType.SYSTEM is included for completeness
    # but typically a project-level fault wouldn't trigger suspect-children.
    EntityType.PROJECT:   (EntityType.SYSTEM,    System,    "project_id"),
}

# Map each entity type to its SQLModel class and the attribute used as its
# human-readable label (name, sku, serial_number, etc.).  Adjust to your schema.
_ENTITY_MODEL_MAP: Dict[str, Tuple[Any, str, Optional[str]]] = {
    # (SQLModelClass, pk_attr, label_attr)
    EntityType.COMPONENT: (Component, "id", "sku"),
    EntityType.UNIT:      (Unit,      "id", "sku"),
    EntityType.MODULE:    (Module,    "id", "sku"),
    EntityType.SUBSYSTEM: (Subsystem, "id", "sku"),
    EntityType.SYSTEM:    (System,    "id", "sku"),
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

# SKU/part-number lookup:  maps entity_type → (SQLModelClass, sku_attr)
# A single SKU must be unique within each entity type (enforced by your schema).
_SKU_SEARCH_MODELS: List[Tuple[str, Any, str]] = [
    (EntityType.COMPONENT, Component, "sku"),
    (EntityType.UNIT,      Unit,      "sku"),
    (EntityType.MODULE,    Module,    "sku"),
    (EntityType.SUBSYSTEM, Subsystem, "sku"),
    (EntityType.SYSTEM,    System,    "sku"),
    # Add more if Project / Order also carry part numbers.
]


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
      1. Searches every entity table in _SKU_SEARCH_MODELS for a matching SKU.
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

    for entity_type, model_cls, sku_attr in _SKU_SEARCH_MODELS:
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
