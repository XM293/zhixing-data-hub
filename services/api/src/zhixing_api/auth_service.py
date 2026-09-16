from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

PASSWORD_ALGORITHM = "pbkdf2_sha256"
PASSWORD_ITERATIONS = 310_000


def hash_password(password: str) -> str:
    if len(password) < 12:
        raise ValueError("密码至少需要 12 个字符")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PASSWORD_ITERATIONS,
    )
    return "$".join(
        (
            PASSWORD_ALGORITHM,
            str(PASSWORD_ITERATIONS),
            base64.urlsafe_b64encode(salt).decode("ascii").rstrip("="),
            base64.urlsafe_b64encode(digest).decode("ascii").rstrip("="),
        )
    )


def verify_password(password: str, encoded: str | None) -> bool:
    if not encoded:
        return False
    try:
        algorithm, iterations_text, salt_text, digest_text = encoded.split("$", 3)
        if algorithm != PASSWORD_ALGORITHM:
            return False
        iterations = int(iterations_text)
        salt = base64.urlsafe_b64decode(f"{salt_text}===")
        expected = base64.urlsafe_b64decode(f"{digest_text}===")
    except (TypeError, ValueError):
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual, expected)
