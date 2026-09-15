from dataclasses import dataclass

@dataclass
class User:
    id: str
    username: str
    password_hash: str
    role: str = "user"