from investment_agent.auth.models import User
from investment_agent.auth.passwords import verify_password

class AuthStore:
    def __init__(self, users: list[User]) -> None:
        self.users: dict[str, User] = {}

        for user in users:
            if user.username in self.users:
                raise ValueError(f"Duplicate username: {user.username}")
            self.users[user.username] = user

    def authenticate(self, username: str, password: str) -> User | None:
        if username not in self.users:
            return None
        user = self.users[username]
        if not verify_password(password, user.password_hash):
            return None
        return user

