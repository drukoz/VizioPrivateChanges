"""Walk the settings tree, plan the privacy changes, and apply them."""

from __future__ import annotations

import dataclasses
import enum
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from vizio_privacy import targets
from vizio_privacy.api import Item, ItemType, ResultStatus, SmartCastClient, SmartCastError

MENU_ROOT = "/menu_native/dynamic/tv_settings"
STATIC_ROOT = "/menu_native/static/tv_settings"

# A menu the walk could not read: (menu path, error text).
WalkError = Tuple[str, str]


class ChangeOutcome(enum.IntEnum):
    ALREADY_PRIVATE = 0  # already at its private value
    WOULD_CHANGE = 1  # dry run: would be changed
    CHANGED = 2  # written and read back
    UNRESOLVED = 3  # matched, but none of its choices is a private value
    NOT_A_LIST = 4  # matched, but not a list the tool can set
    FAILED = 5  # the write was refused, or did not take


@dataclass
class HardenRow:
    path: str  # parent menu path, "" at the top level
    cname: str
    name: Optional[str]
    why: str
    current: Any  # the value of a list item; None for anything else
    desired: Optional[str]
    outcome: ChangeOutcome
    detail: Optional[str] = None  # why it FAILED


def menu_url(path: str) -> str:
    return MENU_ROOT if not path else MENU_ROOT + "/" + path


def static_url(path: str) -> str:
    return STATIC_ROOT if not path else STATIC_ROOT + "/" + path


def _is_private(value: Any, desired: str) -> bool:
    return str(value).strip().lower() == desired.strip().lower()


def _find(items: List[Item], cname: str) -> Optional[Item]:
    for item in items:
        if item.cname == cname:
            return item
    return None


def _walk(
    client: SmartCastClient,
    path: str,
    depth: int,
    max_depth: int,
    out: List[Tuple[str, Item]],
    errors: Optional[List[WalkError]],
) -> None:
    try:
        items = client.get_items(menu_url(path), auth=True)
    except SmartCastError as err:
        if not path or err.result is ResultStatus.REQUIRES_PAIRING:
            raise
        if errors is not None:
            errors.append((path, str(err)))
        return
    for item in items:
        out.append((path, item))
        if item.type is not ItemType.MENU:
            continue
        if targets.skip_menu(item):
            continue
        if depth + 1 > max_depth:
            continue
        child = item.cname if not path else path + "/" + item.cname
        _walk(client, child, depth + 1, max_depth, out, errors)


def dump(
    client: SmartCastClient, max_depth: int = 3, errors: Optional[List[WalkError]] = None
) -> List[Tuple[str, Item]]:
    found = []  # type: List[Tuple[str, Item]]
    _walk(client, "", 0, max_depth, found, errors)
    return found


def _with_choices(
    client: SmartCastClient,
    path: str,
    item: Item,
    cache: Dict[str, List[Item]],
    errors: Optional[List[WalkError]],
) -> Item:
    """The item with its list choices: its own, or else those of the static menu."""
    if item.elements:
        return item
    if path not in cache:
        try:
            cache[path] = client.get_items(static_url(path), auth=True)
        except SmartCastError as err:
            if err.result is ResultStatus.REQUIRES_PAIRING:
                raise
            if errors is not None:
                errors.append((path, "choices: " + str(err)))
            cache[path] = []
    static_item = _find(cache[path], item.cname)
    if static_item is None or not static_item.elements:
        return item
    return dataclasses.replace(item, elements=list(static_item.elements))


def plan(
    client: SmartCastClient, max_depth: int = 3, errors: Optional[List[WalkError]] = None
) -> List[HardenRow]:
    rows = []  # type: List[HardenRow]
    static_cache = {}  # type: Dict[str, List[Item]]
    for path, item in dump(client, max_depth, errors):
        if item.type is ItemType.MENU:
            continue
        why = targets.matches(item)
        if why is None:
            continue
        if item.type not in (ItemType.LIST, ItemType.LIST_X):
            rows.append(
                HardenRow(path, item.cname, item.name, why, None, None, ChangeOutcome.NOT_A_LIST)
            )
            continue
        item = _with_choices(client, path, item, static_cache, errors)
        desired = targets.private_value(item)
        if desired is None:
            rows.append(
                HardenRow(
                    path, item.cname, item.name, why, item.value, None, ChangeOutcome.UNRESOLVED
                )
            )
        elif _is_private(item.value, desired):
            rows.append(
                HardenRow(
                    path,
                    item.cname,
                    item.name,
                    why,
                    item.value,
                    desired,
                    ChangeOutcome.ALREADY_PRIVATE,
                )
            )
        else:
            rows.append(
                HardenRow(
                    path,
                    item.cname,
                    item.name,
                    why,
                    item.value,
                    desired,
                    ChangeOutcome.WOULD_CHANGE,
                )
            )
    return rows


def harden(
    client: SmartCastClient,
    apply: bool = False,
    max_depth: int = 3,
    errors: Optional[List[WalkError]] = None,
) -> List[HardenRow]:
    rows = plan(client, max_depth, errors)
    if not apply:
        return rows
    for row in rows:
        if row.outcome is not ChangeOutcome.WOULD_CHANGE:
            continue
        desired = row.desired
        if desired is None:
            continue
        try:
            fresh = _find(client.get_items(menu_url(row.path), auth=True), row.cname)
            if fresh is None:
                row.outcome = ChangeOutcome.FAILED
                row.detail = "not found on re-read"
                continue
            client.put(
                menu_url(row.path) + "/" + row.cname,
                {"REQUEST": "MODIFY", "HASHVAL": fresh.hashval, "VALUE": desired},
                auth=True,
            )
            check = _find(client.get_items(menu_url(row.path), auth=True), row.cname)
            value = None if check is None else check.value
            if check is not None and _is_private(value, desired):
                row.outcome = ChangeOutcome.CHANGED
            else:
                row.outcome = ChangeOutcome.FAILED
                row.detail = "TV still reports {}".format(value)
        except SmartCastError as err:
            row.outcome = ChangeOutcome.FAILED
            row.detail = str(err)
    return rows
