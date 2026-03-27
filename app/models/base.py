from typing import Optional
from datetime import datetime, timezone
from sqlmodel import SQLModel, Field

# Base models for all entities, defining common fields and structure

# All Base models are immutable and include created_at timestamp. Updateable fields are defined in separate Common models.
# Common models are used for create/update operations and do not include created_at or primary key fields. They can be extended with additional fields as needed.
# Base models are used for database tables and include primary key fields. They can also include relationships if needed, but should not include updateable fields directly.

class UserCommon(SQLModel):    
    username: str
    email: Optional[str] = None
    full_name: Optional[str] = None
    is_active: bool = True
  # Password hash, required for auth

class UserBase(UserCommon):
    password:str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
class ProjectCommon(SQLModel):
    name: str
    description: Optional[str] = None
    start_date: datetime
    end_date: Optional[datetime] = None
    owner_id: int
    order_id: int = None
    status_id: Optional[int] = None

class ProjectBase(ProjectCommon):
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class CustomerCommon(SQLModel):
    name: str
    contact_info: Optional[str] = None

class CustomerBase(CustomerCommon):
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class StatusCommon(SQLModel):
    name: str
    description: Optional[str] = None
    status_type: Optional[str] = None
    
class StatusBase(StatusCommon):
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class OrderCommon(SQLModel):
    customer_id: int
    order_number: Optional[str] = None
    status_id: Optional[int] = None

class OrderBase(OrderCommon):
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class SystemCommon(SQLModel):
    name: str
    description: Optional[str] = None

class SystemBase(SystemCommon):
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class SubsystemCommon(SQLModel):
    name: str
    description: Optional[str] = None

class SubsystemBase(SubsystemCommon):
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class ModuleCommon(SQLModel):
    name: str
    description: Optional[str] = None

class ModuleBase(ModuleCommon):
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class UnitCommon(SQLModel):
    name: str
    description: Optional[str] = None

class UnitBase(UnitCommon):
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class ComponentCommon(SQLModel):
    name: str
    description: Optional[str] = None
    sku: Optional[str] = None


class ComponentBase(ComponentCommon):
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class EntityCommon(SQLModel):
    name: str
    display_name: Optional[str] = None
    entity_type: str
    entity_pk: int

class EntityBase(EntityCommon):
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class EntityStatusHistoryCommon(SQLModel):
    entity_id: Optional[int] = None
    status_id: Optional[int] = None
    changed_by: Optional[int] = None
    notes: Optional[str] = None

class EntityStatusHistoryBase(EntityStatusHistoryCommon):
    changed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class MaintenanceLogCommon(SQLModel):
    entity_id: int
    notes: Optional[str] = None
    next_due: Optional[datetime] = None
    
class MaintenanceLogBase(MaintenanceLogCommon):
    performed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class InventoryCommon(SQLModel):
    component_id: int
    quantity: int = 0
    location: Optional[str] = None

class InventoryBase(InventoryCommon):
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))   

# ===== AUTHENTICATION & AUTHORIZATION MODELS =====
class PermissionCommon(SQLModel):
    name: str  # e.g., "create_project", "delete_user", "view_inventory"
    description: Optional[str] = None

class PermissionBase(PermissionCommon):
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class RoleCommon(SQLModel):
    name: str  # e.g., "Admin", "ProjectManager", "Viewer"
    description: Optional[str] = None

class RoleBase(RoleCommon):
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class Token(SQLModel):
    access_token: str
    token_type: str

class TokenData(SQLModel):
    username: str | None = None