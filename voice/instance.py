"""Stable per-installation identity and LiveKit room selection.

The state lives outside the plugin checkout so `hermes plugins update` can
replace plugin files without changing the instance room.
"""

from __future__ import annotations

import fcntl
import json
import os
import re
import secrets
import tempfile
from dataclasses import dataclass
from pathlib import Path


_AUTO_ROOM_VALUES = {"", "auto", "mate-hermes-test"}
_INSTANCE_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{5,63}$")


@dataclass(frozen=True)
class InstanceIdentity:
    instance_id: str
    room: str
    state_path: Path


def is_auto_room(value: str | None) -> bool:
    """Whether a configured room should resolve to the instance-owned room."""
    return (value or "").strip().casefold() in _AUTO_ROOM_VALUES


def default_state_path() -> Path:
    explicit = (os.getenv("MATE_INSTANCE_STATE_PATH") or "").strip()
    if explicit:
        return Path(explicit).expanduser()
    hermes_home = Path(os.getenv("HERMES_HOME") or "~/.hermes").expanduser()
    return hermes_home / "mate_voice" / "instance.json"


def _valid_instance_id(value: object) -> str | None:
    candidate = str(value or "").strip()
    return candidate if _INSTANCE_ID_RE.fullmatch(candidate) else None


def _read_instance_id(path: Path) -> str | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    return _valid_instance_id(data.get("instance_id")) if isinstance(data, dict) else None


def _write_state(path: Path, instance_id: str, room: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump({"instance_id": instance_id, "room": room}, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass


def load_instance_identity(
    configured_room: str | None,
    *,
    state_path: Path | None = None,
) -> InstanceIdentity:
    """Load or create the stable identity used by one Hermes installation.

    `auto`, an empty value, and the legacy default `mate-hermes-test` migrate to
    an instance-owned room. Other room names remain an explicit operator
    override, while the instance id is still persisted and exposed to clients.
    """
    path = state_path or default_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(path.suffix + ".lock")

    with lock_path.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        configured_id = _valid_instance_id(os.getenv("MATE_INSTANCE_ID"))
        instance_id = configured_id or _read_instance_id(path) or secrets.token_hex(8)
        room = (
            f"mate-{instance_id.casefold()}"
            if is_auto_room(configured_room)
            else str(configured_room).strip()
        )
        _write_state(path, instance_id, room)
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    return InstanceIdentity(instance_id=instance_id, room=room, state_path=path)
