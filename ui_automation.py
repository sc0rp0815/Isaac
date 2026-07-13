from __future__ import annotations

"""Semantische Android-/Desktop-UI-Steuerung über Accessibility-Baum."""

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any, Optional

from audit import AuditLog

DEVICE_PIN_SECRET_REF = "ISAAC_DEVICE_PIN"

# Android KeyEvent: KEYCODE_0 = 7 … KEYCODE_9 = 16
_DIGIT_KEYCODE: dict[str, int] = {str(d): 7 + d for d in range(10)}
_ANDROID_KEY_ALIASES: dict[str, int] = {
    "enter": 66,
    "back": 4,
    "home": 3,
    "menu": 82,
    "del": 67,
    "delete": 67,
}


@dataclass(frozen=True)
class UINode:
    text: str
    content_desc: str
    resource_id: str
    class_name: str
    clickable: bool
    enabled: bool
    is_password: bool
    bounds: tuple[int, int, int, int]

    @property
    def label(self) -> str:
        return (self.text or self.content_desc or self.resource_id or "").strip()

    def center(self) -> tuple[int, int]:
        x1, y1, x2, y2 = self.bounds
        return ((x1 + x2) // 2, (y1 + y2) // 2)


def parse_bounds(raw: str) -> tuple[int, int, int, int]:
    match = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", (raw or "").strip())
    if not match:
        raise ValueError(f"Ungültige bounds: {raw!r}")
    return tuple(int(match.group(i)) for i in range(1, 5))


def _node_bool(value: str) -> bool:
    return (value or "").strip().lower() == "true"


def parse_ui_xml(xml_text: str) -> list[UINode]:
    root = ET.fromstring(xml_text)
    nodes: list[UINode] = []
    for element in root.iter("node"):
        bounds_raw = element.attrib.get("bounds", "")
        if not bounds_raw:
            continue
        try:
            bounds = parse_bounds(bounds_raw)
        except ValueError:
            continue
        nodes.append(
            UINode(
                text=element.attrib.get("text", ""),
                content_desc=element.attrib.get("content-desc", ""),
                resource_id=element.attrib.get("resource-id", ""),
                class_name=element.attrib.get("class", ""),
                clickable=_node_bool(element.attrib.get("clickable", "false")),
                enabled=_node_bool(element.attrib.get("enabled", "true")),
                is_password=_node_bool(element.attrib.get("password", "false")),
                bounds=bounds,
            )
        )
    return nodes


def _normalize_label(value: str) -> str:
    text = (value or "").strip().lower()
    return (
        text.replace("ä", "ae")
        .replace("ö", "oe")
        .replace("ü", "ue")
        .replace("ß", "ss")
    )


def _fold_label(value: str) -> str:
    folded = _normalize_label(value)
    return (
        folded.replace("ae", "a")
        .replace("oe", "o")
        .replace("ue", "u")
    )


def _labels_match(query: str, label: str, *, exact: bool) -> bool:
    if exact:
        return _normalize_label(query) == _normalize_label(label)
    pairs = (
        (_normalize_label(query), _normalize_label(label)),
        (_fold_label(query), _fold_label(label)),
    )
    for needle, hay in pairs:
        if not needle or not hay:
            continue
        if needle in hay or hay in needle:
            return True
    return False


def find_nodes(
    nodes: list[UINode],
    query: str,
    *,
    exact: bool = False,
    clickable_only: bool = True,
) -> list[UINode]:
    if not (query or "").strip():
        return []
    matches: list[UINode] = []
    for node in nodes:
        if clickable_only and not node.clickable:
            continue
        if not node.enabled:
            continue
        if not node.label:
            continue
        if _labels_match(query, node.label, exact=exact):
            matches.append(node)
    matches.sort(key=lambda n: (n.bounds[1], n.bounds[0]))
    return matches


def list_interactive_labels(nodes: list[UINode], *, limit: int = 40) -> list[str]:
    seen: set[str] = set()
    labels: list[str] = []
    for node in nodes:
        if not node.clickable or not node.enabled:
            continue
        label = node.label
        if not label or label in seen:
            continue
        seen.add(label)
        labels.append(label)
        if len(labels) >= limit:
            break
    return labels


def summarize_nodes(nodes: list[UINode], *, limit: int = 40) -> str:
    labels = list_interactive_labels(nodes, limit=limit)
    if not labels:
        return "(keine klickbaren UI-Elemente gefunden)"
    return "\n".join(f"- {label}" for label in labels)


def extract_ui_dump(stdout: str) -> str:
    text = (stdout or "").strip()
    if not text:
        return ""
    if text.startswith("<?xml") or text.startswith("<hierarchy"):
        return text
    start = text.find("<?xml")
    if start == -1:
        start = text.find("<hierarchy")
    if start >= 0:
        return text[start:]
    return ""


UI_DUMP_COMMANDS: tuple[str, ...] = (
    "uiautomator dump /dev/tty 2>/dev/null",
    "uiautomator dump /data/local/tmp/isaac_ui.xml 2>/dev/null && cat /data/local/tmp/isaac_ui.xml",
    "uiautomator dump /sdcard/isaac_ui.xml 2>/dev/null && cat /sdcard/isaac_ui.xml",
    "adb shell uiautomator dump /sdcard/isaac_ui.xml 2>/dev/null && adb shell cat /sdcard/isaac_ui.xml",
)


def android_keycode(name_or_code: str) -> int:
    raw = (name_or_code or "").strip().lower()
    if not raw:
        raise ValueError("Leerer Keycode")
    if raw.isdigit() and len(raw) > 1:
        return int(raw)
    if raw in _ANDROID_KEY_ALIASES:
        return _ANDROID_KEY_ALIASES[raw]
    if raw.isdigit() and len(raw) == 1:
        return _DIGIT_KEYCODE[raw]
    raise ValueError(f"Unbekannter Keycode: {name_or_code}")


def load_device_pin(secret_ref: str = DEVICE_PIN_SECRET_REF) -> Optional[str]:
    from secrets_store import get_secrets_store

    pin = (get_secrets_store().get_secret(secret_ref) or "").strip()
    if not pin:
        return None
    if not pin.isdigit():
        raise ValueError("Geräte-PIN muss numerisch sein")
    if len(pin) < 4 or len(pin) > 16:
        raise ValueError("Geräte-PIN hat ungültige Länge")
    return pin


def pin_keycodes(pin: str) -> list[int]:
    return [android_keycode(ch) for ch in pin]


def audit_ui_action(action: str, detail: str) -> None:
    AuditLog.action("UIAutomation", action, detail[:180], level=40)