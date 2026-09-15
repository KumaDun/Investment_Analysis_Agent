import hashlib
import hmac
import secrets

def hash_password(password: str, *, salt: str | None = None, iterations: int = 600_000) -> str:
    if iterations <= 0:
        raise ValueError("iteration must be greater than 0")
    salt = salt if salt is not None else secrets.token_hex(16)

    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), iterations)
    return f"pbkdf2_sha256${iterations}${salt}${digest.hex()}"

def verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, iterations_text, salt, expected_digest = (
            password_hash.split("$", 3)
        )
        iterations = int(iterations_text)
    except ValueError:
        return False

    if algorithm != "pbkdf2_sha256" or iterations <= 0:
        return False

    actual_hash = hash_password(password, salt=salt, iterations=iterations)
    actual_digest = actual_hash.split("$", 3)[-1]
    return hmac.compare_digest(actual_digest, expected_digest)