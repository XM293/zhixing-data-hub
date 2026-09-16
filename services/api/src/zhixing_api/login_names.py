"""One identifier contract for account creation, bootstrap and authentication."""
from typing import Annotated

from pydantic import BeforeValidator, Field


def normalize_login_name(value: object) -> object:
    return value.strip().casefold() if isinstance(value, str) else value


LoginName = Annotated[str, BeforeValidator(normalize_login_name),
                      Field(min_length=1, max_length=120, pattern=r"^\S+$")]
