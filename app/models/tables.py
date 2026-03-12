from .base import *
from typing import List, Optional
from sqlmodel import Field, Relationship

class UserRole(SQLModel, table=True):
    user_id: Optional[int] = Field(default=None, foreign_key="user.id", primary_key=True)
    role_id: Optional[int] = Field(default=None, foreign_key="role.id", primary_key=True)

class User(UserBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    roles: List["Role"] = Relationship(back_populates="users", link_model=UserRole)
    projects: List["Project"] = Relationship(back_populates="owner")
    status_changes: List["EntityStatusHistory"] = Relationship(back_populates="changed_by_user")
    maintenances: List["MaintenanceLog"] = Relationship(back_populates="performed_by_user")

class RolePermission(SQLModel, table=True):
    role_id: Optional[int] = Field(default=None, foreign_key="role.id", primary_key=True)
    permission_id: Optional[int] = Field(default=None, foreign_key="permission.id", primary_key=True)

class Role(RoleBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    permissions: List["Permission"] = Relationship(back_populates="roles", link_model=RolePermission)
    users: List["User"] = Relationship(back_populates="roles", link_model=UserRole)

class Permission(PermissionBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    roles: List["Role"] = Relationship(back_populates="permissions", link_model=RolePermission)

class Customer(CustomerBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    orders: List["Order"] = Relationship(back_populates="customer")

class Status(StatusBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    # reverse relationships
    orders: List["Order"] = Relationship(back_populates="status")
    projects: List["Project"] = Relationship(back_populates="status")
    systems: List["System"] = Relationship(back_populates="status")
    subsystems: List["Subsystem"] = Relationship(back_populates="status")
    modules: List["Module"] = Relationship(back_populates="status")
    units: List["Unit"] = Relationship(back_populates="status")
    components: List["Component"] = Relationship(back_populates="status")
    entities: List["Entity"] = Relationship(back_populates="status")
    history_records: List["EntityStatusHistory"] = Relationship(back_populates="status")

class Order(OrderBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    customer_id: int = Field(foreign_key="customer.id")
    status_id: Optional[int] = Field(default=None, foreign_key="status.id")
    customer: Optional[Customer] = Relationship(back_populates="orders")
    status: Optional[Status] = Relationship(back_populates="orders")
    projects: List["Project"] = Relationship(back_populates="order")

class Project(ProjectBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    order_id: Optional[int] = Field(default=None, foreign_key="order.id")
    status_id: Optional[int] = Field(default=None, foreign_key="status.id")
    owner_id: Optional[int] = Field(default=None, foreign_key="user.id")
    owner: Optional["User"] = Relationship(back_populates="projects")
    order: Optional["Order"] = Relationship(back_populates="projects")
    status: Optional[Status] = Relationship(back_populates="projects")
    systems: List["System"] = Relationship(back_populates="project")

class System(SystemBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id")
    status_id: Optional[int] = Field(default=None, foreign_key="status.id")
    project: Optional[Project] = Relationship(back_populates="systems")
    status: Optional[Status] = Relationship(back_populates="systems")
    subsystems: List["Subsystem"] = Relationship(back_populates="system")

class Subsystem(SubsystemBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    system_id: int = Field(foreign_key="system.id")
    status_id: Optional[int] = Field(default=None, foreign_key="status.id")
    system: Optional[System] = Relationship(back_populates="subsystems")
    status: Optional[Status] = Relationship(back_populates="subsystems")
    modules: List["Module"] = Relationship(back_populates="subsystem")

class Module(ModuleBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    subsystem_id: int = Field(foreign_key="subsystem.id")
    status_id: Optional[int] = Field(default=None, foreign_key="status.id")
    subsystem: Optional[Subsystem] = Relationship(back_populates="modules")
    status: Optional[Status] = Relationship(back_populates="modules")
    units: List["Unit"] = Relationship(back_populates="module")

class Unit(UnitBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    module_id: int = Field(foreign_key="module.id")
    status_id: Optional[int] = Field(default=None, foreign_key="status.id")
    module: Optional[Module] = Relationship(back_populates="units")
    status: Optional[Status] = Relationship(back_populates="units")
    components: List["Component"] = Relationship(back_populates="unit")

class Component(ComponentBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    unit_id: int = Field(foreign_key="unit.id")
    status_id: Optional[int] = Field(default=None, foreign_key="status.id")
    unit: Optional[Unit] = Relationship(back_populates="components")
    status: Optional[Status] = Relationship(back_populates="components")
    inventory_items: List["Inventory"] = Relationship(back_populates="component")

class Entity(EntityBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    status_id: Optional[int] = Field(default=None, foreign_key="status.id")
    status: Optional["Status"] = Relationship(back_populates="entities")
    status_history: List["EntityStatusHistory"] = Relationship(back_populates="entity")
    maintenance_logs: List["MaintenanceLog"] = Relationship(back_populates="entity")

class MaintenanceLog(MaintenanceLogBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    entity_id: int = Field(foreign_key="entity.id")
    performed_by: Optional[int] = Field(default=None, foreign_key="user.id")
    entity: Optional[Entity] = Relationship(back_populates="maintenance_logs")
    performed_by_user: Optional[User] = Relationship(back_populates="maintenances")

class EntityStatusHistory(EntityStatusHistoryBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    entity_id: int = Field(foreign_key="entity.id")
    status_id: int = Field(foreign_key="status.id")
    status: Optional["Status"] = Relationship(back_populates="history_records")
    changed_by: Optional[int] = Field(default=None, foreign_key="user.id")
    entity: Optional[Entity] = Relationship(back_populates="status_history")
    changed_by_user: Optional[User] = Relationship(back_populates="status_changes")

class Inventory(InventoryBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    component_id: int = Field(foreign_key="component.id")
    component: Optional[Component] = Relationship(back_populates="inventory_items")



# ===== AUTHENTICATION & AUTHORIZATION TABLES =====







