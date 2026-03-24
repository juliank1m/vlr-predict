"""FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import matches, model, predictions, teams

app = FastAPI(
    title="VLR Predict",
    description="Pre-match win probability predictions for professional Valorant.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(predictions.router, prefix="/api/predictions", tags=["predictions"])
app.include_router(predictions.adhoc_router, prefix="/api", tags=["predictions"])
app.include_router(teams.router, prefix="/api/teams", tags=["teams"])
app.include_router(matches.router, prefix="/api/matches", tags=["matches"])
app.include_router(model.router, prefix="/api/model", tags=["model"])


@app.get("/api/health")
async def health():
    return {"status": "ok"}
