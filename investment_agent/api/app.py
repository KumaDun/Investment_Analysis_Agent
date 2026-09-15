import os

from fastapi import FastAPI

from investment_agent.api.routes import sessions
from investment_agent.auth.models import User
from investment_agent.auth.passwords import hash_password
from investment_agent.auth.service import AuthService
from investment_agent.auth.sessions import SessionStore
from investment_agent.auth.store import AuthStore


def create_app() -> FastAPI:
    username = os.environ.get("INVEST_DEMO_USERNAME")
    password = os.environ.get("INVEST_DEMO_PASSWORD")

    if not username or not password:
        raise RuntimeError("INVEST_DEMO_USERNAME and INVEST_DEMO_PASSWORD must be set")

    user = User(id="user_001", username=username, password_hash=hash_password(password))
    auth_service = AuthService(
        auth_store=AuthStore(users=[user]),
        session_store=SessionStore(),
    )

    app = FastAPI(
        title="Investment Agent API",
        version="0.1.0",
    )
    app.state.auth_service = auth_service

    @app.get("/api/v1/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}
    app.include_router(sessions.router, prefix="/api/v1")

    return app