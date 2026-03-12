from typing import List
from fastapi import APIRouter, HTTPException, Depends
from sqlmodel import Session, select
from app.database import get_session
from app.models.tables import (Project)
from app.schemas import schemas

router = APIRouter()

# ===================== PROJECT ENDPOINTS =====================
@router.post("/projects/", response_model=schemas.ProjectRead, tags=["projects"])
def create_project(project: schemas.ProjectCreate, session: Session = Depends(get_session)):
    db_project = Project(**project.dict())
    session.add(db_project)
    session.commit()
    session.refresh(db_project)
    status_name = db_project.status.name if db_project.status else None
    return schemas.ProjectRead(
        **db_project.model_dump(),
        status_name=status_name,
        systems=db_project.systems
    )

@router.get("/projects/", response_model=List[schemas.ProjectRead], tags=["projects"])
def list_projects(skip: int = 0, limit: int = 100, session: Session = Depends(get_session)):
    projects = session.exec(select(Project).offset(skip).limit(limit)).all()
    result = []
    for project in projects:
        status_name = project.status.name if project.status else None
        result.append(schemas.ProjectRead(
            **project.model_dump(),
            status_name=status_name,
            systems=project.systems
        ))
    return result

@router.get("/projects/{project_id}/", response_model=schemas.ProjectRead, tags=["projects"])
def get_project(project_id: int, session: Session = Depends(get_session)):
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    status_name = project.status.name if project.status else None
    return schemas.ProjectRead(
        **project.model_dump(),
        status_name=status_name,
        systems=project.systems
    )

@router.put("/projects/{project_id}/", response_model=schemas.ProjectRead, tags=["projects"])
def update_project(project_id: int, project: schemas.ProjectUpdate, session: Session = Depends(get_session)):
    db_project = session.get(Project, project_id)
    if not db_project:
        raise HTTPException(status_code=404, detail="Project not found")
    for k, v in project.model_dump(exclude_unset=True).items():
        setattr(db_project, k, v)
    session.add(db_project)
    session.commit()
    session.refresh(db_project)
    status_name = db_project.status.name if db_project.status else None
    return schemas.ProjectRead(
        **db_project.model_dump(),
        status_name=status_name,
        systems=db_project.systems
    )

@router.delete("/projects/{project_id}/", tags=["projects"])
def delete_project(project_id: int, session: Session = Depends(get_session)):
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    session.delete(project)
    session.commit()
    return {"ok": True}

@router.get("/projects/{project_id}/systems/", response_model=List[schemas.SystemRead], tags=["projects"])
def list_project_systems(project_id: int, session: Session = Depends(get_session)):
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project.systems
