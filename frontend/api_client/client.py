import os
from typing import Any

import requests

DEFAULT_API_BASE_URL = "http://localhost:8000/api/v1"


class AdPilotApiClient:
    def __init__(self, base_url: str | None = None, timeout_seconds: float = 5.0) -> None:
        self.base_url = (base_url or os.getenv("API_BASE_URL", DEFAULT_API_BASE_URL)).rstrip("/")
        self.timeout_seconds = timeout_seconds

    def health(self) -> dict[str, Any]:
        response = requests.get(f"{self.base_url}/health", timeout=self.timeout_seconds)
        response.raise_for_status()
        return response.json()
