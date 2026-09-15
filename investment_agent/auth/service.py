from investment_agent.auth.sessions import Session, SessionStore
from investment_agent.auth.store import AuthStore

class AuthService:
    def __init__(self, session_store: SessionStore, auth_store: AuthStore) -> None:
        self.session_store = session_store
        self.auth_store = auth_store

    def login(self, username: str, password: str) -> Session | None:
        user = self.auth_store.authenticate(username, password)

        if user is None:
            return None

        return self.session_store.create(user_id=user.id)

    def get_session(self, token: str) -> Session | None:
        return self.session_store.get(token)

    def logout(self, token: str) -> None:
        self.session_store.delete(token)