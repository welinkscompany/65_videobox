"""owner가 밟는 경로를 그대로 밟는다. 실패해도 멈추지 않고 그 자리를 적는다."""
from __future__ import annotations
import json, sys, urllib.request, urllib.error

BASE = "http://127.0.0.1:5173"

def call(method: str, path: str, body: dict | None = None, *, timeout: float = 300.0):
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    request = urllib.request.Request(BASE + path, data=data, method=method)
    if data is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            return response.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as error:
        raw = error.read().decode("utf-8", "replace")
        try:
            return error.code, json.loads(raw)
        except Exception:
            return error.code, {"raw": raw[:500]}

def show(label: str, status: int, payload) -> None:
    mark = "  " if 200 <= status < 300 else "!!"
    print(f"{mark} {label}: {status} {json.dumps(payload, ensure_ascii=False)[:260]}")
    sys.stdout.flush()
