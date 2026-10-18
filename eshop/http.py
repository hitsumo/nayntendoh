"""Small requests wrapper with retries and a polite User-Agent."""

import time

import requests

USER_AGENT = "eshop-tracker/0.1 (+https://github.com/hitsumo/nayntendoh)"

_session = requests.Session()
_session.headers["User-Agent"] = USER_AGENT


def request(method: str, url: str, *, retries: int = 4, timeout: int = 30, **kwargs):
    """Perform an HTTP request, retrying on network errors / 5xx / 429."""
    delay = 1.0
    last_exc = None
    for attempt in range(retries + 1):
        try:
            resp = _session.request(method, url, timeout=timeout, **kwargs)
            if resp.status_code in (429, 500, 502, 503, 504) and attempt < retries:
                time.sleep(delay)
                delay *= 2
                continue
            resp.raise_for_status()
            return resp
        except (requests.ConnectionError, requests.Timeout) as exc:
            last_exc = exc
            if attempt >= retries:
                raise
            time.sleep(delay)
            delay *= 2
    raise last_exc  # pragma: no cover


def get_json(url: str, **kwargs):
    return request("GET", url, **kwargs).json()


def post_json(url: str, payload, **kwargs):
    return request("POST", url, json=payload, **kwargs).json()
