"""Isaac – Owner-Action Routing (nur ISAAC_PRIVILEGE_MODE=admin)

Erkennt imperative Owner-Befehle in natürlicher Sprache und führt sie
über vorhandene Ausführungspfade aus (Shell, Browser, Dateien, Suche).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.parse import quote_plus

from audit import AuditLog
from config import BASE_DIR, DATA_DIR, LOG_DIR, WORKSPACE, get_config, is_owner_equivalent_mode

log = logging.getLogger("Isaac.OwnerAction")

_EXPLANATORY_PREFIXES = (
    "erkläre ",
    "erklaere ",
    "erklär ",
    "erklaer ",
    "was ist ",
    "was bedeutet ",
    "wie funktioniert ",
    "warum ",
    "beschreibe ",
    "vergleiche ",
    "diskutiere ",
    "erzähl ",
    "erzaehl ",
)

_ACTION_VERBS = (
    "suche", "such", "finde", "find", "hol", "hole", "zeig", "zeige",
    "öffne", "oeffne", "navigiere", "verbinde", "verbind", "räum", "raeum",
    "aufräum", "aufraeum", "bereinige", "lösch", "loesch", "verschiebe",
    "kopiere", "installiere", "starte", "führe aus", "fuehre aus",
    "stell ein", "setz", "mach", "liste", "scanne", "scann",
    "schreib", "sende", "rufe", "telefoniere", "lies", "lese", "erstelle",
    "schick", "fotografiere", "nimm", "spiele", "übersetze", "uebersetze",
    "lade", "downloade", "ping", "vibriere", "benachrichtige", "erinnere",
    "komprimiere", "entpacke", "packe", "teile", "stoppe", "aktiviere",
    "deaktiviere", "schalte", "wechsle", "prüfe", "pruefe", "teste",
)

_PHOTOS_MARKERS = (
    "google fotos", "google photos", "photos.google", "fotos app", " foto ",
    "meine fotos", "meinen fotos", "in fotos", "lokale fotos", "galerie",
)
_WLAN_MARKERS = ("wlan", "wifi", "netzwerk", "hotspot")
_ROUTER_MARKERS = ("router", "fritzbox", "fritz!box", "gateway", "modem")
_CLEANUP_MARKERS = (
    "dateisystem", "dateien", "ordner", "speicher", "festplatte", "system",
    "aufräumen", "aufraeumen", "aufräum", "aufraeum", "bereinige", "cleanup", "müll", "muell",
    "downloads", "download", "cache", "temp", "tmp",
)
_OPEN_PREFIXES = ("öffne ", "oeffne ", "navigiere ", "starte ")
_WEB_SEARCH_MARKERS = ("google", "duckduckgo", "im web", "internet", "online", "web")
_EMAIL_MARKERS = ("gmail", "e-mail", "email", "mail", "posteingang", "postfach", "inbox")
_CALENDAR_MARKERS = ("kalender", "calendar", "termin", "termine", "agenda")
_MAPS_MARKERS = ("maps", "karte", "navigation", "route", "weg")
_DEVICE_STATUS_MARKERS = ("akku", "batterie", "speicherplatz", "speicher frei", "ip-adresse", "ip adresse")
_MUSIC_MARKERS = ("spotify", "musik", "music", "song", "lied", "playlist", "höre", "hoere")
_VIDEO_MARKERS = ("youtube", "video", "clip", "trailer")
_WEATHER_MARKERS = ("wetter", "weather", "temperatur", "regenvorhersage", "vorhersage")
_TRANSLATE_MARKERS = ("übersetze", "uebersetze", "übersetz", "uebersetz", "translate")
_TIMER_MARKERS = ("timer", "countdown", "stoppuhr")
_ALARM_MARKERS = ("wecker", "alarm")
_CONTACT_MARKERS = ("kontakt", "kontakte", "telefonbuch", "contacts")
_BLUETOOTH_MARKERS = ("bluetooth", "bluetooth")
_TORCH_MARKERS = ("taschenlampe", "torch", "flashlight", "blitzlicht")
_LOCATION_MARKERS = ("standort", "position", "gps", "koordinaten")
_CREDENTIAL_MARKERS = (
    "passwort", "passwörter", "passwoerter", "login", "logins", "zugangsdaten",
    "credentials", "credential", "anmeldedaten", "passwort-manager", "passwort manager",
)
_NOTIFICATION_MARKERS = ("benachrichtigung", "notification", "notify")
_GIT_MARKERS = (
    "git status", "git pull", "git log", "git diff", "git commit", "git restore", "git fetch",
)
_INSTALL_MARKERS = ("installiere", "apt install", "pip install", "pkg install")
_ISAAC_MARKERS = ("isaac status", "isaac log", "isaac logs", "isaac neustart", "isaac restart")
_SHOPPING_MARKERS = ("amazon", "ebay", "kleinanzeigen")
_VPN_MARKERS = ("vpn",)
_HOTSPOT_MARKERS = ("hotspot", "tethering")
_MOBILE_DATA_MARKERS = ("mobile daten", "mobilfunk", "lte", "5g daten")

_SITE_ALIASES: dict[str, str] = {
    "google fotos": "https://photos.google.com/",
    "google photos": "https://photos.google.com/",
    "gmail": "https://mail.google.com/",
    "google mail": "https://mail.google.com/",
    "posteingang": "https://mail.google.com/",
    "postfach": "https://mail.google.com/",
    "google kalender": "https://calendar.google.com/",
    "kalender": "https://calendar.google.com/",
    "youtube": "https://www.youtube.com/",
    "google drive": "https://drive.google.com/",
    "google": "https://www.google.com/",
    "github": "https://github.com/",
    "maps": "https://maps.google.com/",
    "google maps": "https://maps.google.com/",
    "whatsapp": "https://web.whatsapp.com/",
    "spotify": "https://open.spotify.com/",
    "wikipedia": "https://de.wikipedia.org/",
    "übersetzer": "https://translate.google.com/",
    "uebersetzer": "https://translate.google.com/",
    "google translate": "https://translate.google.com/",
    "amazon": "https://www.amazon.de/",
    "ebay": "https://www.ebay.de/",
    "netflix": "https://www.netflix.com/",
    "reddit": "https://www.reddit.com/",
    "twitter": "https://twitter.com/",
    "x": "https://x.com/",
    "instagram": "https://www.instagram.com/",
    "facebook": "https://www.facebook.com/",
    "telegram": "https://web.telegram.org/",
    "discord": "https://discord.com/app",
    "linkedin": "https://www.linkedin.com/",
    "outlook": "https://outlook.live.com/",
    "chatgpt": "https://chatgpt.com/",
    "openai": "https://chatgpt.com/",
    "deepl": "https://www.deepl.com/translator",
    "dropbox": "https://www.dropbox.com/",
    "onedrive": "https://onedrive.live.com/",
    "paypal": "https://www.paypal.com/",
    "news": "https://news.google.com/",
    "google news": "https://news.google.com/",
    "keep": "https://keep.google.com/",
    "google keep": "https://keep.google.com/",
    "notizen": "https://keep.google.com/",
    "docs": "https://docs.google.com/",
    "sheets": "https://sheets.google.com/",
    "google sheets": "https://sheets.google.com/",
    "google docs": "https://docs.google.com/",
    "twitch": "https://www.twitch.tv/",
    "soundcloud": "https://soundcloud.com/",
    "ard": "https://www.ardmediathek.de/",
    "zdf": "https://www.zdf.de/",
    "wetter": "https://www.google.com/search?q=wetter",
    "weather": "https://www.google.com/search?q=weather",
    "kleinanzeigen": "https://www.kleinanzeigen.de/",
    "booking": "https://www.booking.com/",
    "maps offline": "https://maps.google.com/",
}

_ANDROID_INTENTS: dict[str, str] = {
    "einstellungen": "android.settings.SETTINGS",
    "settings": "android.settings.SETTINGS",
    "wlan": "android.settings.WIFI_SETTINGS",
    "wifi": "android.settings.WIFI_SETTINGS",
    "bluetooth": "android.settings.BLUETOOTH_SETTINGS",
    "speicher": "android.settings.INTERNAL_STORAGE_SETTINGS",
    "storage": "android.settings.INTERNAL_STORAGE_SETTINGS",
    "standort": "android.settings.LOCATION_SOURCE_SETTINGS",
    "location": "android.settings.LOCATION_SOURCE_SETTINGS",
    "kamera": "android.media.action.IMAGE_CAPTURE",
    "camera": "android.media.action.IMAGE_CAPTURE",
    "flugmodus": "android.settings.AIRPLANE_MODE_SETTINGS",
    "flugzeugmodus": "android.settings.AIRPLANE_MODE_SETTINGS",
    "akku": "android.intent.action.POWER_USAGE_SUMMARY",
    "batterie": "android.intent.action.POWER_USAGE_SUMMARY",
    "display": "android.settings.DISPLAY_SETTINGS",
    "bildschirm": "android.settings.DISPLAY_SETTINGS",
    "sound": "android.settings.SOUND_SETTINGS",
    "lautstärke": "android.settings.SOUND_SETTINGS",
    "lautstaerke": "android.settings.SOUND_SETTINGS",
    "benachrichtigungen": "android.settings.NOTIFICATION_SETTINGS",
    "notifications": "android.settings.NOTIFICATION_SETTINGS",
    "entwickleroptionen": "android.settings.APPLICATION_DEVELOPMENT_SETTINGS",
    "entwickler": "android.settings.APPLICATION_DEVELOPMENT_SETTINGS",
    "apps": "android.settings.APPLICATION_SETTINGS",
    "anwendungen": "android.settings.APPLICATION_SETTINGS",
    "datenschutz": "android.settings.PRIVACY_SETTINGS",
    "sicherheit": "android.settings.SECURITY_SETTINGS",
    "tastatur": "android.settings.INPUT_METHOD_SETTINGS",
    "nfc": "android.settings.NFC_SETTINGS",
    "hotspot": "android.settings.TETHER_SETTINGS",
    "usb": "android.settings.USB_SETTINGS",
    "uhr": "android.intent.action.SET_ALARM",
    "wecker": "android.intent.action.SET_ALARM",
    "rechner": "com.android.calculator2",
    "taschenrechner": "com.android.calculator2",
    "calculator": "com.android.calculator2",
    "uhrzeit": "com.android.deskclock",
    "clock": "com.android.deskclock",
    "telefon": "android.intent.action.DIAL",
    "telefonie": "android.intent.action.DIAL",
    "vpn": "android.settings.VPN_SETTINGS",
    "mobilfunk": "android.settings.DATA_ROAMING_SETTINGS",
    "datenroaming": "android.settings.DATA_ROAMING_SETTINGS",
    "sprachassistent": "android.intent.action.VOICE_COMMAND",
    "qr": "com.google.zxing.client.android.SCAN",
    "barcode": "com.google.zxing.client.android.SCAN",
    "barcode scanner": "com.google.zxing.client.android.SCAN",
    "wlan direct": "android.settings.WIFI_SETTINGS",
    "sprache": "android.settings.LOCALE_SETTINGS",
    "sprachen": "android.settings.LOCALE_SETTINGS",
    "backup": "android.settings.BACKUP_AND_RESET_SETTINGS",
    "werksreset": "android.settings.MASTER_CLEAR",
    "zugriffshilfen": "android.settings.ACCESSIBILITY_SETTINGS",
    "barrierefreiheit": "android.settings.ACCESSIBILITY_SETTINGS",
    "wlan calling": "android.settings.WIFI_SETTINGS",
}

# Android app packages (launch real apps via am / monkey / termux-open)
# Prefer this over Playwright when user says "öffne Chrome".
_APP_PACKAGES: dict[str, str] = {
    "chrome": "com.android.chrome",
    "google chrome": "com.android.chrome",
    "chromium": "org.chromium.chrome",
    "firefox": "org.mozilla.firefox",
    "gmail": "com.google.android.gm",
    "google mail": "com.google.android.gm",
    "maps": "com.google.android.apps.maps",
    "google maps": "com.google.android.apps.maps",
    "youtube": "com.google.android.youtube",
    "yt": "com.google.android.youtube",
    "whatsapp": "com.whatsapp",
    "telegram": "org.telegram.messenger",
    "signal": "org.thoughtcrime.securesms",
    "photos": "com.google.android.apps.photos",
    "google fotos": "com.google.android.apps.photos",
    "fotos": "com.google.android.apps.photos",
    "kamera": "com.sec.android.app.camera",
    "camera": "com.sec.android.app.camera",
    "play store": "com.android.vending",
    "playstore": "com.android.vending",
    "files": "com.google.android.apps.nbu.files",
    "dateien": "com.google.android.apps.nbu.files",
    "settings": "com.android.settings",
    "einstellungen": "com.android.settings",
    "calendar": "com.google.android.calendar",
    "kalender": "com.google.android.calendar",
    "contacts": "com.samsung.android.contacts",
    "kontakte": "com.samsung.android.contacts",
    "phone": "com.samsung.android.dialer",
    "telefon": "com.samsung.android.dialer",
    "messages": "com.samsung.android.messaging",
    "sms": "com.samsung.android.messaging",
    "clock": "com.sec.android.app.clockpackage",
    "uhr": "com.sec.android.app.clockpackage",
    "calculator": "com.sec.android.app.popupcalculator",
    "rechner": "com.sec.android.app.popupcalculator",
    "spotify": "com.spotify.music",
    "netflix": "com.netflix.mediaclient",
    "instagram": "com.instagram.android",
    "facebook": "com.facebook.katana",
    "x": "com.twitter.android",
    "twitter": "com.twitter.android",
    "termux": "com.termux",
}

_BRIDGE_SETUP_HINT = (
    "Android-Apps starten braucht die Termux-Brücke.\n"
    "In der Termux-App:\n"
    "  pkg install openssh termux-api tsu\n"
    "  bash scripts/setup_termux_bridge.sh\n"
    "Dann: apps status"
)

_CLEANUP_PROTECTED_NAMES = frozenset({
    ".git", ".env", ".venv", "isaac.db", "audit.jsonl", "constitution.json",
})
_CLEANUP_MAX_DEPTH = 8


@dataclass(frozen=True)
class OwnerAction:
    kind: str
    params: dict[str, Any] = field(default_factory=dict)
    raw: str = ""


@dataclass
class CleanupStats:
    removed_dirs: list[str] = field(default_factory=list)
    removed_files: list[str] = field(default_factory=list)
    freed_bytes: int = 0
    skipped: list[str] = field(default_factory=list)


def _normalize(text: str) -> str:
    t = (text or "").strip().lower()
    t = re.sub(r"^isaac[,:]\s+", "", t)
    t = re.sub(r"\s+", " ", t)
    return t


def _is_explanatory(normalized: str) -> bool:
    if any(normalized.startswith(p) for p in _EXPLANATORY_PREFIXES):
        return True
    if re.search(r"\b(als motiv|in der literatur|literarisch|metapher)\b", normalized):
        return True
    return False


def _is_owner_imperative(normalized: str) -> bool:
    if normalized in {"speedtest", "geschwindigkeitstest", "internetgeschwindigkeit"}:
        return True
    if _extract_toggle_target(normalized):
        return True
    if normalized.startswith(("git ", "isaac ", "ping ", "ping6 ", "timer ", "wecker ", "alarm ")):
        return True
    if _has_action_verb(normalized):
        return True
    status_patterns = (
        r"was steht .+ kalender",
        r"was habe ich .+ kalender",
        r"wie (voll|viel) .+ speicher",
        r"wie ist (der )?(akku|batterie)",
        r"(welche|meine) ip",
        r"ip.adresse",
        r"wie spät",
        r"wie spaet",
        r"welcher tag",
        r"wo bin ich",
        r"wie ist das wetter",
        r"wie wird das wetter",
    )
    return any(re.search(p, normalized) for p in status_patterns)


def _has_action_verb(normalized: str) -> bool:
    if not normalized:
        return False
    multi = ("führe aus", "fuehre aus")
    if any(normalized.startswith(m) for m in multi):
        return True
    first = normalized.split()[0]
    return any(
        normalized == v
        or normalized.startswith(v + " ")
        or first.startswith(v)
        or f" {v} " in f" {normalized} "
        for v in _ACTION_VERBS
    )


def _contains_any(text: str, markers: tuple[str, ...]) -> bool:
    return any(m in text for m in markers)


def _wants_dry_run(normalized: str) -> bool:
    return any(
        t in normalized
        for t in (
            "nur anzeigen", "zeig mir was", "was würde", "was wuerde",
            "dry run", "dry-run", "vorher anzeigen", "nur listen", "simulation",
        )
    )


def _wants_deep_clean(normalized: str) -> bool:
    return any(t in normalized for t in ("gründlich", "gruendlich", "komplett", "alles", "tiefenreinigung", "deep"))


def _extract_photos_query(text: str) -> str:
    patterns = (
        r"(?:in\s+)?(?:meinen?\s+)?fotos\s+nach\s+(.+)$",
        r"(?:über|ueber|nach|mit|von|für|fuer|about|mit dem thema)\s+(.+)$",
        r"(?:raus|heraus)\s+(?:über|ueber|nach|mit|von|für|fuer)\s+(.+)$",
        r"google\s+fotos\s+(?:nach\s+)?(.+)$",
        r"google\s+photos\s+(?:nach\s+)?(.+)$",
        r"fotos\s+(?:nach|über|ueber)\s+(.+)$",
        r"galerie\s+nach\s+(.+)$",
    )
    for pattern in patterns:
        m = re.search(pattern, text, re.I)
        if m:
            q = m.group(1).strip(" .,!?:")
            q = re.sub(r"^(raus|heraus)\s+", "", q, flags=re.I)
            if q and q.lower() not in _PHOTOS_MARKERS:
                return q
    lower = text.lower()
    for marker in ("google fotos", "google photos"):
        if marker in lower:
            tail = text[lower.index(marker) + len(marker):].strip(" :.,!?")
            if tail and len(tail) > 2:
                return tail
    return ""


def _extract_web_query(text: str) -> str:
    patterns = (
        r"(?:suche|such|finde)\s+(?:mir\s+)?(?:bei\s+)?google\s+(?:nach\s+)?(.+)$",
        r"(?:suche|such|finde)\s+(?:mir\s+)?(?:im\s+)?(?:web|internet|online)\s+(?:nach\s+)?(.+)$",
        r"(?:suche|such|finde)\s+(?:mir\s+)?(?:nach\s+)?(.+)$",
    )
    skip_markers = (
        _PHOTOS_MARKERS + _WLAN_MARKERS + _ROUTER_MARKERS + _CLEANUP_MARKERS
        + _EMAIL_MARKERS + _CALENDAR_MARKERS + ("fotos", "galerie", "mail", "sms")
    )
    for pattern in patterns:
        m = re.search(pattern, text, re.I)
        if m:
            q = m.group(1).strip(" .,!?:")
            if q and not _contains_any(q.lower(), skip_markers):
                return q
    return ""


def _extract_ssid(text: str) -> str:
    quoted = re.search(r"[\"']([^\"']{2,32})[\"']", text)
    if quoted:
        return quoted.group(1).strip()
    patterns = (
        r"(?:wlan|wifi|netzwerk|hotspot)\s+([a-zA-Z0-9äöüÄÖÜß\-_\.]{2,32})",
        r"(?:mit|zu|auf)\s+([a-zA-Z0-9äöüÄÖÜß\-_\.]{2,32})\s*$",
    )
    lower = text.lower()
    for pattern in patterns:
        m = re.search(pattern, text, re.I)
        if m:
            ssid = m.group(1).strip()
            if ssid.lower() not in {"wlan", "wifi", "router", "netzwerk", "dem", "der", "die", "das"}:
                return ssid
    return ""


def _extract_path_hint(text: str) -> str:
    patterns = (
        r"(?:in|im|aus|unter)\s+([~/][^\s]+)",
        r"(?:in|im|aus|unter)\s+([a-z]:\\[^\s]+)",
        r"(?:ordner|verzeichnis|pfad)\s+([~/][^\s]+)",
        r"(?:ordner|verzeichnis|pfad)\s+([^\s]+)",
    )
    for pattern in patterns:
        m = re.search(pattern, text, re.I)
        if m:
            return m.group(1).strip(" .,!?")
    lower = text.lower()
    named_roots = {
        "downloads": "~/Downloads",
        "download": "~/Downloads",
        "dcim": "~/DCIM",
        "bilder": "~/Pictures",
        "pictures": "~/Pictures",
        "dokumente": "~/Documents",
        "documents": "~/Documents",
    }
    for name, path in named_roots.items():
        if re.search(rf"\b{re.escape(name)}\b", lower):
            return path
    return ""


def _extract_email_recipient(text: str) -> str:
    patterns = (
        r"(?:schreib|sende|schick)\s+(?:e-?mail|mail)\s+an\s+(.+)$",
        r"(?:schreib|sende)\s+an\s+(.+?)\s+(?:e-?mail|mail)\b",
    )
    for pattern in patterns:
        m = re.search(pattern, text, re.I)
        if m:
            return m.group(1).strip(" .,!?")
    return ""


def _extract_email_search_query(text: str) -> str:
    patterns = (
        r"(?:suche|such|finde)\s+(?:in\s+)?(?:mails?|e-?mails?|posteingang|gmail)\s+nach\s+(.+)$",
        r"(?:suche|such)\s+(?:mails?|e-?mails?)\s+nach\s+(.+)$",
    )
    for pattern in patterns:
        m = re.search(pattern, text, re.I)
        if m:
            return m.group(1).strip(" .,!?:")
    return ""


def _extract_maps_destination(text: str) -> str:
    patterns = (
        r"navigiere\s+nach\s+(.+)$",
        r"route\s+nach\s+(.+)$",
        r"weg\s+nach\s+(.+)$",
        r"fahr\s+nach\s+(.+)$",
        r"bringe\s+mich\s+nach\s+(.+)$",
        r"(?:suche|such|finde)\s+(?:auf\s+)?(?:maps|karte)\s+(.+)$",
    )
    for pattern in patterns:
        m = re.search(pattern, text, re.I)
        if m:
            dest = m.group(1).strip(" .,!?:")
            if dest.lower() not in _SITE_ALIASES:
                return dest
    return ""


def _extract_phone_number(text: str) -> str:
    patterns = (
        r"(?:rufe|telefoniere|call)\s+(?:an\s+)?(.+)$",
        r"(?:schick|sende)\s+sms\s+an\s+(.+)$",
        r"(?:schreib|sende)\s+(?:eine\s+)?sms\s+an\s+(.+)$",
    )
    for pattern in patterns:
        m = re.search(pattern, text, re.I)
        if m:
            return m.group(1).strip(" .,!?:")
    phone = re.search(r"(?:\+|00)?[\d\s\-/]{6,20}", text)
    return phone.group(0).strip() if phone else ""


def _extract_sms_body(text: str) -> str:
    m = re.search(r"(?:sms|nachricht)\s+(?:mit\s+)?(?:inhalt|text)\s+(.+)$", text, re.I)
    if m:
        return m.group(1).strip(" .,!?")
    m = re.search(r"(?:schick|sende)\s+sms\s+an\s+.+?\s+(.+)$", text, re.I)
    if m and not re.match(r"^[\d\s\+\-/]+$", m.group(1).strip()):
        return m.group(1).strip(" .,!?")
    return ""


def _extract_file_paths(text: str) -> tuple[str, str, str]:
    """Returns (operation, source, destination). destination empty for read/delete."""
    transfer_patterns = (
        (r"(?:kopiere|copy)\s+(.+?)\s+nach\s+(.+)$", "copy"),
        (r"(?:verschiebe|move)\s+(.+?)\s+nach\s+(.+)$", "move"),
    )
    for pattern, op in transfer_patterns:
        m = re.search(pattern, text, re.I)
        if m:
            return op, m.group(1).strip(" .,!?\"'"), m.group(2).strip(" .,!?\"'")
    single_patterns = (
        (r"(?:lösche|loesch|delete)\s+(?:datei\s+)?(.+)$", "delete"),
        (r"(?:lies|lese|read)\s+datei\s+(.+)$", "read"),
        (r"(?:lies|lese|read)\s+([~/][^\s]+)$", "read"),
    )
    for pattern, op in single_patterns:
        m = re.search(pattern, text, re.I)
        if m:
            return op, m.group(1).strip(" .,!?\"'"), ""
    return "", "", ""


def _extract_translate_text(text: str) -> tuple[str, str]:
    patterns = (
        r"(?:übersetze|uebersetze|translate)\s+(.+?)\s+(?:nach|in|to)\s+([a-zäöüß]{2,12})$",
        r"(?:übersetze|uebersetze|translate)\s+(.+)$",
    )
    for pattern in patterns:
        m = re.search(pattern, text, re.I)
        if m:
            if m.lastindex and m.lastindex >= 2:
                return m.group(1).strip(" .,!?\"'"), m.group(2).strip()
            return m.group(1).strip(" .,!?\"'"), "en"
    return "", ""


def _extract_weather_location(text: str) -> str:
    patterns = (
        r"(?:wetter|weather)\s+(?:in|für|fuer|bei)\s+(.+)$",
        r"(?:zeige|zeig|hol)\s+(?:das\s+)?wetter\s+(?:in|für|fuer|bei)\s+(.+)$",
        r"(?:wie (?:ist|wird) das )?wetter\s+(?:in|für|fuer|bei)\s+(.+)$",
    )
    for pattern in patterns:
        m = re.search(pattern, text, re.I)
        if m:
            loc = m.group(1).strip(" .,!?")
            if loc.lower() not in ("literatur", "motiv", "metapher"):
                return loc
    if re.search(r"\b(wetter|weather)\b", text, re.I):
        return ""
    return ""


def _extract_media_query(text: str) -> tuple[str, str]:
    patterns = (
        (r"(?:spiele|höre|hoere|starte)\s+(?:auf\s+)?spotify\s+(.+)$", "spotify"),
        (r"(?:spiele|zeige|such)\s+(?:auf\s+)?youtube\s+(.+)$", "youtube"),
        (r"(?:spiele|zeige)\s+(?:video|clip)\s+(.+)$", "youtube"),
        (r"(?:spiele|höre|hoere)\s+(?:musik|song|lied)\s+(.+)$", "spotify"),
    )
    for pattern, platform in patterns:
        m = re.search(pattern, text, re.I)
        if m:
            return platform, m.group(1).strip(" .,!?")
    return "", ""


def _extract_timer_seconds(text: str) -> int:
    m = re.search(
        r"(?:timer|countdown)\s+(?:für|fuer|auf)?\s*(\d+)\s*(sek|sekunden|min|minuten|h|stunden)?",
        text,
        re.I,
    )
    if not m:
        m = re.search(r"(\d+)\s*(sekunden|minuten|stunden)\s+timer", text, re.I)
    if not m:
        return 0
    value = int(m.group(1))
    unit = (m.group(2) or "min").lower()
    if unit.startswith("sek"):
        return value
    if unit.startswith("h") or unit.startswith("st"):
        return value * 3600
    return value * 60


def _extract_alarm_time(text: str) -> str:
    m = re.search(r"(?:wecker|alarm)\s+(?:auf|um|für|fuer)?\s*(\d{1,2}[:.]\d{2})", text, re.I)
    if m:
        return m.group(1).replace(".", ":")
    m = re.search(r"(?:wecker|alarm)\s+(?:auf|um|für|fuer)?\s*(\d{1,2})\s*uhr", text, re.I)
    if m:
        return f"{int(m.group(1)):02d}:00"
    return ""


def _extract_contact_query(text: str) -> str:
    patterns = (
        r"(?:suche|such|finde)\s+kontakt\s+(.+)$",
        r"(?:zeige|zeig)\s+kontakt\s+(.+)$",
        r"(?:rufe|telefoniere)\s+(.+?)\s+an$",
    )
    for pattern in patterns:
        m = re.search(pattern, text, re.I)
        if m:
            name = m.group(1).strip(" .,!?")
            if not re.match(r"^[\d\s\+\-/]+$", name):
                return name
    return ""


def _extract_download_url(text: str) -> str:
    m = re.search(r"(?:https?://|www\.)[^\s]+", text, re.I)
    return m.group(0).strip() if m else ""


def _extract_file_write(text: str) -> tuple[str, str]:
    patterns = (
        r"(?:schreibe|schreib)\s+(?:in\s+)?datei\s+([^\s]+)\s+(?:inhalt|content)\s*:\s*(.+)$",
        r"(?:schreibe|schreib)\s+(?:in\s+)?datei\s+([^\s]+)\s+(.+)$",
        r"(?:schreibe|schreib)\s+(?:in\s+)?([~/][^\s]+)\s+(?:inhalt|content)\s*:\s*(.+)$",
        r"(?:schreibe|schreib)\s+(?:in\s+)?([~/][^\s]+)\s+(.+)$",
    )
    for pattern in patterns:
        m = re.search(pattern, text, re.I)
        if m:
            return m.group(1).strip(" .,!?\"'"), m.group(2).strip()
    return "", ""


def _extract_find_file(text: str) -> tuple[str, str]:
    patterns = (
        r"(?:finde|such|suche)\s+datei\s+(.+?)(?:\s+in\s+(.+))?$",
        r"(?:finde|such|suche)\s+(.+\.\w{1,6})(?:\s+in\s+(.+))?$",
    )
    for pattern in patterns:
        m = re.search(pattern, text, re.I)
        if m:
            name = m.group(1).strip(" .,!?\"'")
            root = (m.group(2) or "~").strip(" .,!?\"'") if m.lastindex and m.lastindex >= 2 else "~"
            return name, root
    return "", ""


def _extract_archive_paths(text: str) -> tuple[str, str, str]:
    patterns = (
        (r"(?:komprimiere|packe|zip)\s+(.+?)\s+nach\s+(.+)$", "zip"),
        (r"(?:entpacke|unzip|entpack)\s+(.+?)(?:\s+nach\s+(.+))?$", "unzip"),
    )
    for pattern, op in patterns:
        m = re.search(pattern, text, re.I)
        if m:
            src = m.group(1).strip(" .,!?\"'")
            dst = m.group(2).strip(" .,!?\"'") if m.lastindex and m.lastindex >= 2 and m.group(2) else ""
            return op, src, dst
    return "", "", ""


def _extract_toggle_target(text: str) -> tuple[str, str]:
    lower = text.lower()
    pairs = (
        (("wlan aus", "wifi aus", "schalte wlan aus", "deaktiviere wlan"), "wlan", "off"),
        (("wlan an", "wifi an", "schalte wlan ein", "aktiviere wlan"), "wlan", "on"),
        (("bluetooth aus", "deaktiviere bluetooth"), "bluetooth", "off"),
        (("bluetooth an", "aktiviere bluetooth"), "bluetooth", "on"),
        (("flugmodus an", "flugzeugmodus an"), "airplane", "on"),
        (("flugmodus aus", "flugzeugmodus aus"), "airplane", "off"),
        (("hotspot an", "tethering an"), "hotspot", "on"),
        (("hotspot aus", "tethering aus"), "hotspot", "off"),
        (("taschenlampe an", "torch an", "lampe an"), "torch", "on"),
        (("taschenlampe aus", "torch aus", "lampe aus"), "torch", "off"),
        (("mobile daten an", "mobilfunk an", "lte an"), "mobile_data", "on"),
        (("mobile daten aus", "mobilfunk aus", "lte aus"), "mobile_data", "off"),
    )
    for phrases, target, state in pairs:
        if any(p in lower for p in phrases):
            return target, state
    return "", ""


def _extract_tts_text(text: str) -> str:
    patterns = (
        r"(?:lies vor|sprich|sage)\s*:?\s*(.+)$",
        r"(?:text to speech|tts)\s+(.+)$",
    )
    for pattern in patterns:
        m = re.search(pattern, text, re.I)
        if m:
            return m.group(1).strip(" .,!?\"'")
    return ""


def _extract_notification_text(text: str) -> str:
    m = re.search(r"(?:benachrichtige|notify|notification)\s+(?:mich\s+)?(?:mit\s+)?(.+)$", text, re.I)
    return m.group(1).strip(" .,!?\"'") if m else ""


def _extract_git_command(text: str) -> str:
    m = re.search(
        r"(git\s+(?:status|pull|log|diff|commit|push|fetch|restore)\b.*)$",
        text,
        re.I,
    )
    return m.group(1).strip() if m else ""


def _extract_install_command(text: str) -> str:
    patterns = (
        (r"(pip3?\s+install\s+.+)$", ""),
        (r"(apt\s+install\s+.+)$", ""),
        (r"(pkg\s+install\s+.+)$", ""),
        (r"installiere\s+(?:paket\s+)?(.+)$", "installiere"),
    )
    for pattern, kind in patterns:
        m = re.search(pattern, text, re.I)
        if m:
            if kind == "installiere":
                pkg = m.group(1).strip()
                return f"pkg install -y {pkg}" if "pkg" in text.lower() else f"apt install -y {pkg}"
            return m.group(1).strip()
    return ""


def _extract_clipboard_text(text: str) -> tuple[str, str]:
    if re.search(r"(?:lies|lese|zeig).*(?:zwischenablage|clipboard)", text, re.I):
        return "read", ""
    m = re.search(
        r"(?:kopiere|setze|schreib)\s+(?:in\s+)?(?:die\s+)?(?:zwischenablage|clipboard)\s+(.+)$",
        text,
        re.I,
    )
    if m:
        return "write", m.group(1).strip(" .,!?\"'")
    return "", ""


def _device_status_kind(normalized: str) -> str:
    if any(t in normalized for t in ("akku", "batterie")):
        return "battery"
    if any(t in normalized for t in ("speicher", "storage", "festplatte", "disk")):
        if not any(t in normalized for t in ("räum", "raeum", "aufräum", "aufraeum", "bereinige", "cleanup")):
            return "storage"
    if any(t in normalized for t in ("ip", "netzwerkadresse")) and "adresse" not in normalized.replace("ip-adresse", ""):
        return "ip"
    if any(t in normalized for t in ("ip-adresse", "ip adresse", "netzwerkadresse")) or re.search(
        r"\bip\b", normalized
    ):
        return "ip"
    if any(t in normalized for t in ("uhrzeit", "wie spät", "wie spaet", "datum", "welcher tag")):
        return "datetime"
    if any(t in normalized for t in _LOCATION_MARKERS) or "wo bin ich" in normalized:
        return "location"
    if any(t in normalized for t in ("prozesse", "prozess", "cpu", "ram", "arbeitsspeicher", "auslastung")):
        return "processes"
    if re.search(r"was steht .+ kalender", normalized):
        return "calendar_today"
    return "all"


def _extract_credential_request(text: str) -> tuple[str, bool]:
    normalized = _normalize(text)
    if not _contains_any(normalized, _CREDENTIAL_MARKERS):
        return "", False
    if not any(v in normalized for v in ("lies", "lese", "hole", "hol", "zeig", "import", "ausles", "auslese", "read")):
        if not re.search(r"\b(passwort|login|zugangsdaten|credentials?)\b.*\b(für|fuer|von)\b", normalized):
            return "", False
    import_flag = any(t in normalized for t in ("import", "importiere", "speicher", "übernimm", "uebernimm"))
    patterns = (
        r"(?:lies|lese|hole|hol|zeig|importiere|ausles|auslese).*(?:passwort|login|zugangsdaten|credentials?).*(?:für|fuer|von)\s+(.+)$",
        r"(?:passwort|login|zugangsdaten|credentials?).*(?:für|fuer|von)\s+(.+)$",
        r"(?:credentials?|logins?).*(?:für|fuer|von)\s+(.+)$",
    )
    for pattern in patterns:
        m = re.search(pattern, text.strip(), re.I)
        if m:
            site = m.group(1).strip(" .,!?\"'")
            site = re.sub(r"\s+(aus|in|im)\s+(chrome|browser|passwort-manager|passwort manager).*$", "", site, flags=re.I)
            return site, import_flag
    if _contains_any(normalized, ("passwort", "passwoerter", "passwörter", "credentials", "zugangsdaten")) and any(
        v in normalized for v in ("liste", "list", "zeig alle", "inventar")
    ):
        return "__list__", False
    return "", False


def _extract_shell_command(text: str) -> str:
    patterns = (
        r"(?:führe aus|fuehre aus|ausführen|ausfuehren|befehl)\s*:\s*(.+)$",
        r"(?:führe aus|fuehre aus)\s+(.+)$",
        r"^shell\s+(.+)$",
    )
    for pattern in patterns:
        m = re.search(pattern, text.strip(), re.I)
        if m:
            return m.group(1).strip()
    return ""


def detect_owner_action(text: str) -> Optional[OwnerAction]:
    """Imperative Owner-Befehle erkennen (Aufrufer prüft admin-Modus separat)."""
    raw = (text or "").strip()
    if not raw:
        return None

    normalized = _normalize(raw)
    if not normalized or _is_explanatory(normalized):
        return None

    # App launches before security_toolkit — "starte chrome" is not a security tool
    app_launch = _detect_app_launch(raw, normalized)
    if app_launch:
        return app_launch

    # Timer/countdown with duration before security_toolkit (tool_id "timer" would steal it)
    if _contains_any(normalized, _TIMER_MARKERS) or normalized.startswith("timer "):
        if re.search(r"\d+", normalized):
            seconds = _extract_timer_seconds(raw)
            if seconds > 0:
                return OwnerAction("timer", {"seconds": seconds}, raw=raw)

    # Bug bounty (authorized programs only)
    if normalized in {
        "bug bounty",
        "bugbounty",
        "bug bounty status",
        "bug bounty list",
        "bounty status",
        "bounty list",
    } or normalized.startswith("bug bounty list") or normalized.startswith(
        "bug bounty status"
    ):
        return OwnerAction("bug_bounty", {"op": "list"}, raw=raw)
    m_bb = re.match(
        r"^(?:bug\s*bounty|bounty)\s+scan\s+([a-zA-Z0-9._\-]+)\s*$",
        normalized,
    )
    if m_bb:
        return OwnerAction(
            "bug_bounty",
            {"op": "scan", "program_id": m_bb.group(1)},
            raw=raw,
        )

    if is_owner_equivalent_mode():
        from security_toolkit import parse_security_command

        security_cmd = parse_security_command(raw)
        if security_cmd:
            return OwnerAction("security_toolkit", security_cmd, raw=raw)

        cred_site, cred_import = _extract_credential_request(raw)
        if cred_site:
            return OwnerAction(
                "credential_access",
                {"site": "" if cred_site == "__list__" else cred_site, "import": cred_import},
                raw=raw,
            )

    if not _is_owner_imperative(normalized):
        return None

    dry_run = _wants_dry_run(normalized)

    if _contains_any(normalized, _ISAAC_MARKERS):
        if "log" in normalized:
            return OwnerAction("isaac_ops", {"op": "logs"}, raw=raw)
        if any(t in normalized for t in ("neustart", "restart")):
            return OwnerAction("isaac_ops", {"op": "restart"}, raw=raw)
        return OwnerAction("isaac_ops", {"op": "status"}, raw=raw)

    git_cmd = _extract_git_command(raw)
    if git_cmd:
        return OwnerAction("git_command", {"command": git_cmd}, raw=raw)

    install_cmd = _extract_install_command(raw)
    if install_cmd:
        return OwnerAction("package_install", {"command": install_cmd}, raw=raw)

    toggle_target, toggle_state = _extract_toggle_target(raw)
    if toggle_target:
        return OwnerAction("device_toggle", {"target": toggle_target, "state": toggle_state}, raw=raw)

    translate_text, translate_lang = _extract_translate_text(raw)
    if translate_text and _contains_any(normalized, _TRANSLATE_MARKERS + ("übersetze", "uebersetze", "translate")):
        return OwnerAction("translate", {"text": translate_text, "target_lang": translate_lang}, raw=raw)

    if _contains_any(normalized, _WEATHER_MARKERS) and not _is_explanatory(normalized):
        if not re.search(r"\b(als motiv|in der literatur|literarisch|metapher)\b", normalized):
            location = _extract_weather_location(raw)
            return OwnerAction("weather", {"location": location}, raw=raw)

    media_platform, media_query = _extract_media_query(raw)
    if media_platform and media_query:
        return OwnerAction("media_play", {"platform": media_platform, "query": media_query}, raw=raw)

    alarm_time = _extract_alarm_time(raw)
    if alarm_time or normalized.startswith(("wecker ", "alarm ")) or (
        _contains_any(normalized, _ALARM_MARKERS) and normalized.startswith(_OPEN_PREFIXES)
    ):
        return OwnerAction("alarm", {"time": alarm_time}, raw=raw)

    contact_query = _extract_contact_query(raw)
    if contact_query:
        return OwnerAction("contacts", {"query": contact_query}, raw=raw)
    if _contains_any(normalized, _CONTACT_MARKERS) and normalized.startswith(_OPEN_PREFIXES):
        return OwnerAction("contacts", {"query": ""}, raw=raw)

    if _contains_any(normalized, _BLUETOOTH_MARKERS):
        if any(t in normalized for t in ("scan", "scann", "geräte", "geraete")):
            return OwnerAction("bluetooth", {"op": "scan"}, raw=raw)
        if any(t in normalized for t in ("status", "verbunden")):
            return OwnerAction("bluetooth", {"op": "status"}, raw=raw)
        if normalized.startswith(_OPEN_PREFIXES) or "verbind" in normalized:
            return OwnerAction("bluetooth", {"op": "settings"}, raw=raw)

    tts_text = _extract_tts_text(raw)
    if tts_text:
        return OwnerAction("tts", {"text": tts_text}, raw=raw)

    notify_text = _extract_notification_text(raw)
    if notify_text:
        return OwnerAction("notification", {"text": notify_text}, raw=raw)

    if normalized.startswith("ping ") or normalized.startswith("ping6 "):
        host = raw.split(maxsplit=1)[-1].strip() if " " in raw else "8.8.8.8"
        return OwnerAction("network_test", {"kind": "ping", "target": host}, raw=raw)

    if any(t in normalized for t in ("speedtest", "geschwindigkeitstest", "internetgeschwindigkeit")):
        return OwnerAction("network_test", {"kind": "speedtest"}, raw=raw)

    email_search = _extract_email_search_query(raw)
    if email_search:
        return OwnerAction("email_search", {"query": email_search}, raw=raw)

    email_to = _extract_email_recipient(raw)
    if email_to and _contains_any(normalized, _EMAIL_MARKERS + ("mail",)):
        return OwnerAction("email_compose", {"to": email_to}, raw=raw)

    if _contains_any(normalized, _EMAIL_MARKERS) and normalized.startswith(_OPEN_PREFIXES):
        return OwnerAction("email_open", {}, raw=raw)

    if any(t in normalized for t in ("lade herunter", "downloade", "download")) and _extract_download_url(raw):
        return OwnerAction(
            "download_url",
            {"url": _extract_download_url(raw), "path": _extract_path_hint(raw) or str(WORKSPACE)},
            raw=raw,
        )

    write_path, write_content = _extract_file_write(raw)
    if write_path and write_content:
        return OwnerAction("file_write", {"path": write_path, "content": write_content}, raw=raw)

    if re.search(r"(?:erstelle|erzeuge|mkdir)\s+(?:ordner|verzeichnis|folder)\s+", normalized):
        m = re.search(r"(?:erstelle|erzeuge|mkdir)\s+(?:ordner|verzeichnis|folder)\s+(.+)$", raw, re.I)
        if m:
            return OwnerAction("mkdir", {"path": m.group(1).strip(" .,!?\"'")}, raw=raw)

    find_name, find_root = _extract_find_file(raw)
    if find_name:
        return OwnerAction("find_files", {"name": find_name, "root": find_root}, raw=raw)

    arch_op, arch_src, arch_dst = _extract_archive_paths(raw)
    if arch_op:
        return OwnerAction("archive", {"operation": arch_op, "source": arch_src, "destination": arch_dst}, raw=raw)

    if re.search(r"(?:öffne|oeffne)\s+ordner\s+", normalized):
        m = re.search(r"(?:öffne|oeffne)\s+ordner\s+(.+)$", raw, re.I)
        if m:
            return OwnerAction("open_folder", {"path": m.group(1).strip(" .,!?\"'")}, raw=raw)

    if _contains_any(normalized, _SHOPPING_MARKERS) and normalized.startswith(("suche ", "such ", "finde ")):
        m = re.search(r"(?:suche|such|finde)\s+(?:auf\s+)?(?:amazon|ebay|kleinanzeigen)\s+(?:nach\s+)?(.+)$", raw, re.I)
        if m:
            platform = next((p for p in ("amazon", "ebay", "kleinanzeigen") if p in normalized), "amazon")
            return OwnerAction("shopping_search", {"platform": platform, "query": m.group(1).strip(" .,!?")}, raw=raw)

    if re.search(r"(?:erstelle|erzeuge)\s+(?:termin|erinnerung|reminder)\s+", normalized):
        m = re.search(r"(?:erstelle|erzeuge)\s+(?:termin|erinnerung|reminder)\s+(.+)$", raw, re.I)
        if m:
            return OwnerAction("calendar_create", {"title": m.group(1).strip(" .,!?")}, raw=raw)

    maps_dest = _extract_maps_destination(raw)
    if maps_dest:
        return OwnerAction("maps_navigate", {"destination": maps_dest}, raw=raw)

    if _contains_any(normalized, _CALENDAR_MARKERS):
        if re.search(r"was steht|heute|morgen|diese woche", normalized):
            view = "today"
            if "morgen" in normalized:
                view = "tomorrow"
            elif "woche" in normalized:
                view = "week"
            return OwnerAction("calendar_open", {"view": view}, raw=raw)
        if normalized.startswith(_OPEN_PREFIXES) or "zeig" in normalized or "zeige" in normalized:
            return OwnerAction("calendar_open", {"view": "open"}, raw=raw)

    clipboard_op, clipboard_text = _extract_clipboard_text(raw)
    if clipboard_op:
        return OwnerAction("clipboard", {"operation": clipboard_op, "text": clipboard_text}, raw=raw)

    if any(t in normalized for t in ("screenshot", "bildschirmfoto", "bildschirm foto")):
        return OwnerAction("screenshot", {}, raw=raw)

    if any(t in normalized for t in ("fotografiere", "selfie")) or (
        any(t in normalized for t in ("foto", "kamera"))
        and any(t in normalized for t in ("mach", "nimm", "öffne", "oeffne", "starte"))
    ):
        return OwnerAction("camera", {}, raw=raw)

    if normalized.startswith(("rufe ", "telefoniere ", "call ")):
        number = _extract_phone_number(raw)
        if number:
            return OwnerAction("phone_call", {"number": number}, raw=raw)

    if re.search(r"(?:schick|sende|schreib)\s+(?:eine\s+)?sms", normalized):
        number = _extract_phone_number(raw)
        if number:
            return OwnerAction(
                "sms_send",
                {"number": number, "body": _extract_sms_body(raw)},
                raw=raw,
            )

    file_op, file_src, file_dst = _extract_file_paths(raw)
    if file_op:
        return OwnerAction(
            "file_operation",
            {"operation": file_op, "source": file_src, "destination": file_dst},
            raw=raw,
        )

    status_kind = _device_status_kind(normalized)
    if status_kind and status_kind != "all":
        return OwnerAction("device_status", {"kind": status_kind}, raw=raw)

    if _contains_any(normalized, _PHOTOS_MARKERS) or re.search(r"\bfotos\b", normalized):
        query = _extract_photos_query(raw)
        if query:
            return OwnerAction("photos_search", {"query": query}, raw=raw)
        if normalized.startswith(_OPEN_PREFIXES):
            return OwnerAction("open_target", {"target": "google fotos"}, raw=raw)

    if _contains_any(normalized, _WLAN_MARKERS):
        ssid = _extract_ssid(raw)
        if any(t in normalized for t in ("status", "signal", "verbunden")):
            return OwnerAction("wlan_status", {}, raw=raw)
        if any(t in normalized for t in ("scan", "scann", "netzwerke")):
            return OwnerAction("wlan_scan", {}, raw=raw)
        if any(t in normalized for t in ("verbind", "connect", "join", "anmelden", "einlogg")):
            return OwnerAction("wlan_connect", {"ssid": ssid, "dry_run": dry_run}, raw=raw)
        if any(t in normalized for t in ("einstellung", "settings")):
            return OwnerAction("wlan_open_settings", {}, raw=raw)

    if _contains_any(normalized, _ROUTER_MARKERS):
        if any(t in normalized for t in ("öffne", "oeffne", "einlogg", "admin", "interface", "oberfläche", "oberflaeche")):
            return OwnerAction("router_admin", {}, raw=raw)
        if any(t in normalized for t in ("verbind", "connect")):
            return OwnerAction("wlan_connect", {"ssid": _extract_ssid(raw), "dry_run": dry_run}, raw=raw)

    if _contains_any(normalized, _WLAN_MARKERS):
        return OwnerAction("wlan_status", {}, raw=raw)

    cleanup_verb = any(t in normalized for t in ("räum", "raeum", "aufräum", "aufraeum", "bereinige", "cleanup"))
    path_hint = _extract_path_hint(raw)
    if cleanup_verb and (_contains_any(normalized, _CLEANUP_MARKERS) or path_hint):
        params: dict[str, Any] = {
            "scope": "deep" if _wants_deep_clean(normalized) else "standard",
            "dry_run": dry_run,
        }
        if path_hint:
            params["root"] = path_hint
        return OwnerAction("filesystem_cleanup", params, raw=raw)

    if any(t in normalized for t in ("liste", "zeig", "zeige")) and any(
        t in normalized for t in ("datei", "ordner", "verzeichnis", "pfad", "inhalt")
    ):
        path_hint = _extract_path_hint(raw) or "~"
        return OwnerAction("file_list", {"path": path_hint}, raw=raw)

    for alias in sorted(_SITE_ALIASES, key=len, reverse=True):
        if alias in normalized and normalized.startswith(_OPEN_PREFIXES):
            # Web/site open by default; native package only with explicit "app"
            force_app = bool(re.search(r"\bapp\b", normalized))
            if force_app and (
                alias in _APP_PACKAGES
                or any(pkg_name in alias or alias in pkg_name for pkg_name in _APP_PACKAGES)
            ):
                for pkg_name in sorted(_APP_PACKAGES, key=len, reverse=True):
                    if pkg_name in alias or alias in pkg_name:
                        return OwnerAction(
                            "app_open",
                            {"name": pkg_name, "url": _SITE_ALIASES.get(alias, "")},
                            raw=raw,
                        )
            return OwnerAction("open_target", {"target": alias}, raw=raw)

    if re.match(r"^(starte|öffne|oeffne)(\s+die)?\s+app\s+", normalized):
        app = re.sub(r"^(starte|öffne|oeffne)(\s+die)?\s+app\s+", "", raw, flags=re.I).strip()
        if app:
            return OwnerAction("app_open", {"name": app}, raw=raw)

    if _contains_any(normalized, tuple(_ANDROID_INTENTS)) and normalized.startswith(_OPEN_PREFIXES):
        name = normalized.split(maxsplit=1)[-1] if " " in normalized else normalized
        for key in sorted(_ANDROID_INTENTS, key=len, reverse=True):
            if key in normalized:
                return OwnerAction("app_open", {"name": key}, raw=raw)

    shell_cmd = _extract_shell_command(raw)
    if shell_cmd:
        return OwnerAction("shell", {"command": shell_cmd}, raw=raw)

    if _contains_any(normalized, _WEB_SEARCH_MARKERS) or normalized.startswith(("suche ", "such ", "finde ")):
        query = _extract_web_query(raw)
        if query:
            return OwnerAction("web_search", {"query": query, "open_browser": True}, raw=raw)

    if normalized.startswith(_OPEN_PREFIXES):
        target = re.sub(r"^(öffne|oeffne|navigiere|starte)\s+(zu\s+)?", "", raw, flags=re.I).strip()
        if target:
            # "öffne youtube.com in chrome" → chrome package + URL
            m_in = re.search(
                r"^(.+?)\s+(?:in|im|mit)\s+(chrome|browser|firefox)\s*$",
                target,
                re.I,
            )
            if m_in:
                dest, browser = m_in.group(1).strip(), m_in.group(2).strip().lower()
                browser = "chrome" if browser == "browser" else browser
                return OwnerAction(
                    "app_open",
                    {"name": browser, "url": _resolve_open_url(dest)},
                    raw=raw,
                )
            # bare app name
            t_norm = _normalize(target)
            for pkg_name in sorted(_APP_PACKAGES, key=len, reverse=True):
                if t_norm == pkg_name or t_norm.startswith(pkg_name + " "):
                    return OwnerAction("app_open", {"name": pkg_name}, raw=raw)
            return OwnerAction("open_target", {"target": target}, raw=raw)

    return None


def _detect_app_launch(raw: str, normalized: str) -> Optional[OwnerAction]:
    """Early detect 'öffne/starte chrome' before security_toolkit steals it."""
    if not normalized:
        return None
    # chrome tabs list / open tab N
    if normalized in {
        "chrome tabs",
        "chrome tab",
        "tabs",
        "zeig tabs",
        "zeige tabs",
        "list tabs",
        "chrome tabs full",
        "tabs full",
    } or normalized.startswith("chrome tabs"):
        full = "full" in normalized or "alle" in normalized
        return OwnerAction("chrome_tabs", {"full": full}, raw=raw)
    m_tab = re.match(
        r"^(?:öffne|oeffne|open)\s+tab\s+(\d+)\s*$",
        normalized,
    )
    if m_tab:
        return OwnerAction("chrome_tab_open", {"index": int(m_tab.group(1))}, raw=raw)

    # chrome secrets / cookies / autofill / accounts / passwords
    if normalized in {
        "chrome secrets",
        "chrome secret",
        "secrets chrome",
        "chrome cookies",
        "chrome autofill",
        "chrome accounts",
        "chrome karten",
        "chrome cards",
        "chrome passwords",
        "chrome passwörter",
        "chrome passwoerter",
        "chrome decrypt",
        "chrome live",
        "decrypt chrome",
        "entschlüssele cookies",
        "entschluessle cookies",
    } or normalized.startswith("chrome secrets") or normalized.startswith(
        "chrome cookies"
    ) or normalized.startswith("chrome autofill") or normalized.startswith(
        "chrome decrypt"
    ) or normalized.startswith("chrome live"):
        # cookie jar export
        if any(
            x in normalized
            for x in (
                "cookie jar",
                "cookiejar",
                "cookies export",
                "export cookies",
                "export cookie",
                "netscape",
            )
        ):
            return OwnerAction("cookie_jar_export", {"refresh": True}, raw=raw)
        # live memory decrypt path
        if any(
            x in normalized
            for x in ("decrypt", "live", "entschlüssel", "entschluessel", "klartext")
        ):
            name_filter = ""
            m_nf = re.search(r"(?:name|filter|für|fuer|von)\s+([\w.\-]+)", normalized)
            if m_nf:
                name_filter = m_nf.group(1)
            do_jar = any(
                x in normalized for x in ("jar", "export", "netscape", "cookie jar")
            )
            return OwnerAction(
                "chrome_decrypt",
                {
                    "reveal": "mask" not in normalized and "redact" not in normalized,
                    "name_filter": name_filter,
                    "export_jar": do_jar or True,  # always export jar with decrypt
                },
                raw=raw,
            )
        section = "all"
        if "cookie" in normalized:
            section = "cookies"
        elif "autofill" in normalized or "formular" in normalized:
            section = "autofill"
        elif "account" in normalized or "konten" in normalized:
            section = "accounts"
        elif "passwort" in normalized or "password" in normalized:
            section = "passwords"
        elif "karte" in normalized or "card" in normalized or "payment" in normalized:
            section = "payments"
        dump = "dump" in normalized or "export" in normalized
        host = ""
        m_host = re.search(r"(?:host|domain|für|fuer|von)\s+([\w.-]+)", normalized)
        if m_host:
            host = m_host.group(1)
        return OwnerAction(
            "chrome_secrets",
            {"section": section, "dump": dump, "host": host},
            raw=raw,
        )

    # UI password fields
    if normalized in {
        "ui passwords",
        "ui passwort",
        "ui passwörter",
        "ui passwoerter",
        "passwortfelder",
        "password fields",
        "lies passwortfelder",
        "zeig passwortfelder",
        "chrome ui passwords",
    } or normalized.startswith("ui passwords") or normalized.startswith("passwortfelder"):
        return OwnerAction(
            "ui_passwords",
            {"reveal": "mask" not in normalized, "try_show": "no show" not in normalized},
            raw=raw,
        )

    # cookie jar (also outside chrome- prefix)
    if normalized in {
        "cookie jar",
        "cookie jar export",
        "export cookie jar",
        "export cookies",
        "cookies export",
    } or normalized.startswith("cookie jar"):
        return OwnerAction("cookie_jar_export", {"refresh": True}, raw=raw)

    # apps list / search / activity / ui
    if normalized in {
        "apps status",
        "app status",
        "termux bridge",
        "termux bridge status",
        "bridge status",
        "android apps",
    } or normalized.startswith("apps status"):
        return OwnerAction("apps_status", {}, raw=raw)
    if normalized in {"apps list", "app list", "liste apps", "appliste"} or normalized.startswith(
        "apps list"
    ) or normalized.startswith("app list") or normalized.startswith("suche app"):
        q = ""
        m_q = re.match(
            r"^(?:apps?\s+list|liste\s+apps|suche\s+app|apps?)\s+(.+)$",
            normalized,
        )
        if m_q:
            q = m_q.group(1).strip()
        third = "user" in normalized or "third" in normalized or "installiert" in normalized
        return OwnerAction("apps_list", {"query": q, "third_party": third}, raw=raw)
    if normalized in {"activity", "aktuelle app", "current app", "foreground app"}:
        return OwnerAction("android_activity", {}, raw=raw)
    if normalized in {"ui dump", "ui baum", "ui list", "screen ui", "ui"}:
        return OwnerAction("android_ui_dump", {}, raw=raw)
    m_tip = re.match(
        r"^(?:tippe|tap|klicke|click)\s+(?:auf\s+)?(.+)$",
        normalized,
    )
    if m_tip:
        body = m_tip.group(1).strip()
        m_xy = re.match(r"^(?:xy\s+)?(\d+)\s+(\d+)$", body)
        if m_xy:
            return OwnerAction(
                "android_input",
                {"op": "tap_xy", "x": int(m_xy.group(1)), "y": int(m_xy.group(2))},
                raw=raw,
            )
        return OwnerAction("android_input", {"op": "tap_label", "label": body}, raw=raw)
    m_text = re.match(
        r"^(?:text|tippe text|type|schreibe|eingabe)\s+(.+)$",
        normalized,
    )
    if m_text:
        return OwnerAction(
            "android_input",
            {"op": "text", "text": m_text.group(1).strip()},
            raw=raw,
        )
    m_key = re.match(r"^(?:key|taste|keyevent)\s+(\w+)$", normalized)
    if m_key:
        return OwnerAction(
            "android_input",
            {"op": "key", "key": m_key.group(1)},
            raw=raw,
        )
    if normalized in {"back", "zurück", "zurueck", "home taste", "home key"}:
        key = "home" if "home" in normalized else "back"
        return OwnerAction("android_input", {"op": "key", "key": key}, raw=raw)
    m_stop = re.match(
        r"^(?:stop|stoppe|beende|force.?stop)\s+(?:app\s+)?(.+)$",
        normalized,
    )
    if m_stop:
        return OwnerAction("app_stop", {"name": m_stop.group(1).strip()}, raw=raw)

    if not normalized.startswith(_OPEN_PREFIXES) and not re.match(
        r"^(starte|öffne|oeffne)(\s+die)?\s+app\s+", normalized
    ):
        # also "chrome öffnen"
        m_rev = re.match(
            r"^(.+?)\s+(öffnen|oeffnen|starten)\s*$",
            normalized,
        )
        if m_rev:
            candidate = m_rev.group(1).strip()
            # Site alias reverse form: "youtube starten"
            for alias in sorted(_SITE_ALIASES, key=len, reverse=True):
                if candidate == alias:
                    return OwnerAction("open_target", {"target": alias}, raw=raw)
            for pkg_name in sorted(_APP_PACKAGES, key=len, reverse=True):
                if candidate == pkg_name or candidate.endswith(" " + pkg_name):
                    return OwnerAction("app_open", {"name": pkg_name}, raw=raw)
            for intent_name in sorted(_ANDROID_INTENTS, key=len, reverse=True):
                if candidate == intent_name:
                    return OwnerAction("app_open", {"name": intent_name}, raw=raw)
            # single-token unknown only
            if candidate and " " not in candidate and len(candidate) >= 2:
                return OwnerAction("app_open", {"name": candidate}, raw=raw)
        return None

    # strip open prefixes
    rest = re.sub(
        r"^(starte|öffne|oeffne)(\s+die)?\s+(app\s+)?",
        "",
        normalized,
        flags=re.I,
    ).strip()
    rest = re.sub(r"^(zu\s+)", "", rest).strip()
    if not rest:
        return None

    # Defer specialized Owner handlers (timer/router/wlan/…) — do not steal as app_open
    if _contains_any(rest, _TIMER_MARKERS) and re.search(r"\d+", rest):
        return None
    if _contains_any(rest, _ALARM_MARKERS) and re.search(r"\d+", rest):
        return None
    if _contains_any(normalized, _ROUTER_MARKERS):
        return None
    if _contains_any(rest, _WLAN_MARKERS) and any(
        t in rest for t in ("verbind", "status", "scan", "einstellung", "settings")
    ):
        return None

    # URL in chrome
    m_in = re.search(
        r"^(.+?)\s+(?:in|im|mit)\s+(chrome|browser|firefox)\s*$",
        rest,
        re.I,
    )
    if m_in:
        dest, browser = m_in.group(1).strip(), m_in.group(2).strip().lower()
        browser = "chrome" if browser == "browser" else browser
        url = _resolve_open_url(dest)
        return OwnerAction("app_open", {"name": browser, "url": url}, raw=raw)

    force_app = bool(
        re.search(r"\bapp\b", normalized)
        or re.match(r"^(starte|öffne|oeffne)(\s+die)?\s+app\s+", normalized)
    )

    # Site aliases (youtube, github, …) → open_target unless user said "app"
    for alias in sorted(_SITE_ALIASES, key=len, reverse=True):
        if rest == alias or rest.startswith(alias + " "):
            if force_app and (
                alias in _APP_PACKAGES
                or any(alias == k or alias.startswith(k) for k in _APP_PACKAGES)
            ):
                for pkg_name in sorted(_APP_PACKAGES, key=len, reverse=True):
                    if pkg_name == alias or alias.startswith(pkg_name):
                        return OwnerAction(
                            "app_open",
                            {"name": pkg_name, "url": _SITE_ALIASES.get(alias, "")},
                            raw=raw,
                        )
            return OwnerAction("open_target", {"target": alias}, raw=raw)

    for pkg_name in sorted(_APP_PACKAGES, key=len, reverse=True):
        if rest == pkg_name or rest.startswith(pkg_name + " "):
            return OwnerAction("app_open", {"name": pkg_name}, raw=raw)
    for intent_name in sorted(_ANDROID_INTENTS, key=len, reverse=True):
        if rest == intent_name or rest.startswith(intent_name + " "):
            return OwnerAction("app_open", {"name": intent_name}, raw=raw)
    # Unknown free-form "öffne X" → leave to main detector (open_target / search / …)
    # Only force app_open when user said "app" or a short bare name (no multi-word domain tasks)
    if force_app and rest:
        return OwnerAction("app_open", {"name": rest}, raw=raw)
    if rest and " " not in rest and len(rest) >= 2 and not rest.startswith("http"):
        # bare token e.g. "chrome" already handled; single unknown token → app search
        return OwnerAction("app_open", {"name": rest}, raw=raw)
    return None


def _resolve_open_url(dest: str) -> str:
    """Map 'google' / site aliases / bare domains to a concrete https URL."""
    dest = (dest or "").strip()
    if not dest:
        return "https://www.google.de/"
    lower = _normalize(dest)
    # known sites first (gmail, google, maps, …)
    for alias, url in sorted(_SITE_ALIASES.items(), key=lambda x: -len(x[0])):
        if lower == alias or lower == alias.replace(" ", ""):
            return url
    # bare brand → homepage (not search)
    brand_homes = {
        "google": "https://www.google.de/",
        "google.de": "https://www.google.de/",
        "google.com": "https://www.google.com/",
        "youtube": "https://www.youtube.com/",
        "gmail": "https://mail.google.com/",
        "maps": "https://maps.google.com/",
    }
    if lower in brand_homes:
        return brand_homes[lower]
    if re.match(r"^https?://", dest, re.I):
        return dest
    if re.match(r"^[\w.-]+\.[a-z]{2,}", dest, re.I) and " " not in dest:
        return f"https://{dest}"
    return f"https://www.google.com/search?q={quote_plus(dest)}"


async def execute_owner_action(action: OwnerAction) -> tuple[str, bool]:
    handlers: dict[str, Callable] = {
        "photos_search": _photos_search,
        "web_search": _web_search,
        "wlan_status": _wlan_status,
        "wlan_scan": _wlan_scan,
        "wlan_open_settings": _wlan_open_settings,
        "wlan_connect": _wlan_connect,
        "router_admin": _router_admin,
        "filesystem_cleanup": _filesystem_cleanup,
        "file_list": _file_list,
        "file_operation": _file_operation,
        "app_open": _app_open,
        "apps_status": _apps_status,
        "chrome_tabs": _chrome_tabs,
        "chrome_tab_open": _chrome_tab_open,
        "chrome_secrets": _chrome_secrets,
        "chrome_decrypt": _chrome_decrypt,
        "cookie_jar_export": _cookie_jar_export,
        "ui_passwords": _ui_passwords,
        "apps_list": _apps_list,
        "app_stop": _app_stop,
        "android_activity": _android_activity,
        "android_ui_dump": _android_ui_dump,
        "android_input": _android_input,
        "shell": _shell_action,
        "open_target": _open_target,
        "email_open": _email_open,
        "email_compose": _email_compose,
        "email_search": _email_search,
        "calendar_open": _calendar_open,
        "maps_navigate": _maps_navigate,
        "device_status": _device_status,
        "screenshot": _screenshot,
        "camera": _camera,
        "phone_call": _phone_call,
        "sms_send": _sms_send,
        "clipboard": _clipboard,
        "translate": _translate,
        "weather": _weather,
        "media_play": _media_play,
        "timer": _timer,
        "alarm": _alarm,
        "contacts": _contacts,
        "bluetooth": _bluetooth,
        "tts": _tts,
        "notification": _notification_send,
        "network_test": _network_test,
        "download_url": _download_url,
        "file_write": _file_write,
        "mkdir": _mkdir,
        "find_files": _find_files,
        "archive": _archive,
        "open_folder": _open_folder,
        "shopping_search": _shopping_search,
        "calendar_create": _calendar_create,
        "device_toggle": _device_toggle,
        "git_command": _git_command,
        "package_install": _package_install,
        "security_toolkit": _security_toolkit,
        "bug_bounty": _bug_bounty,
        "credential_access": _credential_access,
        "isaac_ops": _isaac_ops,
    }
    handler = handlers.get(action.kind)
    if not handler:
        return f"[Owner] Unbekannte Aktion: {action.kind}", False
    try:
        return await handler(action)
    except Exception as exc:
        log.warning("Owner action %s failed: %s", action.kind, exc)
        return f"[Owner] Fehler bei {action.kind}: {exc}", False


async def _runtime():
    from computer_use import ComputerUseRuntime
    return ComputerUseRuntime()


async def _shell(command: str, timeout: float = 45.0) -> dict[str, Any]:
    from computer_use import AgentAction
    runtime = await _runtime()
    return await runtime.execute(AgentAction("shell", {"command": command}))


async def _shell_json(command: str) -> Any:
    result = await _shell(command)
    if not result.get("ok") and not result.get("stdout"):
        return None
    raw = (result.get("stdout") or "").strip()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def _resolve_cleanup_root(root_hint: str) -> Optional[Path]:
    hint = (root_hint or "").strip()
    if not hint:
        return None
    if hint.startswith("~"):
        return (Path.home() / hint[2:].lstrip("/\\")).resolve()
    path = Path(hint).expanduser()
    if not path.is_absolute():
        path = Path.home() / path
    return path.resolve()


def _cleanup_roots(scope: str, root_hint: str = "") -> list[Path]:
    scoped = _resolve_cleanup_root(root_hint)
    if scoped and scoped.exists():
        return [scoped]
    roots = [Path.home(), WORKSPACE.resolve(), BASE_DIR.resolve()]
    if scope == "deep":
        termux_storage = Path.home() / "storage"
        if termux_storage.exists():
            for sub in ("downloads", "dcim", "shared"):
                p = termux_storage / sub
                if p.exists():
                    roots.append(p.resolve())
    unique: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        key = str(root)
        if key not in seen and root.exists():
            seen.add(key)
            unique.append(root)
    return unique


def _is_protected(path: Path) -> bool:
    parts = set(path.parts)
    if parts & _CLEANUP_PROTECTED_NAMES:
        return True
    if path.name.startswith(".env"):
        return True
    if DATA_DIR in path.parents or path == DATA_DIR:
        if path.name in {"isaac.db", "audit.jsonl", "constitution.json", "runtime_settings.json"}:
            return True
    return False


def _dir_size(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_size
    total = 0
    try:
        for child in path.rglob("*"):
            if child.is_file():
                total += child.stat().st_size
    except Exception:
        pass
    return total


def _scan_cleanup_targets(scope: str, root_hint: str = "") -> list[tuple[Path, str]]:
    targets: list[tuple[Path, str]] = []
    file_patterns = ("**/*.pyc", "**/*.pyo", "**/*.tmp", "**/*~", "**/.DS_Store", "**/*.crdownload", "**/*.part")
    dir_patterns = ("**/__pycache__",)

    for root in _cleanup_roots(scope, root_hint):
        depth = len(root.parts)
        for pattern in dir_patterns:
            for path in root.glob(pattern):
                if _is_protected(path) or len(path.parts) - depth > _CLEANUP_MAX_DEPTH:
                    continue
                targets.append((path, "cache_dir"))
        for pattern in file_patterns:
            for path in root.glob(pattern):
                if _is_protected(path) or len(path.parts) - depth > _CLEANUP_MAX_DEPTH:
                    continue
                targets.append((path, "temp_file"))
        if scope == "deep":
            for path in root.glob("**/.cache"):
                if path.is_dir() and not _is_protected(path) and len(path.parts) - depth <= _CLEANUP_MAX_DEPTH:
                    targets.append((path, "cache_dir"))
            if LOG_DIR.exists() and (root == BASE_DIR.resolve() or root == Path.home()):
                cutoff = time.time() - 14 * 86400
                for path in LOG_DIR.glob("*.log"):
                    try:
                        if path.stat().st_mtime < cutoff:
                            targets.append((path, "old_log"))
                    except OSError:
                        pass

    deduped: list[tuple[Path, str]] = []
    seen: set[str] = set()
    for path, kind in sorted(targets, key=lambda x: len(str(x[0])), reverse=True):
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        deduped.append((path, kind))
    return deduped


def _remove_empty_dirs(roots: list[Path], stats: CleanupStats, dry_run: bool) -> None:
    for root in roots:
        if not root.exists() or not root.is_dir():
            continue
        for path in sorted(root.rglob("*"), key=lambda p: len(p.parts), reverse=True):
            if not path.is_dir() or _is_protected(path):
                continue
            try:
                if any(path.iterdir()):
                    continue
            except OSError:
                continue
            if dry_run:
                stats.removed_dirs.append(f"[dry] {path}")
                continue
            try:
                path.rmdir()
                stats.removed_dirs.append(str(path))
            except OSError as exc:
                stats.skipped.append(f"{path}: {exc}")


async def _photos_search(action: OwnerAction) -> tuple[str, bool]:
    query = str(action.params.get("query") or "").strip()
    if not query:
        return "[Owner] Kein Suchbegriff für Google Fotos erkannt.", False
    url = f"https://photos.google.com/search/{quote_plus(query)}"
    AuditLog.action("OwnerAction", "photos_search", f"query={query[:120]}")

    browser_note = await _browser_navigate(url, wait_ms=2500)
    opened = await _open_url(url)
    return (
        f"[Owner] Google Fotos-Suche ausgeführt.\n"
        f"Suchbegriff: {query}\n"
        f"URL: {url}\n"
        f"{browser_note}\n"
        f"{opened}\n"
        f"Hinweis: In Google Fotos eingeloggt sein — sonst Login-Seite."
    ), True


async def _web_search(action: OwnerAction) -> tuple[str, bool]:
    query = str(action.params.get("query") or "").strip()
    if not query:
        return "[Owner] Kein Suchbegriff erkannt.", False
    AuditLog.action("OwnerAction", "web_search", f"query={query[:120]}")
    lines = [f"[Owner] Websuche: {query}", ""]

    try:
        from search import get_search

        result = await get_search().search(query, max_hits=8)
        if result:
            if result.abstract:
                lines.append(f"Kurzantwort: {result.abstract[:500]}")
                lines.append("")
            if result.hits:
                for i, hit in enumerate(result.hits[:8], 1):
                    lines.append(f"{i}. {hit.titel}")
                    if hit.snippet:
                        lines.append(f"   {hit.snippet[:220]}")
                    lines.append(f"   {hit.url}")
                if action.params.get("open_browser") and result.hits:
                    top_url = result.hits[0].url
                    note = await _open_url(top_url)
                    lines.extend(["", f"Top-Treffer geöffnet: {top_url}", note])
                return "\n".join(lines), True
    except Exception as exc:
        log.debug("Search engine failed: %s", exc)
        lines.append(f"(Such-API: {exc})")

    url = f"https://www.google.com/search?q={quote_plus(query)}"
    opened = await _open_url(url)
    lines.extend(["", f"Fallback: Google-Suche geöffnet.", f"URL: {url}", opened])
    return "\n".join(lines), True


async def _wlan_status(action: OwnerAction) -> tuple[str, bool]:
    AuditLog.action("OwnerAction", "wlan_status", action.raw[:120])
    runtime = await _runtime()
    lines = ["[Owner] WLAN-Status", ""]

    if runtime.runtime == "termux":
        for cmd in ("termux-wifi-connectioninfo", "termux-wifi-signal", "ip route"):
            result = await _shell(cmd)
            label = cmd.split()[0] if " " not in cmd else cmd
            if result.get("stdout"):
                lines.append(f"--- {label} ---")
                lines.append(result["stdout"][:2500])
            elif result.get("error"):
                lines.append(f"--- {label} --- ({result['error']})")
    elif runtime.runtime == "s8":
        for cmd in (
            "iwgetid -r 2>/dev/null",
            "iw dev wlan0 link 2>/dev/null",
            "ip -4 addr show wlan0",
            "ip -4 route show default",
        ):
            result = await _shell(cmd)
            if result.get("stdout"):
                lines.append(result["stdout"][:2500])
    else:
        for cmd in (
            "nmcli -t -f ACTIVE,SSID,SIGNAL,SECURITY dev wifi",
            "ip -4 route show default",
            "iwconfig 2>/dev/null | head -30",
        ):
            result = await _shell(cmd)
            if result.get("stdout"):
                lines.append(result["stdout"][:2500])
    gateway = await _default_gateway()
    if gateway:
        lines.extend(["", f"Gateway/Router: {gateway}", f"Router-UI: http://{gateway}"])
    return "\n".join(lines), True


async def _wlan_scan(action: OwnerAction) -> tuple[str, bool]:
    AuditLog.action("OwnerAction", "wlan_scan", action.raw[:120])
    runtime = await _runtime()
    lines = ["[Owner] WLAN-Scan", ""]

    if runtime.runtime == "termux":
        data = await _shell_json("termux-wifi-scanlist")
        if isinstance(data, list):
            for net in data[:25]:
                if isinstance(net, dict):
                    lines.append(
                        f"- {net.get('SSID', '?')} │ Signal: {net.get('level', '?')} │ "
                        f"Sicherheit: {net.get('capabilities', '?')}"
                    )
            return "\n".join(lines), True
        result = await _shell("termux-wifi-scanlist")
        return f"[Owner] Scan:\n{result.get('stdout', result.get('error', 'kein Ergebnis'))}", bool(result.get("ok"))
    result = await _shell("nmcli -t -f SSID,SIGNAL,SECURITY dev wifi list 2>/dev/null | head -30")
    lines.append(result.get("stdout") or result.get("error", "nmcli nicht verfügbar"))
    return "\n".join(lines), bool(result.get("stdout"))


async def _wlan_open_settings(action: OwnerAction) -> tuple[str, bool]:
    AuditLog.action("OwnerAction", "wlan_open_settings", action.raw[:120])
    runtime = await _runtime()
    cmd = (
        "am start -a android.settings.WIFI_SETTINGS"
        if runtime.runtime == "termux"
        else "nm-connection-editor >/dev/null 2>&1 & disown || nmtui"
    )
    result = await _shell(cmd)
    if result.get("ok"):
        return "[Owner] WLAN-Einstellungen geöffnet.", True
    return f"[Owner] WLAN-Einstellungen fehlgeschlagen: {result.get('error', 'unbekannt')}", False


async def _wlan_connect(action: OwnerAction) -> tuple[str, bool]:
    ssid = str(action.params.get("ssid") or "").strip()
    if not ssid:
        ssid = (os.environ.get("ISAAC_WIFI_SSID") or "").strip()
    wifi_password = (os.environ.get("ISAAC_WIFI_PASSWORD") or "").strip()
    dry_run = bool(action.params.get("dry_run"))
    AuditLog.action("OwnerAction", "wlan_connect", f"ssid={ssid[:40]} dry_run={dry_run}")

    lines = ["[Owner] WLAN-Verbindung", ""]
    runtime = await _runtime()
    current_ssid = await _current_wifi_ssid()

    if ssid and current_ssid and current_ssid.lower() == ssid.lower():
        lines.append(f"Bereits verbunden mit: {current_ssid}")
        gateway = await _default_gateway()
        if gateway:
            lines.append(f"Gateway: {gateway}")
        return "\n".join(lines), True

    if runtime.runtime == "termux":
        scan = await _shell_json("termux-wifi-scanlist")
        if ssid and isinstance(scan, list):
            match = next(
                (n for n in scan if isinstance(n, dict) and str(n.get("SSID", "")).lower() == ssid.lower()),
                None,
            )
            if match:
                lines.append(f"Netzwerk gefunden: {match.get('SSID')} (Signal {match.get('level')})")
            else:
                lines.append(f"SSID '{ssid}' im Scan nicht gefunden — trotzdem Einstellungen öffnen.")
        elif not ssid:
            lines.append("Keine SSID erkannt. Verfügbare Netze:")
            if isinstance(scan, list):
                for net in scan[:12]:
                    if isinstance(net, dict):
                        lines.append(f"  - {net.get('SSID')}")

        if dry_run:
            lines.append("(Dry-Run: WLAN-Einstellungen würden geöffnet.)")
            return "\n".join(lines), True

        await _shell("termux-wifi-enable true")
        opened = await _wlan_open_settings(action)
        lines.append(opened[0])
        lines.append(
            "Android erlaubt automatisches Join oft nur für gespeicherte Netze.\n"
            "Bitte Netzwerk in den Einstellungen auswählen"
            + (f" ('{ssid}')." if ssid else ".")
        )
        return "\n".join(lines), opened[1]

    if ssid:
        if wifi_password:
            cmd = (
                f"nmcli dev wifi connect {shlex_quote(ssid)} password {shlex_quote(wifi_password)} 2>&1"
            )
        else:
            cmd = f"nmcli dev wifi connect {shlex_quote(ssid)} 2>&1"
        result = await _shell(cmd)
        if result.get("ok"):
            lines.append(f"Verbunden mit {ssid}.")
            return "\n".join(lines), True
        lines.append(result.get("stdout") or result.get("error", "Verbindung fehlgeschlagen"))
        if not wifi_password:
            lines.append("Tipp: Gespeichertes Netzwerk via ISAAC_WIFI_SSID / ISAAC_WIFI_PASSWORD in .env.")
        return "\n".join(lines), False

    opened = await _wlan_open_settings(action)
    return opened[0] + "\nBitte WLAN in den Einstellungen wählen.", opened[1]


async def _router_admin(action: OwnerAction) -> tuple[str, bool]:
    AuditLog.action("OwnerAction", "router_admin", action.raw[:120])
    gateway = await _default_gateway()
    if not gateway:
        opened = await _wlan_open_settings(action)
        return (
            "[Owner] Router-Adresse nicht ermittelt.\n"
            "WLAN-Einstellungen geöffnet — verbundenes Netz prüfen.\n"
            + opened[0]
        ), opened[1]

    urls = [f"http://{gateway}", f"https://{gateway}"]
    lines = [f"[Owner] Router-Interface", f"Gateway: {gateway}", ""]
    for url in urls:
        note = await _browser_navigate(url, wait_ms=1500)
        opened = await _open_url(url)
        lines.extend([f"Versucht: {url}", note, opened, ""])
    return "\n".join(lines).strip(), True


async def _filesystem_cleanup(action: OwnerAction) -> tuple[str, bool]:
    scope = str(action.params.get("scope") or "standard")
    dry_run = bool(action.params.get("dry_run"))
    root_hint = str(action.params.get("root") or "")
    targets = _scan_cleanup_targets(scope, root_hint)
    stats = CleanupStats()

    for path, kind in targets:
        if not path.exists():
            continue
        size = _dir_size(path)
        label = f"[dry] {path}" if dry_run else str(path)
        try:
            if dry_run:
                if path.is_dir():
                    stats.removed_dirs.append(label)
                else:
                    stats.removed_files.append(label)
                stats.freed_bytes += size
                continue
            if path.is_dir():
                shutil.rmtree(path)
                stats.removed_dirs.append(label)
            else:
                path.unlink()
                stats.removed_files.append(label)
            stats.freed_bytes += size
        except Exception as exc:
            stats.skipped.append(f"{path}: {exc}")

    cleanup_roots = _cleanup_roots(scope, root_hint)
    if scope == "deep" and not dry_run:
        _remove_empty_dirs(cleanup_roots, stats, dry_run=False)
    elif scope == "deep" and dry_run:
        _remove_empty_dirs(cleanup_roots, stats, dry_run=True)

    AuditLog.action(
        "OwnerAction",
        "filesystem_cleanup",
        f"scope={scope} dry={dry_run} dirs={len(stats.removed_dirs)} files={len(stats.removed_files)} freed={stats.freed_bytes}",
    )
    mode = "Vorschau" if dry_run else "Abgeschlossen"
    lines = [
        f"[Owner] Dateisystem-Aufräumen {mode}.",
        f"Modus: {scope}" + (f" │ Pfad: {root_hint}" if root_hint else ""),
        f"Ordner: {len(stats.removed_dirs)}",
        f"Dateien: {len(stats.removed_files)}",
        f"Freigegeben: {stats.freed_bytes // 1024} KB",
    ]
    if stats.removed_dirs[:6]:
        lines.extend(["", "Ordner:", *[f"- {p}" for p in stats.removed_dirs[:6]]])
    if stats.removed_files[:6]:
        lines.extend(["", "Dateien:", *[f"- {p}" for p in stats.removed_files[:6]]])
    if stats.skipped[:4]:
        lines.extend(["", "Übersprungen:", *[f"- {s}" for s in stats.skipped[:4]]])
    return "\n".join(lines), True


async def _file_list(action: OwnerAction) -> tuple[str, bool]:
    from file_access import execute_file_command, FileCommand

    path = str(action.params.get("path") or "~").strip()
    cmd = FileCommand(
        operation="list",
        path=path,
        recursive="rekursiv" in action.raw.lower(),
    )
    AuditLog.action("OwnerAction", "file_list", path[:120])
    out, ok = execute_file_command(cmd)
    return f"[Owner] {out}", ok


async def _file_operation(action: OwnerAction) -> tuple[str, bool]:
    from file_access import execute_file_command, FileCommand, resolve_path

    op = str(action.params.get("operation") or "").strip().lower()
    source = str(action.params.get("source") or "").strip()
    destination = str(action.params.get("destination") or "").strip()
    AuditLog.action("OwnerAction", "file_operation", f"{op} {source[:80]}")

    if op in {"read", "delete"}:
        cmd = FileCommand(operation=op, path=source)
        out, ok = execute_file_command(cmd)
        return f"[Owner] {out}", ok

    if op in {"copy", "move"}:
        src_resolved, src_err = resolve_path(source)
        dst_resolved, dst_err = resolve_path(destination)
        if not src_resolved:
            return f"[Owner] Quelle: {src_err}", False
        if not dst_resolved:
            return f"[Owner] Ziel: {dst_err}", False
        if not src_resolved.exists():
            return f"[Owner] Quelle nicht gefunden: {src_resolved}", False
        try:
            if src_resolved.is_dir():
                if op == "copy":
                    shutil.copytree(src_resolved, dst_resolved, dirs_exist_ok=True)
                else:
                    shutil.move(str(src_resolved), str(dst_resolved))
            else:
                dst_resolved.parent.mkdir(parents=True, exist_ok=True)
                if op == "copy":
                    shutil.copy2(src_resolved, dst_resolved)
                else:
                    shutil.move(str(src_resolved), str(dst_resolved))
        except Exception as exc:
            return f"[Owner] {op} fehlgeschlagen: {exc}", False
        verb = "Kopiert" if op == "copy" else "Verschoben"
        return f"[Owner] {verb}: {src_resolved} → {dst_resolved}", True

    return f"[Owner] Unbekannte Dateioperation: {op}", False


async def _email_open(action: OwnerAction) -> tuple[str, bool]:
    AuditLog.action("OwnerAction", "email_open", action.raw[:80])
    return await _open_target(OwnerAction("open_target", {"target": "gmail"}, raw=action.raw))


async def _email_compose(action: OwnerAction) -> tuple[str, bool]:
    recipient = str(action.params.get("to") or "").strip()
    if not recipient:
        return "[Owner] Kein E-Mail-Empfänger erkannt.", False
    url = f"https://mail.google.com/mail/?view=cm&fs=1&to={quote_plus(recipient)}"
    AuditLog.action("OwnerAction", "email_compose", recipient[:80])
    opened = await _open_url(url)
    return f"[Owner] E-Mail-Entwurf für {recipient}\nURL: {url}\n{opened}", True


async def _email_search(action: OwnerAction) -> tuple[str, bool]:
    query = str(action.params.get("query") or "").strip()
    if not query:
        return "[Owner] Kein Mail-Suchbegriff erkannt.", False
    url = f"https://mail.google.com/mail/u/0/#search/{quote_plus(query)}"
    AuditLog.action("OwnerAction", "email_search", query[:120])
    opened = await _open_url(url)
    return f"[Owner] Gmail-Suche: {query}\nURL: {url}\n{opened}", True


async def _calendar_open(action: OwnerAction) -> tuple[str, bool]:
    view = str(action.params.get("view") or "open").strip().lower()
    paths = {
        "today": "https://calendar.google.com/calendar/r/day",
        "tomorrow": "https://calendar.google.com/calendar/r/day",
        "week": "https://calendar.google.com/calendar/r/week",
        "open": "https://calendar.google.com/",
    }
    url = paths.get(view, paths["open"])
    AuditLog.action("OwnerAction", "calendar_open", view)
    opened = await _open_url(url)
    label = {"today": "heute", "tomorrow": "morgen", "week": "diese Woche"}.get(view, "Kalender")
    return f"[Owner] Google Kalender ({label}) geöffnet.\nURL: {url}\n{opened}", True


async def _maps_navigate(action: OwnerAction) -> tuple[str, bool]:
    destination = str(action.params.get("destination") or "").strip()
    if not destination:
        return "[Owner] Kein Navigationsziel erkannt.", False
    url = f"https://www.google.com/maps/dir/?api=1&destination={quote_plus(destination)}"
    AuditLog.action("OwnerAction", "maps_navigate", destination[:120])
    browser_note = await _browser_navigate(url, wait_ms=2000)
    opened = await _open_url(url)
    return (
        f"[Owner] Navigation nach: {destination}\n"
        f"URL: {url}\n"
        f"{browser_note}\n"
        f"{opened}"
    ), True


async def _device_status(action: OwnerAction) -> tuple[str, bool]:
    kind = str(action.params.get("kind") or "all").strip().lower()
    AuditLog.action("OwnerAction", "device_status", kind)
    runtime = await _runtime()
    lines = [f"[Owner] Gerätestatus ({kind})", ""]

    if kind in {"calendar_today", "all"} and kind == "calendar_today":
        return await _calendar_open(OwnerAction("calendar_open", {"view": "today"}, raw=action.raw))

    if kind in {"battery", "all"}:
        if runtime.runtime == "termux":
            result = await _shell("termux-battery-status")
            if result.get("stdout"):
                lines.extend(["--- Akku ---", result["stdout"][:2000]])
        else:
            for cmd in ("upower -i $(upower -e | grep BAT | head -1) 2>/dev/null", "cat /sys/class/power_supply/BAT*/capacity 2>/dev/null"):
                result = await _shell(cmd)
                if result.get("stdout"):
                    lines.extend(["--- Akku ---", result["stdout"][:1000]])
                    break

    if kind in {"storage", "all"}:
        result = await _shell("df -h 2>/dev/null | head -20")
        if result.get("stdout"):
            lines.extend(["", "--- Speicher ---", result["stdout"][:2500]])

    if kind in {"ip", "all"}:
        for cmd in ("ip -4 addr show 2>/dev/null | grep inet", "hostname -I 2>/dev/null"):
            result = await _shell(cmd)
            if result.get("stdout"):
                lines.extend(["", "--- IP ---", result["stdout"][:1500]])
                break

    if kind in {"datetime", "all"}:
        result = await _shell("date '+%A %d.%m.%Y %H:%M:%S %Z' 2>/dev/null || date")
        if result.get("stdout"):
            lines.extend(["", "--- Datum/Uhrzeit ---", result["stdout"].strip()])

    if kind == "location":
        return await _location_get(OwnerAction("location", {}, raw=action.raw))

    if kind in {"processes", "all"} and kind == "processes":
        for cmd in ("top -bn1 | head -20", "ps aux --sort=-%mem | head -15"):
            result = await _shell(cmd)
            if result.get("stdout"):
                lines.extend(["", "--- Prozesse ---", result["stdout"][:3000]])
                break

    return "\n".join(lines).strip(), bool(len(lines) > 2)


async def _screenshot(action: OwnerAction) -> tuple[str, bool]:
    AuditLog.action("OwnerAction", "screenshot", action.raw[:80])
    runtime = await _runtime()
    stamp = time.strftime("%Y%m%d_%H%M%S")
    out_path = WORKSPACE / f"screenshot_{stamp}.png"
    if runtime.runtime == "termux":
        cmd = f"screencap -p {shlex_quote(str(out_path))}"
    else:
        cmd = f"import -window root {shlex_quote(str(out_path))} 2>/dev/null || scrot {shlex_quote(str(out_path))}"
    result = await _shell(cmd)
    if out_path.exists():
        return f"[Owner] Screenshot gespeichert: {out_path}", True
    return f"[Owner] Screenshot fehlgeschlagen: {result.get('error', result.get('stderr', 'unbekannt'))}", False


async def _camera(action: OwnerAction) -> tuple[str, bool]:
    AuditLog.action("OwnerAction", "camera", action.raw[:80])
    return await _app_open(OwnerAction("app_open", {"name": "kamera"}, raw=action.raw))


async def _phone_call(action: OwnerAction) -> tuple[str, bool]:
    number = str(action.params.get("number") or "").strip()
    if not number:
        return "[Owner] Keine Telefonnummer erkannt.", False
    dial = re.sub(r"[^\d\+]", "", number)
    AuditLog.action("OwnerAction", "phone_call", dial[:20])
    runtime = await _runtime()
    if runtime.runtime == "termux":
        result = await _shell(f"am start -a android.intent.action.DIAL -d tel:{dial}")
        if result.get("ok"):
            return f"[Owner] Wählfeld geöffnet für: {dial}", True
        return f"[Owner] Anruf fehlgeschlagen: {result.get('error', 'unbekannt')}", False
    result = await _shell(f"xdg-open tel:{dial} 2>/dev/null")
    return f"[Owner] Anruf initiiert: {dial}", bool(result.get("ok"))


async def _sms_send(action: OwnerAction) -> tuple[str, bool]:
    number = str(action.params.get("number") or "").strip()
    body = str(action.params.get("body") or "").strip()
    if not number:
        return "[Owner] Keine Nummer für SMS erkannt.", False
    dial = re.sub(r"[^\d\+]", "", number)
    AuditLog.action("OwnerAction", "sms_send", dial[:20])
    runtime = await _runtime()
    if runtime.runtime == "termux":
        body_arg = f" --es sms_body {shlex_quote(body)}" if body else ""
        result = await _shell(
            f"am start -a android.intent.action.SENDTO -d sms:{dial}{body_arg}"
        )
        if result.get("ok"):
            return f"[Owner] SMS-App geöffnet für: {dial}", True
        return f"[Owner] SMS fehlgeschlagen: {result.get('error', 'unbekannt')}", False
    return "[Owner] SMS nur auf Android/Termux verfügbar.", False


async def _translate(action: OwnerAction) -> tuple[str, bool]:
    text = str(action.params.get("text") or "").strip()
    lang = str(action.params.get("target_lang") or "en").strip()
    if not text:
        return "[Owner] Kein Text zum Übersetzen.", False
    url = f"https://translate.google.com/?sl=auto&tl={quote_plus(lang)}&text={quote_plus(text)}"
    AuditLog.action("OwnerAction", "translate", f"{lang} {text[:80]}")
    opened = await _open_url(url)
    return f"[Owner] Übersetzung ({lang}): {text[:200]}\nURL: {url}\n{opened}", True


async def _weather(action: OwnerAction) -> tuple[str, bool]:
    location = str(action.params.get("location") or "").strip()
    query = f"wetter {location}" if location else "wetter heute"
    AuditLog.action("OwnerAction", "weather", query[:80])
    try:
        from search import get_search

        result = await get_search().search(query, max_hits=5)
        if result and (result.abstract or result.hits):
            lines = [f"[Owner] Wetter: {query}", ""]
            if result.abstract:
                lines.append(result.abstract[:600])
            for hit in (result.hits or [])[:3]:
                lines.append(f"- {hit.titel}: {hit.snippet[:160] if hit.snippet else hit.url}")
            return "\n".join(lines), True
    except Exception as exc:
        log.debug("Weather search failed: %s", exc)
    url = f"https://www.google.com/search?q={quote_plus(query)}"
    opened = await _open_url(url)
    return f"[Owner] Wetterabfrage: {query}\nURL: {url}\n{opened}", True


async def _media_play(action: OwnerAction) -> tuple[str, bool]:
    platform = str(action.params.get("platform") or "youtube").strip().lower()
    query = str(action.params.get("query") or "").strip()
    if not query:
        return "[Owner] Kein Medien-Suchbegriff.", False
    urls = {
        "spotify": f"https://open.spotify.com/search/{quote_plus(query)}",
        "youtube": f"https://www.youtube.com/results?search_query={quote_plus(query)}",
    }
    url = urls.get(platform, urls["youtube"])
    AuditLog.action("OwnerAction", "media_play", f"{platform} {query[:80]}")
    opened = await _open_url(url)
    return f"[Owner] {platform.title()}-Suche: {query}\nURL: {url}\n{opened}", True


async def _timer(action: OwnerAction) -> tuple[str, bool]:
    seconds = int(action.params.get("seconds") or 0)
    if seconds <= 0:
        return "[Owner] Ungültige Timer-Dauer.", False
    AuditLog.action("OwnerAction", "timer", f"seconds={seconds}")
    runtime = await _runtime()
    if runtime.runtime == "termux":
        result = await _shell(
            f"termux-notification --title 'Isaac Timer' --content 'Läuft...' "
            f"--button1 'OK' --id isaac_timer && (sleep {seconds} && "
            f"termux-vibrate -d 800 && termux-notification --title 'Timer fertig' "
            f"--content 'Zeit abgelaufen' --id isaac_timer_done) &"
        )
        if result.get("ok"):
            return f"[Owner] Timer gestartet: {seconds} Sekunden.", True
    return f"[Owner] Timer: {seconds}s (sleep {seconds} im Hintergrund empfohlen).", True


async def _alarm(action: OwnerAction) -> tuple[str, bool]:
    alarm_time = str(action.params.get("time") or "").strip()
    AuditLog.action("OwnerAction", "alarm", alarm_time[:20])
    runtime = await _runtime()
    if runtime.runtime == "termux":
        if alarm_time:
            hour, minute = alarm_time.split(":", 1)
            result = await _shell(
                f"am start -a android.intent.action.SET_ALARM "
                f"--ei android.intent.extra.alarm.HOUR {int(hour)} "
                f"--ei android.intent.extra.alarm.MINUTES {int(minute)}"
            )
        else:
            result = await _shell("am start -a android.intent.action.SET_ALARM")
        if result.get("ok"):
            return f"[Owner] Wecker-App geöffnet" + (f" ({alarm_time})" if alarm_time else "") + ".", True
        return f"[Owner] Wecker fehlgeschlagen: {result.get('error', 'unbekannt')}", False
    return "[Owner] Wecker nur auf Android/Termux verfügbar.", False


async def _contacts(action: OwnerAction) -> tuple[str, bool]:
    query = str(action.params.get("query") or "").strip()
    AuditLog.action("OwnerAction", "contacts", query[:80])
    runtime = await _runtime()
    if runtime.runtime == "termux":
        if query:
            result = await _shell(
                f"am start -a android.intent.action.VIEW "
                f"-d content://com.android.contacts/contacts/filter/{quote_plus(query)}"
            )
        else:
            result = await _shell(
                "am start -a android.intent.action.VIEW -d content://com.android.contacts/contacts/"
            )
        if result.get("ok"):
            return f"[Owner] Kontakte geöffnet" + (f" (Suche: {query})" if query else "") + ".", True
        return f"[Owner] Kontakte fehlgeschlagen: {result.get('error', 'unbekannt')}", False
    return "[Owner] Kontakte nur auf Android/Termux verfügbar.", False


async def _bluetooth(action: OwnerAction) -> tuple[str, bool]:
    op = str(action.params.get("op") or "settings").strip().lower()
    AuditLog.action("OwnerAction", "bluetooth", op)
    runtime = await _runtime()
    if op == "settings":
        return await _app_open(OwnerAction("app_open", {"name": "bluetooth"}, raw=action.raw))
    if runtime.runtime == "termux":
        if op == "scan":
            result = await _shell("termux-bluetooth-scan -d 8")
            if result.get("stdout"):
                return f"[Owner] Bluetooth-Scan:\n{result['stdout'][:3000]}", True
        if op == "status":
            result = await _shell("termux-bluetooth-info")
            if result.get("stdout"):
                return f"[Owner] Bluetooth:\n{result['stdout'][:2000]}", True
    result = await _shell("bluetoothctl show 2>/dev/null; bluetoothctl devices 2>/dev/null | head -20")
    return f"[Owner] Bluetooth:\n{result.get('stdout', result.get('error', 'nicht verfügbar'))}", bool(result.get("stdout"))


async def _tts(action: OwnerAction) -> tuple[str, bool]:
    text = str(action.params.get("text") or "").strip()
    if not text:
        return "[Owner] Kein Text für Sprachausgabe.", False
    AuditLog.action("OwnerAction", "tts", text[:80])
    runtime = await _runtime()
    if runtime.runtime == "termux":
        result = await _shell(f"termux-tts-speak {shlex_quote(text)}")
        if result.get("ok"):
            return f"[Owner] Vorlesen: {text[:200]}", True
        return f"[Owner] TTS fehlgeschlagen: {result.get('error', 'unbekannt')}", False
    result = await _shell(f"espeak {shlex_quote(text)} 2>/dev/null || spd-say {shlex_quote(text)} 2>/dev/null")
    return f"[Owner] Vorlesen: {text[:200]}", bool(result.get("ok"))


async def _notification_send(action: OwnerAction) -> tuple[str, bool]:
    text = str(action.params.get("text") or "").strip()
    if not text:
        return "[Owner] Kein Benachrichtigungstext.", False
    AuditLog.action("OwnerAction", "notification", text[:80])
    runtime = await _runtime()
    if runtime.runtime == "termux":
        result = await _shell(
            f"termux-notification --title 'Isaac' --content {shlex_quote(text)}"
        )
        if result.get("ok"):
            return f"[Owner] Benachrichtigung gesendet: {text[:200]}", True
        return f"[Owner] Benachrichtigung fehlgeschlagen: {result.get('error', 'unbekannt')}", False
    return "[Owner] Benachrichtigungen nur mit Termux-API verfügbar.", False


async def _network_test(action: OwnerAction) -> tuple[str, bool]:
    kind = str(action.params.get("kind") or "ping").strip().lower()
    target = str(action.params.get("target") or "8.8.8.8").strip()
    AuditLog.action("OwnerAction", "network_test", f"{kind} {target[:40]}")
    if kind == "speedtest":
        result = await _shell("curl -s https://raw.githubusercontent.com/sivel/speedtest-cli/master/speedtest.py | python3 - 2>/dev/null | head -20")
        if not result.get("stdout"):
            return await _open_target(OwnerAction("open_target", {"target": "https://fast.com"}, raw=action.raw))
        return f"[Owner] Speedtest:\n{result['stdout'][:4000]}", True
    result = await _shell(f"ping -c 4 {shlex_quote(target)} 2>/dev/null || ping -n 4 {shlex_quote(target)}")
    lines = [f"[Owner] Ping {target}", "", result.get("stdout") or result.get("error", "fehlgeschlagen")]
    return "\n".join(lines), bool(result.get("ok"))


async def _download_url(action: OwnerAction) -> tuple[str, bool]:
    url = str(action.params.get("url") or "").strip()
    dest = str(action.params.get("path") or str(WORKSPACE)).strip()
    if not url:
        return "[Owner] Keine Download-URL.", False
    if not url.startswith("http"):
        url = f"https://{url}"
    dest_path = Path(dest).expanduser()
    if dest_path.is_dir():
        filename = url.rstrip("/").split("/")[-1] or "download.bin"
        dest_path = dest_path / filename
    AuditLog.action("OwnerAction", "download_url", url[:120])
    result = await _shell(f"curl -fL --retry 2 -o {shlex_quote(str(dest_path))} {shlex_quote(url)}")
    if dest_path.exists():
        return f"[Owner] Heruntergeladen: {dest_path} ({dest_path.stat().st_size} Bytes)", True
    return f"[Owner] Download fehlgeschlagen: {result.get('error', result.get('stderr', 'unbekannt'))}", False


async def _file_write(action: OwnerAction) -> tuple[str, bool]:
    from file_access import execute_file_command, FileCommand

    path = str(action.params.get("path") or "").strip()
    content = str(action.params.get("content") or "")
    cmd = FileCommand(operation="write", path=path, content=content)
    AuditLog.action("OwnerAction", "file_write", path[:80])
    out, ok = execute_file_command(cmd)
    return f"[Owner] {out}", ok


async def _mkdir(action: OwnerAction) -> tuple[str, bool]:
    from file_access import resolve_path

    path = str(action.params.get("path") or "").strip()
    resolved, error = resolve_path(path)
    if not resolved:
        return f"[Owner] {error}", False
    try:
        resolved.mkdir(parents=True, exist_ok=True)
        AuditLog.action("OwnerAction", "mkdir", str(resolved)[:120])
        return f"[Owner] Ordner erstellt: {resolved}", True
    except Exception as exc:
        return f"[Owner] Ordner fehlgeschlagen: {exc}", False


async def _find_files(action: OwnerAction) -> tuple[str, bool]:
    name = str(action.params.get("name") or "").strip()
    root = str(action.params.get("root") or "~").strip()
    if not name:
        return "[Owner] Kein Dateiname.", False
    from file_access import resolve_path

    resolved, error = resolve_path(root)
    if not resolved or not resolved.exists():
        return f"[Owner] Suchpfad: {error or 'nicht gefunden'}", False
    AuditLog.action("OwnerAction", "find_files", f"{name} in {resolved}")
    if "*" in name or "?" in name:
        cmd = f"find {shlex_quote(str(resolved))} -name {shlex_quote(name)} 2>/dev/null | head -40"
    else:
        cmd = f"find {shlex_quote(str(resolved))} -iname {shlex_quote('*' + name + '*')} 2>/dev/null | head -40"
    result = await _shell(cmd)
    output = (result.get("stdout") or "").strip()
    if output:
        return f"[Owner] Gefunden in {resolved}:\n{output}", True
    return f"[Owner] Keine Treffer für '{name}' in {resolved}.", False


async def _archive(action: OwnerAction) -> tuple[str, bool]:
    op = str(action.params.get("operation") or "").strip().lower()
    source = str(action.params.get("source") or "").strip()
    destination = str(action.params.get("destination") or "").strip()
    from file_access import resolve_path

    src, err = resolve_path(source)
    if not src or not src.exists():
        return f"[Owner] Quelle: {err or 'nicht gefunden'}", False
    AuditLog.action("OwnerAction", "archive", f"{op} {source[:60]}")
    if op == "zip":
        dst, derr = resolve_path(destination) if destination else (None, "")
        dst_path = str(dst) if dst else str(src) + ".zip"
        if not dst_path.endswith(".zip"):
            dst_path += ".zip"
        result = await _shell(f"zip -r {shlex_quote(dst_path)} {shlex_quote(str(src))}")
        return f"[Owner] Archiv erstellt: {dst_path}", bool(result.get("ok"))
    dst_dir = resolve_path(destination)[0] if destination else src.parent
    dst = str(dst_dir or src.parent)
    result = await _shell(f"unzip -o {shlex_quote(str(src))} -d {shlex_quote(dst)}")
    return f"[Owner] Entpackt nach: {dst}", bool(result.get("ok"))


async def _open_folder(action: OwnerAction) -> tuple[str, bool]:
    from file_access import resolve_path

    path = str(action.params.get("path") or "").strip()
    resolved, error = resolve_path(path)
    if not resolved:
        return f"[Owner] {error}", False
    AuditLog.action("OwnerAction", "open_folder", str(resolved)[:120])
    runtime = await _runtime()
    if runtime.runtime == "termux":
        uri = f"file://{resolved}"
        result = await _shell(f"am start -a android.intent.action.VIEW -d {shlex_quote(uri)} -t resource/folder")
        if result.get("ok"):
            return f"[Owner] Ordner geöffnet: {resolved}", True
    result = await _shell(f"xdg-open {shlex_quote(str(resolved))} 2>/dev/null")
    return f"[Owner] Ordner: {resolved}", bool(result.get("ok"))


async def _shopping_search(action: OwnerAction) -> tuple[str, bool]:
    platform = str(action.params.get("platform") or "amazon").strip().lower()
    query = str(action.params.get("query") or "").strip()
    urls = {
        "amazon": f"https://www.amazon.de/s?k={quote_plus(query)}",
        "ebay": f"https://www.ebay.de/sch/i.html?_nkw={quote_plus(query)}",
        "kleinanzeigen": f"https://www.kleinanzeigen.de/s-suchanfrage.html?keywords={quote_plus(query)}",
    }
    url = urls.get(platform, urls["amazon"])
    AuditLog.action("OwnerAction", "shopping_search", f"{platform} {query[:80]}")
    opened = await _open_url(url)
    return f"[Owner] {platform.title()}-Suche: {query}\nURL: {url}\n{opened}", True


async def _calendar_create(action: OwnerAction) -> tuple[str, bool]:
    title = str(action.params.get("title") or "").strip()
    if not title:
        return "[Owner] Kein Termintitel.", False
    url = f"https://calendar.google.com/calendar/r/eventedit?text={quote_plus(title)}"
    AuditLog.action("OwnerAction", "calendar_create", title[:80])
    opened = await _open_url(url)
    return f"[Owner] Termin erstellen: {title}\nURL: {url}\n{opened}", True


async def _device_toggle(action: OwnerAction) -> tuple[str, bool]:
    target = str(action.params.get("target") or "").strip().lower()
    state = str(action.params.get("state") or "on").strip().lower()
    enabled = state == "on"
    AuditLog.action("OwnerAction", "device_toggle", f"{target}={state}")
    runtime = await _runtime()
    commands: dict[str, tuple[str, str]] = {
        "wlan": (
            f"termux-wifi-enable {'true' if enabled else 'false'}",
            "nmcli radio wifi on" if enabled else "nmcli radio wifi off",
        ),
        "torch": (
            f"termux-torch {'on' if enabled else 'off'}",
            "",
        ),
        "bluetooth": (
            "",
            f"bluetoothctl power {'on' if enabled else 'off'}",
        ),
        "airplane": (
            "am start -a android.settings.AIRPLANE_MODE_SETTINGS",
            "",
        ),
        "hotspot": (
            "am start -a android.settings.TETHER_SETTINGS",
            "",
        ),
        "mobile_data": (
            "am start -a android.settings.DATA_ROAMING_SETTINGS",
            "",
        ),
    }
    termux_cmd, linux_cmd = commands.get(target, ("", ""))
    if runtime.runtime == "termux" and termux_cmd:
        result = await _shell(termux_cmd)
        if result.get("ok"):
            return f"[Owner] {target} → {state}", True
        if target in {"airplane", "hotspot", "mobile_data"}:
            return f"[Owner] Einstellungen für {target} geöffnet — bitte manuell schalten.", True
        return f"[Owner] {target} fehlgeschlagen: {result.get('error', 'unbekannt')}", False
    if linux_cmd:
        result = await _shell(linux_cmd)
        return f"[Owner] {target} → {state}", bool(result.get("ok"))
    return f"[Owner] Toggle {target}/{state} nicht unterstützt.", False


async def _location_get(action: OwnerAction) -> tuple[str, bool]:
    AuditLog.action("OwnerAction", "location", action.raw[:80])
    runtime = await _runtime()
    if runtime.runtime == "termux":
        data = await _shell_json("termux-location -p gps")
        if isinstance(data, dict):
            lat = data.get("latitude")
            lon = data.get("longitude")
            acc = data.get("accuracy")
            if lat is not None and lon is not None:
                maps = f"https://maps.google.com/?q={lat},{lon}"
                return (
                    f"[Owner] Standort: {lat}, {lon}"
                    + (f" (±{acc}m)" if acc else "")
                    + f"\nMaps: {maps}"
                ), True
        result = await _shell("termux-location -p gps")
        if result.get("stdout"):
            return f"[Owner] Standort:\n{result['stdout'][:2000]}", True
    return "[Owner] Standort nur mit Termux-API (termux-location) verfügbar.", False


async def _git_command(action: OwnerAction) -> tuple[str, bool]:
    """Owner git: status/diff/commit/restore via native git_ops; else legacy shell.

    Phase 3.7 — no push through git_ops; push/pull/fetch keep shell path with audit.
    """
    command = str(action.params.get("command") or "").strip()
    if not command:
        return "[Owner] Kein Git-Befehl.", False
    AuditLog.action("OwnerAction", "git_command", command[:120])

    # Block force-push style from owner shell path too (defense in depth)
    low = command.lower()
    if re.search(r"\bpush\b", low) and re.search(r"(--force|-f\b)", low):
        return "[Owner] git push --force ist blockiert.", False

    try:
        from git_ops import (
            format_git_result,
            parse_owner_git_command,
            run_parsed_git_op,
        )

        parsed = parse_owner_git_command(command)
        if parsed is not None:
            res = run_parsed_git_op(parsed, root=BASE_DIR)
            text = f"[Owner] {command}\n{format_git_result(res)}"
            return text.strip(), bool(res.ok)
    except Exception as exc:
        log.debug("git_ops owner path fallback: %s", exc)

    # Legacy: pull / fetch / log / push (non-force) / unknown
    cwd = shlex_quote(str(BASE_DIR))
    result = await _shell(f"cd {cwd} && {command}")
    lines = [f"[Owner] {command}", "", result.get("stdout") or result.get("error", "")]
    return "\n".join(lines).strip(), bool(result.get("ok"))


async def _credential_access(action: OwnerAction) -> tuple[str, bool]:
    from computer_use import AgentAction, format_agent_result, get_computer_use

    site = str(action.params.get("site") or "").strip()
    do_import = bool(action.params.get("import"))
    runtime = get_computer_use()
    if not site:
        result = await runtime.execute(AgentAction("credential_list"))
    else:
        result = await runtime.execute(
            AgentAction("credential_read", {"site": site, "import": do_import})
        )
    text = format_agent_result(result).replace("[Agent]", "[Owner]", 1)
    return text, bool(result.get("ok"))


async def _security_toolkit(action: OwnerAction) -> tuple[str, bool]:
    from security_toolkit import execute_security_command
    from procedure_memory import record_owner_action_outcome

    result, ok = await execute_security_command(dict(action.params or {}))
    try:
        kind = str(action.params.get("tool_id") or action.params.get("action") or "security_toolkit")
        record_owner_action_outcome(kind=f"security:{kind}", raw=action.raw, ok=ok)
    except Exception as exc:
        log.debug("Security procedure capture skipped: %s", exc)
    return result, ok


async def _bug_bounty(action: OwnerAction) -> tuple[str, bool]:
    """Authorized bug-bounty list/scan with tested evidence reports."""
    op = str(action.params.get("op") or "list").strip().lower()
    try:
        from bug_bounty import (
            format_programs_report,
            format_scan_report,
            run_program_scan,
        )

        if op in {"list", "status", "programs"}:
            return format_programs_report(), True
        if op == "scan":
            pid = str(action.params.get("program_id") or "").strip()
            if not pid:
                return "[BugBounty] program_id fehlt — bug bounty scan <id>", False
            result = await asyncio.to_thread(run_program_scan, pid)
            return format_scan_report(result), bool(result.get("ok"))
        return f"[BugBounty] Unbekannte Op: {op}", False
    except Exception as exc:
        return f"[BugBounty] Fehler: {exc}", False


async def _package_install(action: OwnerAction) -> tuple[str, bool]:
    command = str(action.params.get("command") or "").strip()
    if not command:
        return "[Owner] Kein Installationsbefehl.", False
    AuditLog.action("OwnerAction", "package_install", command[:120])
    result = await _shell(command)
    lines = [f"[Owner] {command}", ""]
    if result.get("stdout"):
        lines.append(result["stdout"][:6000])
    if result.get("stderr"):
        lines.append(result["stderr"][:2000])
    return "\n".join(lines), bool(result.get("ok"))


async def _isaac_ops(action: OwnerAction) -> tuple[str, bool]:
    op = str(action.params.get("op") or "status").strip().lower()
    AuditLog.action("OwnerAction", "isaac_ops", op)
    if op == "logs":
        lines = ["[Owner] Isaac-Logs", ""]
        if LOG_DIR.exists():
            for path in sorted(LOG_DIR.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)[:3]:
                try:
                    tail = path.read_text(encoding="utf-8", errors="replace").splitlines()[-15:]
                    lines.extend([f"--- {path.name} ---", *tail, ""])
                except OSError:
                    pass
        return "\n".join(lines).strip() or "[Owner] Keine Logs gefunden.", True
    if op == "restart":
        return (
            "[Owner] Neustart manuell ausführen:\n"
            f"  cd {BASE_DIR} && bash run_isaac.sh\n"
            "Oder laufenden Prozess beenden und isaac_core.py neu starten."
        ), True
    lines = [
        "[Owner] Isaac-Status",
        f"BASE_DIR: {BASE_DIR}",
        f"WORKSPACE: {WORKSPACE}",
        f"DATA_DIR: {DATA_DIR}",
        f"Privilege: {'admin' if is_owner_equivalent_mode() else 'user'}",
        f"Computer-Use: {get_config().computer_use_enabled}",
        f"Browser: {get_config().browser_automation}",
    ]
    try:
        from owner_autonomy import autonomy_status

        auto = autonomy_status()
        lines.append(
            f"Owner-Autonomie: {'an' if auto.get('enabled') else 'aus'} "
            f"(max/Zyklus={auto.get('max_per_cycle')}, "
            f"geplant={auto.get('scheduled_count')}, "
            f"fällig={','.join(auto.get('due_task_ids') or []) or '-'})"
        )
        nxt = auto.get("next_run") or {}
        if nxt.get("task_id") and nxt.get("next_run"):
            lines.append(
                f"Nächster Lauf: {nxt.get('task_id')} @ {nxt.get('next_run')} "
                f"(in {nxt.get('hours_until')}h)"
            )
        for row in (auto.get("next_runs") or [])[:3]:
            if row.get("task_id") == nxt.get("task_id"):
                continue
            lines.append(
                f"  danach: {row.get('task_id')} @ {row.get('next_run')} "
                f"(in {row.get('hours_until')}h)"
            )
    except Exception:
        pass
    try:
        from automation_pipeline import format_automation_status

        lines.append("")
        lines.append(format_automation_status())
    except Exception:
        pass
    return "\n".join(lines), True


async def _clipboard(action: OwnerAction) -> tuple[str, bool]:
    op = str(action.params.get("operation") or "").strip().lower()
    text = str(action.params.get("text") or "")
    AuditLog.action("OwnerAction", "clipboard", op)
    runtime = await _runtime()
    if runtime.runtime != "termux":
        return "[Owner] Zwischenablage nur mit Termux-API (termux-clipboard-*) verfügbar.", False
    if op == "read":
        result = await _shell("termux-clipboard-get")
        content = (result.get("stdout") or "").strip()
        if content:
            return f"[Owner] Zwischenablage:\n{content[:4000]}", True
        return "[Owner] Zwischenablage leer oder nicht lesbar.", bool(result.get("ok"))
    if op == "write":
        if not text:
            return "[Owner] Kein Text für Zwischenablage.", False
        result = await _shell(f"termux-clipboard-set {shlex_quote(text)}")
        if result.get("ok"):
            return f"[Owner] Zwischenablage gesetzt ({len(text)} Zeichen).", True
        return f"[Owner] Zwischenablage fehlgeschlagen: {result.get('error', 'unbekannt')}", False
    return "[Owner] Unbekannte Zwischenablage-Operation.", False


async def _chrome_tabs(action: OwnerAction) -> tuple[str, bool]:
    """List Chrome tabs from Magisk-readable storage."""
    full = bool(action.params.get("full"))
    try:
        from chrome_tabs import format_tabs_report, list_tabs

        result = await list_tabs(limit=40, full=full)
        return format_tabs_report(result), bool(result.get("ok"))
    except Exception as exc:
        return f"[Chrome Tabs] Fehler: {exc}", False


async def _chrome_tab_open(action: OwnerAction) -> tuple[str, bool]:
    """Open cached tab index in Android Chrome."""
    idx = int(action.params.get("index") or 0)
    try:
        from chrome_tabs import get_cached_tab, list_tabs

        tab = get_cached_tab(idx)
        if not tab:
            # refresh once
            await list_tabs(limit=40, full=False)
            tab = get_cached_tab(idx)
        if not tab:
            return (
                f"[Chrome Tabs] Tab {idx} unbekannt — zuerst: chrome tabs",
                False,
            )
        url = tab.get("url") or ""
        return await _app_open(
            OwnerAction(
                "app_open",
                {"name": "chrome", "url": url},
                raw=action.raw,
            )
        )
    except Exception as exc:
        return f"[Chrome Tabs] Öffnen fehlgeschlagen: {exc}", False


async def _chrome_secrets(action: OwnerAction) -> tuple[str, bool]:
    """Read Chrome cookies catalog, autofill, cards, accounts (owner)."""
    section = str(action.params.get("section") or "all")
    dump = bool(action.params.get("dump"))
    host = str(action.params.get("host") or "").strip()
    try:
        from chrome_secrets import collect_secrets, format_secrets_report

        result = await collect_secrets(
            host_filter=host,
            include_dump=dump,
        )
        return format_secrets_report(result, section=section), bool(result.get("ok"))
    except Exception as exc:
        return f"[Chrome Secrets] Fehler: {exc}", False


async def _chrome_decrypt(action: OwnerAction) -> tuple[str, bool]:
    """Live memory extract of plaintext cookie/token values (owner)."""
    reveal = bool(action.params.get("reveal", True))
    name_filter = str(action.params.get("name_filter") or "").strip()
    export_jar = bool(action.params.get("export_jar", True))
    try:
        from chrome_secrets import (
            format_live_decrypt_report,
            items_to_cookie_jar,
            live_decrypt_sessions,
            write_cookie_jar,
        )

        result = await live_decrypt_sessions(
            reveal=reveal,
            name_filter=name_filter,
        )
        if result.get("ok") and export_jar and reveal:
            entries = items_to_cookie_jar(result.get("items") or [])
            jar = write_cookie_jar(entries, basename="cookies")
            result["cookie_jar"] = jar
        return format_live_decrypt_report(result, reveal=reveal), bool(result.get("ok"))
    except Exception as exc:
        return f"[Chrome Decrypt] Fehler: {exc}", False


async def _cookie_jar_export(action: OwnerAction) -> tuple[str, bool]:
    """Export Netscape/JSON cookie jar from live memory decrypt."""
    refresh = bool(action.params.get("refresh", True))
    try:
        from chrome_secrets import export_cookie_jar, format_cookie_jar_report

        result = await export_cookie_jar(refresh_live=refresh, reveal=True)
        return format_cookie_jar_report(result), bool(result.get("ok"))
    except Exception as exc:
        return f"[Cookie Jar] Fehler: {exc}", False


async def _ui_passwords(action: OwnerAction) -> tuple[str, bool]:
    """Read password fields from current Android UI hierarchy."""
    reveal = bool(action.params.get("reveal", True))
    try_show = bool(action.params.get("try_show", True))
    try:
        from android_apps import format_ui_passwords_report, read_ui_password_fields

        result = await read_ui_password_fields(try_show=try_show)
        return format_ui_passwords_report(result, reveal=reveal), bool(result.get("ok"))
    except Exception as exc:
        return f"[UI Passwords] Fehler: {exc}", False


async def _apps_list(action: OwnerAction) -> tuple[str, bool]:
    query = str(action.params.get("query") or "").strip()
    third = bool(action.params.get("third_party"))
    try:
        from android_apps import format_apps_list, list_packages

        result = await list_packages(third_party_only=third)
        return format_apps_list(result, query=query), bool(result.get("ok") or result.get("packages"))
    except Exception as exc:
        return f"[Apps] Liste fehlgeschlagen: {exc}", False


async def _app_stop(action: OwnerAction) -> tuple[str, bool]:
    name = str(action.params.get("name") or "").strip()
    try:
        from android_apps import force_stop, resolve_package

        resolved = await resolve_package(name)
        if not resolved.get("ok"):
            return f"[Apps] Stop: {resolved.get('error')}", False
        pkg = resolved["package"]
        result = await force_stop(pkg)
        if result.get("ok"):
            return f"[Apps] force-stop: {pkg}", True
        return f"[Apps] force-stop fehlgeschlagen: {result.get('error') or result}", False
    except Exception as exc:
        return f"[Apps] Stop Fehler: {exc}", False


async def _android_activity(action: OwnerAction) -> tuple[str, bool]:
    try:
        from android_apps import current_activity

        result = await current_activity()
        if result.get("focus"):
            return f"[Apps] Vordergrund: {result['focus']}", True
        raw = (result.get("raw") or "")[:400]
        return f"[Apps] Activity:\n{raw or result.get('error') or 'unbekannt'}", bool(raw)
    except Exception as exc:
        return f"[Apps] Activity Fehler: {exc}", False


async def _android_ui_dump(action: OwnerAction) -> tuple[str, bool]:
    try:
        from android_apps import format_ui_dump, ui_dump_text

        result = await ui_dump_text()
        return format_ui_dump(result), bool(result.get("ok"))
    except Exception as exc:
        return f"[UI] Dump Fehler: {exc}", False


async def _android_input(action: OwnerAction) -> tuple[str, bool]:
    op = str(action.params.get("op") or "").strip()
    try:
        from android_apps import input_key, input_tap, input_text, ui_tap_label

        if op == "tap_xy":
            r = await input_tap(int(action.params.get("x") or 0), int(action.params.get("y") or 0))
            return (
                f"[UI] tap {r.get('x')},{r.get('y')} ok={r.get('ok')}",
                bool(r.get("ok")),
            )
        if op == "tap_label":
            label = str(action.params.get("label") or "")
            r = await ui_tap_label(label)
            if r.get("ok"):
                return f"[UI] getippt: {r.get('label')} @{r.get('x')},{r.get('y')}", True
            return f"[UI] tippe fehlgeschlagen: {r.get('error')}", False
        if op == "text":
            text = str(action.params.get("text") or "")
            r = await input_text(text)
            return f"[UI] text ({r.get('len')} Zeichen) ok={r.get('ok')}", bool(r.get("ok"))
        if op == "key":
            key = action.params.get("key") or "back"
            r = await input_key(key)
            return f"[UI] key {key} ok={r.get('ok')}", bool(r.get("ok"))
        return f"[UI] Unbekannte Input-Op: {op}", False
    except Exception as exc:
        return f"[UI] Input Fehler: {exc}", False


async def _apps_status(action: OwnerAction) -> tuple[str, bool]:
    """Diagnose Android app launch path (Termux bridge)."""
    lines = ["[Apps / Android-Brücke]"]
    try:
        from termux_bridge import bridge_enabled, bridge_mode, diagnose_bridge

        diag = diagnose_bridge()
        lines.append(f"bridge_enabled={bridge_enabled()} mode={bridge_mode()}")
        if isinstance(diag, dict):
            lines.append(f"available={diag.get('mode') != 'none'}")
            for p in diag.get("probes") or []:
                if isinstance(p, dict):
                    lines.append(
                        f"  probe {p.get('mode')}: available={p.get('available')} "
                        f"{(p.get('detail') or '')[:60]}"
                    )
            tools = diag.get("tools") or {}
            ok_tools = [k for k, v in tools.items() if v]
            bad_tools = [k for k, v in tools.items() if not v]
            lines.append(f"  tools_ok={ok_tools or '—'}")
            if bad_tools:
                lines.append(f"  tools_missing={bad_tools[:8]}")
        lines.append("")
        lines.append("Befehle: öffne chrome | öffne die app gmail | öffne maps.google.com in chrome")
        if (diag or {}).get("mode") == "none" or not any(
            (p or {}).get("available") for p in (diag or {}).get("probes") or []
        ):
            lines.append("")
            lines.append(_BRIDGE_SETUP_HINT)
        return "\n".join(lines), True
    except Exception as exc:
        return f"[Apps] Diagnose fehlgeschlagen: {exc}\n\n{_BRIDGE_SETUP_HINT}", False


async def _launch_android_package(
    package: str,
    *,
    url: str = "",
    label: str = "",
) -> dict[str, Any]:
    """Try Termux-bridge / am / monkey / termux-open to start a real Android app."""
    package = (package or "").strip()
    url = (url or "").strip()
    label = label or package
    attempts: list[str] = []

    # 1) Prefer bridge with explicit shell that uses Android am
    try:
        from termux_bridge import bridge_available, run_termux_command

        if bridge_available():
            if url:
                # Open URL in specific package (Chrome keeps Google session)
                cmd = (
                    f"am start -a android.intent.action.VIEW "
                    f"-d {shlex_quote(url)} -p {shlex_quote(package)}"
                )
                r = await run_termux_command(["sh", "-c", cmd], timeout=20.0)
                attempts.append(f"bridge am VIEW: ok={r.get('ok')} err={r.get('error','')[:80]}")
                if r.get("ok"):
                    return {
                        "ok": True,
                        "via": "termux_bridge:am_view",
                        "package": package,
                        "url": url,
                        "attempts": attempts,
                    }
                # termux-open-url (default handler = often Chrome)
                r2 = await run_termux_command(["termux-open-url", url], timeout=15.0)
                attempts.append(f"bridge termux-open-url: ok={r2.get('ok')}")
                if r2.get("ok"):
                    return {
                        "ok": True,
                        "via": "termux_bridge:termux-open-url",
                        "package": package,
                        "url": url,
                        "attempts": attempts,
                    }
            # Launch package
            for cmd in (
                f"monkey -p {shlex_quote(package)} -c android.intent.category.LAUNCHER 1",
                f"am start $(cmd package resolve-activity --brief {shlex_quote(package)} 2>/dev/null | tail -n 1)",
            ):
                r = await run_termux_command(["sh", "-c", cmd], timeout=20.0)
                attempts.append(f"bridge launch: ok={r.get('ok')} {cmd[:50]}")
                if r.get("ok"):
                    return {
                        "ok": True,
                        "via": "termux_bridge:am",
                        "package": package,
                        "attempts": attempts,
                    }
            # termux-open package
            r3 = await run_termux_command(
                ["termux-open", f"android-app://{package}"],
                timeout=15.0,
            )
            attempts.append(f"bridge termux-open app: ok={r3.get('ok')}")
            if r3.get("ok"):
                return {
                    "ok": True,
                    "via": "termux_bridge:termux-open",
                    "package": package,
                    "attempts": attempts,
                }
        else:
            attempts.append("bridge_unavailable")
    except Exception as exc:
        attempts.append(f"bridge_exc:{exc}")

    # 2) Direct shell (when am exists in PATH — pure Termux runtime)
    if url:
        r = await _shell(
            f"am start -a android.intent.action.VIEW -d {shlex_quote(url)} "
            f"-p {shlex_quote(package)}"
        )
        attempts.append(f"shell am VIEW: ok={r.get('ok')}")
        if r.get("ok"):
            return {"ok": True, "via": "shell:am_view", "package": package, "url": url, "attempts": attempts}
    r = await _shell(
        f"monkey -p {shlex_quote(package)} -c android.intent.category.LAUNCHER 1"
    )
    attempts.append(f"shell monkey: ok={r.get('ok')} err={(r.get('error') or r.get('stderr') or '')[:80]}")
    if r.get("ok"):
        return {"ok": True, "via": "shell:monkey", "package": package, "attempts": attempts}

    return {
        "ok": False,
        "error": "android_launch_failed",
        "package": package,
        "label": label,
        "attempts": attempts,
        "hint": _BRIDGE_SETUP_HINT,
    }


async def _app_open(action: OwnerAction) -> tuple[str, bool]:
    name = _normalize(str(action.params.get("name") or ""))
    url = str(action.params.get("url") or "").strip()
    AuditLog.action("OwnerAction", "app_open", f"{name[:60]} url={url[:80]}")

    # Intent-based settings apps
    intent = _ANDROID_INTENTS.get(name)
    if intent and not url:
        is_action_intent = intent.startswith("android.")
        if is_action_intent:
            result = await _shell(f"am start -a {shlex_quote(intent)}")
            if not result.get("ok"):
                try:
                    from termux_bridge import bridge_available, run_termux_command

                    if bridge_available():
                        result = await run_termux_command(
                            ["sh", "-c", f"am start -a {shlex_quote(intent)}"],
                            timeout=15.0,
                        )
                except Exception:
                    pass
            if result.get("ok"):
                return f"[Owner] Android-Intent geöffnet: {intent}", True
            return (
                f"[Owner] Intent fehlgeschlagen: {result.get('error', 'unbekannt')}\n\n"
                f"{_BRIDGE_SETUP_HINT}",
                False,
            )
        # package-as-intent-value (legacy calculator etc.)
        package = intent if re.match(r"^[\w.]+$", intent) else ""
        if package and package.count(".") >= 1:
            launch = await _launch_android_package(package, label=name)
            if launch.get("ok"):
                return (
                    f"[Owner] App gestartet: {name} ({package}) via {launch.get('via')}",
                    True,
                )

    package = _APP_PACKAGES.get(name, "")
    if not package and re.match(r"^[\w.]+$", name) and name.count(".") >= 1:
        package = name  # raw package id

    suggestions: list[str] = []
    if not package:
        try:
            from android_apps import resolve_package

            resolved = await resolve_package(name)
            if resolved.get("ok"):
                package = str(resolved.get("package") or "")
                suggestions = list(resolved.get("suggestions") or [])
        except Exception as exc:
            log.debug("resolve_package: %s", exc)

    if package:
        launch = await _launch_android_package(package, url=url, label=name)
        if launch.get("ok"):
            extra = f"\nURL: {url}" if url else ""
            hint_more = ""
            if suggestions and len(suggestions) > 1:
                hint_more = f"\n(weitere Treffer: {', '.join(suggestions[1:4])})"
            return (
                f"[Owner] Android-App geöffnet: {name} ({package}) "
                f"via {launch.get('via')}{extra}"
                f"{hint_more}\n"
                f"(Echte App — Sessions der App gelten.)",
                True,
            )
        attempts = "; ".join(launch.get("attempts") or [])[:300]
        return (
            f"[Owner] Konnte App '{name}' ({package}) nicht starten.\n"
            f"Versuche: {attempts}\n\n"
            f"{launch.get('hint') or _BRIDGE_SETUP_HINT}",
            False,
        )

    # Site alias URL without package
    if name in _SITE_ALIASES:
        return await _open_target(
            OwnerAction("open_target", {"target": name, "prefer_native": True}, raw=action.raw)
        )

    return (
        f"[Owner] Unbekannte App: {name}\n"
        f"Bekannt u. a.: {', '.join(sorted(_APP_PACKAGES)[:12])}…\n"
        f"Oder: apps list | öffne app com.android.chrome | suche app whatsapp",
        False,
    )


async def _shell_action(action: OwnerAction) -> tuple[str, bool]:
    command = str(action.params.get("command") or "").strip()
    if not command:
        return "[Owner] Leerer Shell-Befehl.", False
    AuditLog.action("OwnerAction", "shell", command[:160])
    result = await _shell(command)
    lines = [f"[Owner] Shell: {command}", ""]
    if result.get("stdout"):
        lines.append(result["stdout"][:6000])
    if result.get("stderr"):
        lines.append(f"stderr: {result['stderr'][:1000]}")
    if result.get("error"):
        lines.append(f"Fehler: {result['error']}")
    return "\n".join(lines), bool(result.get("ok"))


async def _open_target(action: OwnerAction) -> tuple[str, bool]:
    target = str(action.params.get("target") or "").strip()
    if not target:
        return "[Owner] Kein Ziel angegeben.", False

    lower = target.lower()
    # App name mistaken as open_target
    for pkg_name in sorted(_APP_PACKAGES, key=len, reverse=True):
        if lower == pkg_name or lower.strip() == pkg_name:
            return await _app_open(
                OwnerAction("app_open", {"name": pkg_name}, raw=action.raw)
            )

    for alias, url in sorted(_SITE_ALIASES.items(), key=lambda x: -len(x[0])):
        if alias in lower or lower == alias:
            target = url
            break

    if not re.match(r"^https?://", target, re.I):
        if re.match(r"^[\w.-]+\.[a-z]{2,}", target, re.I) and " " not in target:
            target = f"https://{target}"
        else:
            target = f"https://www.google.com/search?q={quote_plus(target)}"

    AuditLog.action("OwnerAction", "open_target", target[:160])
    # Prefer native Android Chrome (session!) over Playwright
    native = await _launch_android_package(
        "com.android.chrome",
        url=target,
        label="chrome",
    )
    if native.get("ok"):
        return (
            f"[Owner] Geöffnet in Android-Chrome: {target}\n"
            f"via {native.get('via')} (deine App-Session)",
            True,
        )
    opened = await _open_url(target)
    browser_note = await _browser_navigate(target, wait_ms=800)
    hint = ""
    if not native.get("ok"):
        hint = f"\n(Hinweis: Android-Chrome nicht erreichbar — {_BRIDGE_SETUP_HINT.splitlines()[0]})"
    return f"[Owner] Geöffnet: {target}\n{opened}\n{browser_note}{hint}", True


async def _open_url(url: str) -> str:
    from computer_use import AgentAction, computer_use_enabled

    # Native first
    native = await _launch_android_package("com.android.chrome", url=url, label="chrome")
    if native.get("ok"):
        return f"Android-Chrome via {native.get('via')}."

    if computer_use_enabled():
        runtime = await _runtime()
        result = await runtime.execute(AgentAction("open", {"target": url}))
        if result.get("ok"):
            via = result.get("via", "Computer-Use")
            return f"Geöffnet über {via}."
        cu_err = result.get("error", "unbekannt")
    else:
        cu_err = "computer_use off"

    if get_config().browser_automation:
        note = await _browser_navigate(url)
        if "Browser" in note and "fehlgeschlagen" not in note.lower():
            return f"{note} (Playwright — eigene Session, nicht Android-Chrome)"
        return f"{note}; computer_use={cu_err}"
    return f"Öffne URL manuell (native Chrome fehlgeschlagen; {cu_err})."


async def _browser_navigate(url: str, wait_ms: int = 1000) -> str:
    if not get_config().browser_automation:
        return ""
    try:
        from browser import get_browser

        result = await get_browser().run_flow(
            "owner-action",
            url,
            [
                {"action": "goto", "url": url},
                {"action": "wait", "ms": wait_ms},
                {"action": "extract_text", "selector": "title", "save_as": "page_title"},
            ],
            name="Owner Action",
        )
        if result.get("ok"):
            title = (result.get("memory") or {}).get("page_title", "")
            current = result.get("current_url", url)
            return f"Browser: {current}" + (f" │ Titel: {title[:120]}" if title else "")
        return f"Browser: {result.get('error', 'Navigation fehlgeschlagen')}"
    except Exception as exc:
        return f"Browser: {exc}"


async def _default_gateway() -> str:
    result = await _shell("ip route 2>/dev/null | awk '/default/ {print $3; exit}'")
    gw = (result.get("stdout") or "").strip().splitlines()[0] if result.get("stdout") else ""
    if gw:
        return gw
    data = await _shell_json("termux-wifi-connectioninfo")
    if isinstance(data, dict):
        for key in ("gateway", "ip_gateway", "router"):
            val = data.get(key)
            if val:
                return str(val)
    return ""


async def _current_wifi_ssid() -> str:
    data = await _shell_json("termux-wifi-connectioninfo")
    if isinstance(data, dict):
        for key in ("ssid", "SSID"):
            if data.get(key):
                return str(data[key])
    runtime = await _runtime()
    if runtime.runtime == "s8":
        for cmd in ("iwgetid -r 2>/dev/null", "iw dev wlan0 link 2>/dev/null | awk '/SSID/ {print $2}'"):
            result = await _shell(cmd)
            ssid = (result.get("stdout") or "").strip()
            if ssid:
                return ssid
    result = await _shell("nmcli -t -f ACTIVE,SSID dev wifi 2>/dev/null | awk -F: '$1==\"yes\" {print $2; exit}'")
    return (result.get("stdout") or "").strip()


def shlex_quote(value: str) -> str:
    if not value:
        return "''"
    if re.match(r"^[a-zA-Z0-9_@.:-]+$", value):
        return value
    return "'" + value.replace("'", "'\"'\"'") + "'"


def owner_action_enabled() -> bool:
    return is_owner_equivalent_mode()