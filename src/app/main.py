"""FastAPI application entrypoint."""
from __future__ import annotations

import os

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.deps import LoginRedirect
from app.routers import auth, categories, competitions, exports, participants, rounds

app = FastAPI(title="System SUMO — protokoły zawodów")

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.exception_handler(LoginRedirect)
async def _login_redirect(request: Request, exc: LoginRedirect):
    return RedirectResponse(url="/login", status_code=303)


app.include_router(auth.router)
app.include_router(competitions.router)
app.include_router(categories.router)
app.include_router(participants.router)
app.include_router(rounds.router)
app.include_router(exports.router)


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}
