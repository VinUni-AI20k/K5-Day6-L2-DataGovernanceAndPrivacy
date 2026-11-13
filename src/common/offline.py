"""Offline guard: make accidental network calls fail loudly during demo/eval.

The lab contract says `python -m src.main --offline` must not touch the network
and must NOT silently download models. Call `enable_offline_guard()` early.
"""
from __future__ import annotations

import os
import socket

_ALLOWED_HOSTS = {"127.0.0.1", "localhost", "::1"}
_original_connect = socket.socket.connect
_original_create_connection = socket.create_connection


class NetworkBlockedError(RuntimeError):
    pass


def _host_of(address) -> str:
    if isinstance(address, tuple) and address:
        return str(address[0])
    return str(address)


def _guarded_connect(self, address):  # type: ignore[no-untyped-def]
    if self.family == getattr(socket, "AF_UNIX", None) or _host_of(address) in _ALLOWED_HOSTS:
        return _original_connect(self, address)
    raise NetworkBlockedError(
        f"Network access blocked by --offline (tried to connect to {address!r}). "
        "Pre-download models/data before the lab and load them from disk."
    )


def _guarded_create_connection(address, *args, **kwargs):  # type: ignore[no-untyped-def]
    if _host_of(address) in _ALLOWED_HOSTS:
        return _original_create_connection(address, *args, **kwargs)
    raise NetworkBlockedError(f"Network access blocked by --offline (create_connection to {address!r}).")


def enable_offline_guard() -> None:
    """Block outbound sockets and tell common ML libs to stay offline."""
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    os.environ.setdefault("HF_DATASETS_OFFLINE", "1")
    os.environ.setdefault("YOLO_OFFLINE", "1")
    socket.socket.connect = _guarded_connect  # type: ignore[method-assign]
    socket.create_connection = _guarded_create_connection  # type: ignore[assignment]


def disable_offline_guard() -> None:
    socket.socket.connect = _original_connect  # type: ignore[method-assign]
    socket.create_connection = _original_create_connection  # type: ignore[assignment]


def require_local_file(path: str, what: str = "model weights") -> str:
    """Fail clearly (never download) if a required local artefact is missing."""
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Missing {what}: {path}. This lab runs offline — copy the pre-downloaded file "
            "from the instructor pack (models_optional/) or switch to a fixture."
        )
    return path
