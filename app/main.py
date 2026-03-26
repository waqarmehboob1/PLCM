from fastapi import FastAPI
from app.database import init_db, close_db, engine
from sqlmodel import Session
from contextlib import asynccontextmanager
from app.routers import router
from app.auth import initialize_roles_and_permissions

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # Initialize default roles and permissions
    with Session(engine) as session:
        initialize_roles_and_permissions(session)
    try:
        yield
    finally:
        # shutdown
        close_db()
    yield

app: FastAPI = FastAPI(title="PLCM System", lifespan=lifespan)
app.include_router(router, prefix="/api")

@app.get("/")
def root():
    return {"message": "PLM FastAPI running"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", reload=True)
    # uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)