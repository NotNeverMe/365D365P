"""Tiny HTTP helper with retries.

Network access is only needed the first time a dataset is requested. After
that, every loader reads the committed copy under ``data/``.
"""

from __future__ import annotations

import time

import requests

USER_AGENT = "365-projects/0.1 (+https://github.com/; economics data dashboards)"
RETRY_STATUS = {429, 500, 502, 503, 504}


class DataUnavailable(RuntimeError):
    """Raised when a remote dataset cannot be downloaded."""


def get(url: str, *, params: dict | None = None, timeout: int = 60, retries: int = 3) -> requests.Response:
    """GET ``url`` with exponential backoff on transient errors."""
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            response = requests.get(
                url, params=params, timeout=timeout, headers={"User-Agent": USER_AGENT}
            )
            if response.status_code in RETRY_STATUS:
                last_error = DataUnavailable(f"{url} -> HTTP {response.status_code}")
            elif response.status_code >= 400:
                raise DataUnavailable(f"{url} -> HTTP {response.status_code}")
            else:
                return response
        except requests.RequestException as exc:  # network level failure
            last_error = exc
        time.sleep(2**attempt)
    raise DataUnavailable(f"Could not fetch {url}: {last_error}")
