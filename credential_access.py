from __future__ import annotations

"""Owner-only Zugriff auf Credentials (intern + sichtbar auf dem Bildschirm)."""

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

from audit import AuditLog
from config import is_owner_equivalent_mode
from ui_automation import UINode, _fold_label, find_nodes

_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_MASKED_RE = re.compile(r"^[\*•·\.\u2022\s]+$")
_SITE_RE = re.compile(r"^[a-z0-9][a-z0-9\-\.]*\.[a-z]{2,}(?:\s|$|/)", re.I)

_SHOW_PASSWORD_LABELS = (
    "anzeigen",
    "show password",
    "passwort anzeigen",
    "passwort zeigen",
    "show",
    "sichtbar",
    "eye",
    "auge",
)

_BROWSER_CREDS_PATH = Path(__file__).parent / "data" / "browser_creds.json"


@dataclass(frozen=True)
class CredentialRecord:
    source: str
    site: str
    username: str
    password: str
    login_url: str = ""

    def to_dict(self, *, reveal: bool = False) -> dict[str, str]:
        return {
            "source": self.source,
            "site": self.site,
            "username": self.username,
            "password": self.password if reveal else mask_secret(self.password),
            "login_url": self.login_url,
        }


def credential_access_allowed() -> bool:
    return is_owner_equivalent_mode()


def require_credential_access() -> Optional[str]:
    if credential_access_allowed():
        return None
    return "Credential-Zugriff nur im Owner/Admin-Modus (ISAAC_PRIVILEGE_MODE=admin)."


def mask_secret(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    if len(raw) <= 4:
        return "****"
    return f"{raw[:2]}...{raw[-2:]}"


def audit_credential_access(action: str, detail: str) -> None:
    AuditLog.action("CredentialAccess", action, detail[:200], level=40)


def list_internal_credentials() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    if _BROWSER_CREDS_PATH.exists():
        try:
            data = json.loads(_BROWSER_CREDS_PATH.read_text(encoding="utf-8"))
            for domain, payload in data.items():
                rows.append(
                    {
                        "source": "browser_creds",
                        "site": domain,
                        "username": str(payload.get("username") or ""),
                        "password": mask_secret(str(payload.get("password") or "")),
                        "login_url": str(payload.get("login_url") or ""),
                    }
                )
        except Exception:
            pass
    try:
        from secrets_store import get_secrets_store

        for ref, row in (get_secrets_store()._cache or {}).items():
            kind = str((row or {}).get("kind") or "secret")
            rows.append(
                {
                    "source": "secrets_store",
                    "site": ref,
                    "username": kind,
                    "password": mask_secret(str((row or {}).get("value") or "")),
                    "login_url": "",
                }
            )
    except Exception:
        pass
    return rows


def list_visible_sites(nodes: list[UINode], *, limit: int = 40) -> list[str]:
    seen: set[str] = set()
    sites: list[str] = []
    for node in nodes:
        text = (node.text or node.content_desc or "").strip()
        if not text or text in seen:
            continue
        folded = _fold_label(text)
        if _EMAIL_RE.match(text):
            continue
        if _MASKED_RE.match(text):
            continue
        if "." in text and (_SITE_RE.match(text) or any(tld in folded for tld in (".com", ".de", ".org", ".net", ".io"))):
            seen.add(text)
            sites.append(text)
            if len(sites) >= limit:
                break
    return sites


def _password_candidates(nodes: list[UINode]) -> list[str]:
    found: list[str] = []
    for node in nodes:
        text = (node.text or "").strip()
        if not text or _MASKED_RE.match(text) or _EMAIL_RE.match(text):
            continue
        label = _fold_label(node.label)
        if node.is_password or "passwort" in label or "password" in label:
            if len(text) >= 4:
                found.append(text)
            continue
        if 8 <= len(text) <= 128 and " " not in text and any(ch.isdigit() for ch in text):
            if re.fullmatch(r"[A-Za-z0-9_@#$%&*+\-/:=?.,!]+", text):
                found.append(text)
    deduped: list[str] = []
    seen: set[str] = set()
    for item in found:
        if item not in seen:
            seen.add(item)
            deduped.append(item)
    return deduped


def extract_visible_credentials(nodes: list[UINode], *, site_hint: str = "") -> list[CredentialRecord]:
    emails = [n.text.strip() for n in nodes if _EMAIL_RE.match((n.text or "").strip())]
    passwords = _password_candidates(nodes)
    sites = list_visible_sites(nodes)
    site = site_hint.strip() or (sites[0] if sites else "")
    if site_hint:
        matches = [s for s in sites if _labels_match_site(site_hint, s)]
        if matches:
            site = matches[0]
    username = emails[0] if emails else ""
    password = passwords[0] if passwords else ""
    if not username and not password and not site:
        return []
    return [
        CredentialRecord(
            source="ui_screen",
            site=site,
            username=username,
            password=password,
            login_url=_guess_login_url(site),
        )
    ]


def _labels_match_site(query: str, label: str) -> bool:
    q = _fold_label(query)
    hay = _fold_label(label)
    if not q or not hay:
        return False
    return q in hay or hay in q


def _guess_login_url(site: str) -> str:
    raw = (site or "").strip()
    if not raw:
        return ""
    if raw.startswith(("http://", "https://")):
        return raw
    if "." in raw:
        return f"https://{raw.split()[0]}"
    return ""


def read_internal_credential(site_query: str) -> Optional[CredentialRecord]:
    query = _fold_label(site_query)
    if not query:
        return None
    if _BROWSER_CREDS_PATH.exists():
        try:
            data = json.loads(_BROWSER_CREDS_PATH.read_text(encoding="utf-8"))
            for domain, payload in data.items():
                if _labels_match_site(query, domain):
                    return CredentialRecord(
                        source="browser_creds",
                        site=domain,
                        username=str(payload.get("username") or ""),
                        password=str(payload.get("password") or ""),
                        login_url=str(payload.get("login_url") or ""),
                    )
        except Exception:
            pass
    try:
        from secrets_store import get_secrets_store

        store = get_secrets_store()
        for ref in store._cache.keys():
            if _labels_match_site(query, ref):
                value = (store.get_secret(ref) or "").strip()
                return CredentialRecord(
                    source="secrets_store",
                    site=ref,
                    username="",
                    password=value,
                    login_url="",
                )
    except Exception:
        pass
    return None


def import_credential(record: CredentialRecord) -> dict[str, str]:
    domain = (record.site or "").strip()
    if not domain:
        raise ValueError("Import ohne Site/Domäne nicht möglich")
    login_url = record.login_url or _guess_login_url(domain)
    host = urlparse(login_url).netloc if login_url else domain
    if record.username and record.password:
        from browser import get_browser

        get_browser().add_credential(host or domain, login_url or f"https://{domain}", record.username, record.password)
        audit_credential_access("import_browser", f"domain={host or domain}")
        return {"target": "browser_creds", "domain": host or domain}
    if record.password:
        from secrets_store import get_secrets_store

        ref = domain.upper().replace(".", "_").replace("-", "_")
        get_secrets_store().set_secret(ref, record.password, kind="credential_import")
        audit_credential_access("import_secret", f"ref={ref}")
        return {"target": "secrets_store", "ref": ref}
    raise ValueError("Nichts zu importieren (Passwort fehlt)")


def pick_show_password_label(nodes: list[UINode]) -> Optional[str]:
    for label in _SHOW_PASSWORD_LABELS:
        if find_nodes(nodes, label, clickable_only=True):
            return label
    return None