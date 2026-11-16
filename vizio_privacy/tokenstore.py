"""Where the auth token lives: ``~/.vizio-privacy/<host>.json``, owner-only.

This repository is public, so a token must never be written inside it. The
store keeps one small JSON file per TV host under the user's home directory,
in a directory mode ``0o700`` and a file mode ``0o600``, so only the owner can
read it.

``VIZIO_PRIVACY_HOME`` replaces ``~`` when it is set, which the tests use to
point the store at a temporary directory.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

DIR_MODE = 0o700
FILE_MODE = 0o600


def _home() -> str:
    override = os.environ.get("VIZIO_PRIVACY_HOME")
    if override:
        return override
    return os.path.expanduser("~")


def token_path(host: str) -> str:
    """The path of the token file for ``host``, always outside the repository."""
    return os.path.join(_home(), ".vizio-privacy", "{}.json".format(host))


def save_token(host: str, device_id: str, auth_token: str) -> str:
    """Write the token for ``host`` with owner-only permissions; return its path."""
    path = token_path(host)
    directory = os.path.dirname(path)
    os.makedirs(directory, mode=DIR_MODE, exist_ok=True)
    try:
        os.chmod(directory, DIR_MODE)
    except OSError:
        pass
    payload = {"host": host, "device_id": device_id, "auth_token": auth_token}  # type: Dict[str, Any]
    # Create the file owner-only from the start, so the token is never readable by others.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, FILE_MODE)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(payload, handle)
    os.chmod(path, FILE_MODE)
    return path


def load_token(host: str) -> Optional[dict]:
    """The saved token record for ``host``, or ``None`` when there is none."""
    path = token_path(host)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as handle:
        loaded = json.load(handle)
    return loaded if isinstance(loaded, dict) else None
