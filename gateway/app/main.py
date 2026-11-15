from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import config, observability
from .routers import patterns, services, shop

app = FastAPI(
    title="Microservices 12 Patterns — API Gateway",
    description="Single entry point for the frontend (pattern 5). Routes /api/shop/* to the "
                "service that owns each path, aggregates /api/order-summary, and serves the "
                "live demo endpoints for the pattern pages.",
    version="0.3.0",
)

observability.install(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.FRONTEND_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # Lets the frontend read these on cross-origin responses, to link a click to its trace.
    expose_headers=["X-Request-Id", "X-Trace-Id"],
)

app.include_router(shop.router)
app.include_router(patterns.router)
app.include_router(services.router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "gateway"}
