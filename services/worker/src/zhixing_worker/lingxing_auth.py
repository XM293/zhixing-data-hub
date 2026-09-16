from time import time

from zhixing_connectors.auth import AccessToken
from zhixing_connectors.signing import build_signature


class LingxingAuth:
    """Compatibility adapter; protocol implementation lives in shared connectors."""

    def __init__(self, app_id: str, app_secret: str, base_url: str) -> None:
        self._app_id, self._app_secret, self.base_url = app_id, app_secret, base_url

    def signed_params(self, params: dict[str, object], token: str) -> dict[str, str]:
        values = {
            **params, "access_token": token, "app_key": self._app_id,
            "timestamp": str(int(time())),
        }
        return {
            **{k: str(v) for k, v in values.items() if v != ""},
            "sign": build_signature(values, self._app_id),
        }


__all__ = ["AccessToken", "LingxingAuth"]
