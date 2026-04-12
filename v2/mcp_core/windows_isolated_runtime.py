from __future__ import annotations

import ctypes
import os
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any


CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0
DESKTOP_CREATE_FLAGS = 0
DESKTOP_ACCESS = 0x0002 | 0x0040 | 0x0080 | 0x0100


@dataclass(slots=True)
class IsolatedRuntimeSession:
    desktop_name: str
    desktop_handle: int | None
    process: subprocess.Popen[str]
    project_root: Path
    host_desktop_name: str = ""
    execution_mode: str = "isolated_runtime"

    @property
    def pid(self) -> int:
        return int(self.process.pid)


def runtime_session_path(project_root: Path) -> Path:
    return (project_root / "pointer_gpf" / "tmp" / "runtime_session.json").resolve()


def launch_isolated_runtime(project_root: Path, godot_executable: str, *, timeout_ms: int = 15000) -> IsolatedRuntimeSession:
    if os.name != "nt":
        raise OSError("isolated_runtime is currently supported only on Windows")
    host_desktop_name = _current_desktop_name()
    desktop_name = f"pointer_gpf_v2_{uuid.uuid4().hex[:12]}"
    if host_desktop_name and host_desktop_name.lower() == desktop_name.lower():
        raise RuntimeError("isolated runtime desktop unexpectedly matched the host desktop name")
    desktop_handle = _create_desktop(desktop_name)
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.lpDesktop = f"winsta0\\{desktop_name}"
    env = os.environ.copy()
    env["POINTER_GPF_EXECUTION_MODE"] = "isolated_runtime"
    env["POINTER_GPF_RUNTIME_DESKTOP"] = desktop_name
    session_file = runtime_session_path(project_root)
    session_file.unlink(missing_ok=True)
    kwargs: dict[str, Any] = {
        "cwd": str(project_root),
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "startupinfo": startupinfo,
        "env": env,
        "text": True,
    }
    if os.name == "nt":
        kwargs["creationflags"] = CREATE_NO_WINDOW
    process = subprocess.Popen([godot_executable, "--path", str(project_root)], **kwargs)
    session = IsolatedRuntimeSession(
        desktop_name=desktop_name,
        desktop_handle=desktop_handle,
        process=process,
        project_root=project_root.resolve(),
        host_desktop_name=host_desktop_name,
    )
    _wait_for_runtime_session(session, timeout_ms=timeout_ms)
    return session


def _wait_for_runtime_session(session: IsolatedRuntimeSession, *, timeout_ms: int) -> dict[str, Any]:
    deadline = time.monotonic() + max(1, timeout_ms) / 1000.0
    path = runtime_session_path(session.project_root)
    while time.monotonic() < deadline:
        if session.process.poll() is not None:
            raise RuntimeError(f"isolated runtime exited before bridge session was ready (pid={session.pid})")
        if path.is_file():
            try:
                import json

                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                time.sleep(0.05)
                continue
            if (
                isinstance(payload, dict)
                and int(payload.get("process_id", -1)) == session.pid
                and str(payload.get("execution_mode", "")).strip() == session.execution_mode
            ):
                return payload
        time.sleep(0.05)
    raise TimeoutError(f"isolated runtime bridge was not ready within {timeout_ms} ms")


def verify_isolated_runtime_stopped(session: IsolatedRuntimeSession, *, timeout_ms: int = 10000, stable_ms: int = 500) -> dict[str, Any]:
    deadline = time.monotonic() + max(1, timeout_ms) / 1000.0
    stable_since: float | None = None
    stable_seconds = max(0, stable_ms) / 1000.0
    while time.monotonic() < deadline:
        now = time.monotonic()
        running = session.process.poll() is None
        if not running:
            if stable_since is None:
                stable_since = now
            stable_stop_ms = int(max(0.0, now - stable_since) * 1000)
        else:
            stable_since = None
            stable_stop_ms = 0
        if not running and stable_stop_ms >= stable_ms:
            return {
                "status": "verified",
                "runtime_pid": session.pid,
                "execution_mode": session.execution_mode,
                "desktop_name": session.desktop_name,
                "host_desktop_name": session.host_desktop_name,
                "separate_desktop": bool(session.desktop_name and session.host_desktop_name and session.desktop_name != session.host_desktop_name),
                "stable_stop_ms": stable_stop_ms,
                "required_stable_stop_ms": stable_ms,
            }
        time.sleep(0.1)
    return {
        "status": "failed",
        "runtime_pid": session.pid,
        "execution_mode": session.execution_mode,
        "desktop_name": session.desktop_name,
        "host_desktop_name": session.host_desktop_name,
        "separate_desktop": bool(session.desktop_name and session.host_desktop_name and session.desktop_name != session.host_desktop_name),
        "stable_stop_ms": int(max(0.0, (time.monotonic() - stable_since) * 1000)) if stable_since is not None else 0,
        "required_stable_stop_ms": stable_ms,
    }


def close_isolated_runtime_session(session: IsolatedRuntimeSession) -> None:
    if session.process.poll() is None:
        session.process.kill()
        try:
            session.process.wait(timeout=5)
        except Exception:
            pass
    _close_desktop(session.desktop_handle)


def _create_desktop(name: str) -> int:
    user32 = ctypes.windll.user32
    user32.CreateDesktopW.restype = ctypes.c_void_p
    handle = user32.CreateDesktopW(name, None, None, DESKTOP_CREATE_FLAGS, DESKTOP_ACCESS, None)
    if not handle:
        raise OSError(f"CreateDesktopW failed for desktop {name!r}")
    return int(handle)


def _current_desktop_name() -> str:
    if os.name != "nt":
        return ""
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    user32.GetThreadDesktop.restype = ctypes.c_void_p
    thread_id = kernel32.GetCurrentThreadId()
    desktop_handle = user32.GetThreadDesktop(thread_id)
    if not desktop_handle:
        return ""
    needed = ctypes.c_uint(0)
    UOI_NAME = 2
    user32.GetUserObjectInformationW(ctypes.c_void_p(desktop_handle), UOI_NAME, None, 0, ctypes.byref(needed))
    if needed.value <= 2:
        return ""
    buffer = ctypes.create_unicode_buffer(max(1, needed.value // ctypes.sizeof(ctypes.c_wchar)))
    ok = user32.GetUserObjectInformationW(
        ctypes.c_void_p(desktop_handle),
        UOI_NAME,
        buffer,
        needed.value,
        ctypes.byref(needed),
    )
    if not ok:
        return ""
    return buffer.value.strip()


def _close_desktop(handle: int | None) -> None:
    if not handle:
        return
    try:
        ctypes.windll.user32.CloseDesktop(ctypes.c_void_p(handle))
    except Exception:
        pass
