from enum import StrEnum


class ErrorClass(StrEnum):
    RETRYABLE = "retryable"
    PERMANENT = "permanent"


def classify(status: int, code: str | None = None) -> ErrorClass:
    if status == 429 or status >= 500 or status == 408:
        return ErrorClass.RETRYABLE
    return ErrorClass.PERMANENT
