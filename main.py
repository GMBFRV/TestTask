from contextlib import asynccontextmanager
import uvicorn
from fastapi import FastAPI
from app.db import Base, engine
from app.routes.places import router as places_router
from app.routes.projects import router as projects_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="Travel Projects API", lifespan=lifespan)

app.include_router(projects_router)
app.include_router(places_router)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)