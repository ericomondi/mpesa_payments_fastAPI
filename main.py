
from fastapi import FastAPI
from contextlib import asynccontextmanager
from database import database, engine, Base
from routers.lnmo_router import router as lnmo_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await database.connect()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    # Shutdown
    await database.disconnect()

app = FastAPI(
    title="MPESA Payments API",
    description="FastAPI implementation of MPESA LNMO payments",
    version="1.0.0",
    lifespan=lifespan
)

# Include routers
app.include_router(lnmo_router)

@app.get("/")
async def root():
    return {"message": "Welcome to the MPESA Payments API!"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
