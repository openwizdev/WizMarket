"""HTTP client for TypeSafe System One.

The only call is POST https://api.typesafe.ai/v1/systemone, as documented at
https://docs.typesafe.ai/api/system-one. The key is read from TYPESAFE_API_KEY
and is never logged. Callers treat None as "use the existing decision".
"""

import http.client
import json
import os
import time
import urllib.error
import urllib.request

ENDPOINT = "https://api.typesafe.ai/v1/systemone"
MODEL = "jev-1.14.0"
_RETRY_STATUSES = frozenset((408, 429, *range(500, 600)))
_SERVICE_ERROR_STATUSES = frozenset((401, 403, 404))
_MAX_RETRIES = 2
_BODY_LIMIT = 1024 * 1024
_DEFAULT_TIMEOUT = 20


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _default_opener():
    return urllib.request.build_opener(_NoRedirect).open


def key_from_env():
    """The API key, or None when it is missing or rejected by the documented rules."""
    raw = os.environ.get("TYPESAFE_API_KEY")
    if raw is None:
        return None
    key = raw.strip()
    if not key or any(ord(c) < 33 or ord(c) > 126 for c in key):
        return None
    return key


class HttpSystemOneClient:
    """Asks one System One request. Returns the answers object, or None on any failure."""

    def __init__(self, api_key, opener=None, sleep=time.sleep, model=MODEL, url=ENDPOINT,
                 timeout=_DEFAULT_TIMEOUT, clock=time.monotonic, deadline=None):
        if not isinstance(api_key, str) or not api_key or any(ord(c) < 33 or ord(c) > 126 for c in api_key):
            raise ValueError("TYPESAFE_API_KEY is empty or not printable ASCII")
        self._api_key = api_key
        self._open = opener or _default_opener()
        self._sleep = sleep
        self._model = model
        self._url = url
        self._timeout = timeout
        self._clock = clock
        self._deadline = deadline
        self._unavailable = False
        self._stop_reason = None

    @property
    def unavailable(self):
        return self._unavailable

    @property
    def stop_reason(self):
        return self._stop_reason

    def _trip(self, reason="service failure"):
        self._unavailable = True
        self._stop_reason = reason
        return None

    def __repr__(self):
        return f"HttpSystemOneClient(model={self._model!r})"

    def ask(self, state, questions, timeout=None):
        if self._unavailable:
            return None
        deadlines = []
        if self._deadline is not None:
            deadlines.append(self._deadline)
        if timeout is not None:
            deadlines.append(self._clock() + timeout)
        call_deadline = min(deadlines) if deadlines else None
        payload = json.dumps({"model": self._model, "state": state, "questions": questions},
                             ensure_ascii=False).encode("utf-8")
        for attempt in range(_MAX_RETRIES + 1):
            if call_deadline is not None:
                remaining = call_deadline - self._clock()
                if remaining <= 0:
                    if self._deadline is not None and self._clock() >= self._deadline:
                        return self._trip("deadline")
                    return None
                req_timeout = min(self._timeout, remaining)
            else:
                req_timeout = self._timeout
            request = urllib.request.Request(
                self._url, data=payload, method="POST",
                headers={"Authorization": "Bearer " + self._api_key, "Content-Type": "application/json",
                         "Accept": "application/json"})
            try:
                with self._open(request, timeout=req_timeout) as response:
                    status = getattr(response, "status", 200)
                    if status in _RETRY_STATUSES:
                        if attempt < _MAX_RETRIES:
                            delay = _retry_delay(response, attempt)
                            if delay is None:
                                return self._trip("service failure")
                            if call_deadline is not None and self._clock() + delay >= call_deadline:
                                return self._trip("deadline")
                            self._sleep(delay)
                            continue
                        return self._trip("service failure")
                    if status in _SERVICE_ERROR_STATUSES or 300 <= status < 400:
                        return self._trip("service failure")
                    if status >= 400:
                        return None
                    return _answers(response.read(_BODY_LIMIT + 1))
            except urllib.error.HTTPError as error:
                if error.code in _RETRY_STATUSES:
                    if attempt < _MAX_RETRIES:
                        delay = _retry_delay(error, attempt)
                        if delay is None:
                            return self._trip("service failure")
                        if call_deadline is not None and self._clock() + delay >= call_deadline:
                            return self._trip("deadline")
                        self._sleep(delay)
                        continue
                    return self._trip("service failure")
                if error.code in _SERVICE_ERROR_STATUSES or 300 <= error.code < 400:
                    return self._trip("service failure")
                return None
            except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException):
                return self._trip("service failure")
            except ValueError:
                return None
        return None


def client_from_env(opener=None, sleep=time.sleep, clock=time.monotonic, deadline=None):
    key = key_from_env()
    if key is None:
        return None
    return HttpSystemOneClient(key, opener=opener, sleep=sleep, clock=clock, deadline=deadline)


def _retry_delay(error, attempt):
    headers = getattr(error, "headers", None)
    header = None
    if headers is not None:
        header = headers.get("Retry-After")
        if header is None and hasattr(headers, "get"):
            header = headers.get("retry-after")
        millis = headers.get("retry-after-ms") if hasattr(headers, "get") else None
        if millis is not None and header is None:
            try:
                header = float(millis) / 1000
            except (TypeError, ValueError):
                header = None
    if header is not None and header != "":
        try:
            delay = float(header)
        except (TypeError, ValueError):
            return None
        if not (0 <= delay <= 2):
            return None
        return delay
    return min(5.0, 0.5 * (2 ** attempt))


def _answers(raw):
    if not isinstance(raw, (bytes, bytearray)) or len(raw) > _BODY_LIMIT:
        return None
    try:
        body = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    answers = body.get("answers") if isinstance(body, dict) else None
    if not isinstance(answers, dict) or not answers:
        return None
    return answers
