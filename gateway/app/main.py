from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import config
from .routers import services, shop

app = FastAPI(
    title="Microservices 12 Patterns — API Gateway",
    description="Single entry point for the frontend (pattern 5). Routes /api/shop/* to the "
                "service that owns each path.",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.FRONTEND_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(shop.router)
app.include_router(services.router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "gateway"}
