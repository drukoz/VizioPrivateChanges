"""The TV's three-step PIN pairing: start, pair with the on-screen PIN, cancel.

Pairing is the only way to obtain the auth token that every ``/menu_native/``
call needs. ``begin_pair`` starts a session and the TV puts a 4-digit PIN on
the owner's screen; ``finish_pair`` trades that PIN for an auth token;
``cancel_pair`` abandons a session that was never completed.

The challenge type and the pairing request token travel as the TV's
integers, never as text. This module opens no socket of its own: it uses the
``SmartCastClient`` given to it, so the tests inject a fake transport.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from vizio_privacy.api import (
    ResultStatus,
    SmartCastClient,
    SmartCastError,
    _ci_get,
)

DEFAULT_DEVICE_ID = "vizio-privacy"
DEFAULT_DEVICE_NAME = "Vizio Privacy"


@dataclass
class PairStart:
    """What ``/pairing/start`` answers: the challenge and the token to pair with."""

    challenge_type: int
    pairing_token: int


def _pairing_item(envelope: Dict[str, Any]) -> Dict[str, Any]:
    """Return the ``ITEM`` of a pairing answer (pairing answers use ITEM, not ITEMS)."""
    item = _ci_get(envelope, "ITEM", {})
    if not isinstance(item, dict):
        raise SmartCastError(ResultStatus.UNKNOWN, "pairing answer has no ITEM")
    return item


def begin_pair(
    client: SmartCastClient,
    device_id: str = DEFAULT_DEVICE_ID,
    device_name: str = DEFAULT_DEVICE_NAME,
) -> PairStart:
    """Start a pairing session; the TV shows a 4-digit PIN on screen."""
    envelope = client.put(
        "/pairing/start",
        {"DEVICE_ID": device_id, "DEVICE_NAME": device_name},
        auth=False,
    )
    item = _pairing_item(envelope)
    challenge_type = _ci_get(item, "CHALLENGE_TYPE")
    pairing_token = _ci_get(item, "PAIRING_REQ_TOKEN")
    if challenge_type is None or pairing_token is None:
        raise SmartCastError(
            ResultStatus.INVALID_PARAMETER, "pairing/start answer is missing a field"
        )
    return PairStart(challenge_type=int(challenge_type), pairing_token=int(pairing_token))


def finish_pair(
    client: SmartCastClient,
    challenge_type: int,
    pairing_token: int,
    pin: str,
    device_id: str = DEFAULT_DEVICE_ID,
) -> str:
    """Trade the on-screen PIN for the auth token."""
    envelope = client.put(
        "/pairing/pair",
        {
            "DEVICE_ID": device_id,
            "CHALLENGE_TYPE": int(challenge_type),
            "PAIRING_REQ_TOKEN": int(pairing_token),
            "RESPONSE_VALUE": str(pin),
        },
        auth=False,
    )
    item = _pairing_item(envelope)
    auth_token = _ci_get(item, "AUTH_TOKEN")
    if auth_token is None:
        raise SmartCastError(ResultStatus.INVALID_PARAMETER, "pairing/pair answer has no AUTH_TOKEN")
    return str(auth_token)


def cancel_pair(
    client: SmartCastClient,
    device_id: str = DEFAULT_DEVICE_ID,
    device_name: str = DEFAULT_DEVICE_NAME,
) -> None:
    """Abandon a started pairing. A pairing that already finished is not an error."""
    try:
        client.put(
            "/pairing/cancel",
            {"DEVICE_ID": device_id, "DEVICE_NAME": device_name},
            auth=False,
        )
    except SmartCastError:
        return None
