import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

@dataclass
class Session:
    token: str
    user_id: str
    expires_at: datetime

class SessionStore:
    def __init__(self, ttl_minutes: int = 120) -> None:
        if ttl_minutes <= 0:
            raise ValueError("TTL must be a positive integer")

        self.ttl = timedelta(minutes=ttl_minutes)
        self.sessions: dict[str, Session] = {}

    def create(self, user_id: str) -> Session:
        session = Session(
            token = secrets.token_urlsafe(32),
            user_id = user_id,
            expires_at = datetime.now(timezone.utc) + self.ttl,
        )
        self.sessions[session.token] = session
        return session

    def get(self, token: str) -> Session | None:
        session = self.sessions.get(token)

        if session is None:
            return None

        if datetime.now(timezone.utc) >= session.expires_at:
            self.sessions.pop(token, None)
            return None

        return session

    def delete(self, token: str) -> None:
        self.sessions.pop(token, None)