from typing import Optional, List
from datetime import datetime
from sqlmodel import SQLModel
from pydantic import ConfigDict
from app.models.base import (
    UserBase,
    CustomerBase,
    StatusBase,
    OrderBase,
    ProjectBase,
    SystemBase,
    SubsystemBase,
    ModuleBase,
    UnitBase,
    ComponentBase,
    InventoryBase,
    EntityBase,
    EntityStatusHistoryBase,
    MaintenanceLogBase,
    UserCommon,
    ProjectCommon,
    CustomerCommon,
    StatusCommon,
    OrderCommon,
    SystemCommon,
    SubsystemCommon,
    ModuleCommon,
    UnitCommon,
    ComponentCommon,
    InventoryCommon,
    EntityCommon,
    EntityStatusHistoryCommon,
    MaintenanceLogCommon,
    HierarchyBase,
)


# ---- User ----

class UserCreate(UserBase):
    pass

class UserRead(UserBase):
    id: int
    projects: Optional[List["ProjectRead"]] = None
    roles: Optional[List["RoleRead"]] = None
    permissions: List[str] = []

    class Config:
        orm_mode = True

class UserUpdate(SQLModel):
    username: Optional[str] = None
    email: Optional[str] = None
    full_name: Optional[str] = None
    is_active: Optional[bool] = None


class UserWithRoles(UserBase):
    id: int
    username: str
    full_name: str
    email: str | None = None
    roles: List[str]

# ---- Customer ----
class CustomerCreate(CustomerBase):
    pass

class CustomerRead(CustomerBase):
    id: int
    orders: Optional[List["OrderRead"]] = None
    class Config:
        orm_mode = True

class CustomerUpdate(SQLModel):
    name: Optional[str] = None
    contact_info: Optional[str] = None

# ---- Status ----
class StatusCreate(StatusBase):
    pass

class StatusRead(StatusBase):
    id: int
    class Config:
        orm_mode = True

class StatusUpdate(SQLModel):
    name: Optional[str] = None
    description: Optional[str] = None

class HierarchyCreate(HierarchyBase):
    pass

class HierarchyRead(HierarchyBase):
    id: int
    class Config:
        orm_mode = True

class HierarchyUpdate(SQLModel):
    name: Optional[str] = None
    description: Optional[str] = None
    hierarchy_type: Optional[str] = None
    parent_id: Optional[int] = None

# ---- Order ----
class OrderCreate(OrderBase):
    pass

class OrderRead(OrderBase):
    id: int
    status_id: Optional[int] = None
    customer_id: int
    status_name: Optional[str] = None
    projects: Optional[List["ProjectRead"]] = None

    class Config:
        orm_mode = True

class OrderUpdate(SQLModel):
    customer_id: Optional[int] = None
    order_number: Optional[str] = None
    status_id: Optional[int] = None

# ---- Project ----
class ProjectCreate(ProjectBase):
    pass

class ProjectRead(ProjectBase):
    id: int
    order_id: Optional[int] = None
    status_id: Optional[int] = None
    status_name: Optional[str] = None
    owner_id: Optional[int] = None
    systems: Optional[List["SystemRead"]] = None
    class Config:
        orm_mode = True

class ProjectUpdate(SQLModel):
    name: Optional[str] = None
    description: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    owner_id: Optional[int] = None
    order_id: Optional[int] = None
    status_id: Optional[int] = None

# ---- System / Subsystem / Module / Unit / Component ----
class SystemCreate(SystemBase):
    status_id: Optional[int] = None
    status_name: Optional[str] = None

class SystemRead(SystemBase):
    id: int
    project_id: int
    status_id: Optional[int] = None
    status_name: Optional[str] = None
    subsystems: Optional[List["SubsystemRead"]] = None

    class Config:
        orm_mode = True

class SystemUpdate(SQLModel):
    project_id: Optional[int] = None
    name: Optional[str] = None
    description: Optional[str] = None
    status_id: Optional[int] = None
    part_number: Optional[str] = None
    serial_number: Optional[str] = None
    configuration_item: Optional[str] = None

class SubsystemCreate(SubsystemBase):
    system_id: int
    status_id: Optional[int] = None


class SubsystemRead(SubsystemBase):
    id: int
    system_id: int
    status_id: Optional[int] = None
    status_name: Optional[str] = None
    modules: Optional[List["ModuleRead"]] = None

    class Config:
        orm_mode = True

class SubsystemUpdate(SQLModel):
    system_id: Optional[int] = None
    name: Optional[str] = None
    description: Optional[str] = None
    status_id: Optional[int] = None
    part_number: Optional[str] = None
    serial_number: Optional[str] = None
    configuration_item: Optional[str] = None

class ModuleCreate(ModuleBase):
    subsystem_id: int
    status_id: Optional[int] = None

