#!/usr/bin/env python
"""Launch the two local workers, then remove PID 1's Linux capabilities."""

from __future__ import annotations

import ctypes
import os
import signal
import subprocess
import sys


class _CapHeader(ctypes.Structure):
    _fields_ = [("version", ctypes.c_uint32), ("pid", ctypes.c_int)]


class _CapData(ctypes.Structure):
    _fields_ = [
        ("effective", ctypes.c_uint32),
        ("permitted", ctypes.c_uint32),
        ("inheritable", ctypes.c_uint32),
    ]


def _drop_pid_one_capabilities() -> None:
    header = _CapHeader(version=0x20080522, pid=0)
    data = (_CapData * 2)()
    if ctypes.CDLL(None, use_errno=True).capset(ctypes.byref(header), data) != 0:
        raise OSError(ctypes.get_errno(), "capset failed")
    status = open("/proc/self/status", encoding="utf-8").read()
    if "CapEff:\t0000000000000000" not in status or "CapPrm:\t0000000000000000" not in status:
        raise RuntimeError("PID 1 capabilities remained after capset")


def _wait_for_first_worker() -> int:
    while True:
        try:
            _pid, status = os.wait()
            return os.waitstatus_to_exitcode(status)
        except InterruptedError:
            continue


def main() -> int:
    api = subprocess.Popen(
        [
            "setpriv", "--reuid=10001", "--regid=10001", "--init-groups", "--",
            "python", "-m", "uvicorn", "videobox_api.main:create_app", "--factory",
            "--host", "127.0.0.1", "--port", "8000",
        ]
    )
    web_env = os.environ.copy()
    web_env.pop("VIDEOBOX_DATABASE_URL", None)
    web_env.pop("POSTGRES_PASSWORD", None)
    web = subprocess.Popen(
        [
            "setpriv", "--reuid=10002", "--regid=10002", "--init-groups", "--",
            "nginx", "-c", "/etc/nginx/workspace-nginx.conf", "-g", "daemon off;",
        ],
        env=web_env,
    )
    del api, web
    _drop_pid_one_capabilities()
    signal.signal(signal.SIGTERM, lambda _signum, _frame: sys.exit(143))
    signal.signal(signal.SIGINT, lambda _signum, _frame: sys.exit(130))
    return _wait_for_first_worker()


if __name__ == "__main__":
    raise SystemExit(main())