class ModuleRead(ModuleBase):
    id: int
    subsystem_id: int
    status_id: Optional[int] = None
    status_name: Optional[str] = None
    units: Optional[List["UnitRead"]] = None

    class Config:
        orm_mode = True

class ModuleUpdate(SQLModel):
    subsystem_id: Optional[int] = None
    name: Optional[str] = None
    description: Optional[str] = None
    status_id: Optional[int] = None
    part_number: Optional[str] = None
    serial_number: Optional[str] = None
    configuration_item: Optional[str] = None

class UnitCreate(UnitBase):
    module_id: Optional[int] = None
    status_id: Optional[int] = None

class UnitRead(UnitBase):
    id: int
    module_id: Optional[int] = None
    status_id: Optional[int] = None
    status_name: Optional[str] = None
    components: Optional[List["ComponentRead"]] = None

    class Config:
        orm_mode = True

class UnitUpdate(SQLModel):
    module_id: Optional[int] = None
    name: Optional[str] = None
    description: Optional[str] = None
    status_id: Optional[int] = None
    part_number: Optional[str] = None
    serial_number: Optional[str] = None
    configuration_item: Optional[str] = None

class ComponentCreate(ComponentBase):
    unit_id: Optional[int] = None
    status_id: Optional[int] = None

class ComponentRead(ComponentBase):
    id: int
    unit_id: Optional[int] = None
    status_id: Optional[int] = None
    status_name: Optional[str] = None
    inventory_items: Optional[List["InventoryRead"]] = None

    class Config:
        orm_mode = True

class ComponentUpdate(SQLModel):
    unit_id: Optional[int] = None
    name: Optional[str] = None
    sku: Optional[str] = None
    description: Optional[str] = None
    status_id: Optional[int] = None
    part_number: Optional[str] = None
    serial_number: Optional[str] = None
    configuration_item: Optional[str] = None

# ---- Inventory ----
class InventoryCreate(InventoryBase):
    pass

class InventoryRead(InventoryBase):
    id: int

    class Config:
        orm_mode = True

class InventoryUpdate(SQLModel):
    component_id: Optional[int] = None
    quantity: Optional[int] = None
    location: Optional[str] = None

# ---- Entity / History / Maintenance ----
class EntityCreate(EntityBase):
    status_id: Optional[int] = None
    pass

class EntityRead(EntityBase):
    id: int
    status_id: Optional[int] = None
    status_history: Optional[List["EntityStatusHistoryRead"]] = None
    maintenance_logs: Optional[List["MaintenanceLogRead"]] = None
    class Config:
        orm_mode = True

class EntityUpdate(SQLModel):
    entity_type: Optional[str] = None
    entity_pk: Optional[int] = None
    display_name: Optional[str] = None
    status_id: Optional[int] = None

class EntityStatusHistoryCreate(EntityStatusHistoryBase):
    pass

class EntityStatusHistoryRead(EntityStatusHistoryBase):
    id: int
    class Config:
        orm_mode = True

class EntityStatusHistoryUpdate(SQLModel):
    entity_id: Optional[int] = None
    status_id: Optional[int] = None
    changed_by: Optional[int] = None
    notes: Optional[str] = None

class MaintenanceLogCreate(MaintenanceLogBase):
    pass

class MaintenanceLogRead(MaintenanceLogBase):
    id: int
    entity_id: Optional[int] = None
    performed_by: Optional[int] = None
    notes: Optional[str] = None
    performed_at: Optional[datetime] = None
    next_due: Optional[datetime] = None
    performed_by_user: Optional[UserRead] = None

    class Config:
        orm_mode = True

class MaintenanceLogUpdate(SQLModel):
    entity_id: Optional[int] = None
    performed_by: Optional[int] = None
    notes: Optional[str] = None
    next_due: Optional[datetime] = None






# ---- Authentication & Authorization ----

class PermissionRead(SQLModel):
    id: int
    name: str
    description: Optional[str] = None
    
    class Config:
        orm_mode = True


class RoleCreate(SQLModel):
    name: str
    description: Optional[str] = None


class RoleRead(SQLModel):
    id: int
    name: str
    description: Optional[str] = None
    permissions: Optional[List[PermissionRead]] = None
    
    class Config:
        orm_mode = True


class RoleUpdate(SQLModel):
    name: Optional[str] = None
    description: Optional[str] = None


class TokenResponse(SQLModel):
    access_token: str
    token_type: str
    user_id: int
    username: str
    email: Optional[str] = None
    roles: List[str] = []
    permissions: List[str] = []


class LoginRequest(SQLModel):
    username: str
    password: str


class ChangePasswordRequest(SQLModel):
    old_password: str
    new_password: str


class AssignRoleRequest(SQLModel):
    user_id: int
    role_id: int


class UserReadWithRoles(UserRead):
    roles: Optional[List[RoleRead]] = None
    
    class Config:
        orm_mode = True
