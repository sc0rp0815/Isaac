from __future__ import annotations

"""Isaac – Execution Contract (mission routing + evidence + background)

Sichert, dass Owner-Imperative (Browser, Login, gebundene Missionen) tatsächlich
ausgeführt werden und Antworten nur mit echter Tool-Evidenz Erfolg behaupten.

Kein zweiter Router im Executor: Klassifikation/Kernel entscheidet; dieses Modul
liefert Detection, Evidence-Format und goal-gebundene Background-Missionen.
"""

import json
import logging
import os
import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

from config import DATA_DIR
from audit import AuditLog

log = logging.getLogger("Isaac.ExecutionContract")

MISSIONS_PATH = DATA_DIR / "execution_missions.json"
PENDING_BROWSER_PATH = DATA_DIR / "pending_browser_mission.json"

# ── Mission kinds ─────────────────────────────────────────────────────────────
KIND_BROWSER_NAVIGATE = "browser_navigate"
KIND_BROWSER_LOGIN = "browser_login"
KIND_BOUNTY_RESEARCH = "bounty_research"
KIND_GENERIC = "generic"

# ── Known targets (host nicknames → URL) ──────────────────────────────────────
KNOWN_TARGETS: dict[str, str] = {
    "github": "https://github.com",
    "google": "https://www.google.com",
    "gmail": "https://mail.google.com",
    "accounts.google": "https://accounts.google.com",
    "openrouter": "https://openrouter.ai",
    "groq": "https://console.groq.com",
    "wikipedia": "https://de.wikipedia.org",
    "hackerone": "https://hackerone.com",
    "bugcrowd": "https://bugcrowd.com",
    "yeswehack": "https://yeswehack.com",
    "intigriti": "https://www.intigriti.com",
    "synack": "https://www.synack.com",
    "revolut": "https://app.revolut.com",
}

BOUNTY_MARKERS = (
    "hackerone",
    "bugcrowd",
    "yeswehack",
    "intigriti",
    "synack",
    "bug bounty",
    "bugbounty",
    "belohnung",
    "bounty",
    "verwundbarkeit",
    "vulnerability program",
)

LOGIN_MARKERS = (
    "einloggen",
    "log dich",
    "logge dich",
    "melde dich",
    "anmelden",
    "login",
    "sign in",
    "sign-in",
    "anmeldung",
)

NAVIGATE_MARKERS = (
    "gehe auf",
    "geh auf",
    "gehe zu",
    "geh zu",
    "öffne ",
    "oeffne ",
    "navigiere zu",
    "besuche ",
    "rufe auf",
    "mach auf",
    "browser auf",
    "browser:",
    "browser ",
)

# Phrases that claim tool/browser success OR impending action without evidence
_FAKE_SUCCESS_RE = re.compile(
    r"(?is)\b("
    r"ich habe (mich )?(erfolgreich )?(.{0,40}?)?(eingeloggt|angemeldet|geöffnet|navigiert|besucht)"
    r"|ich bin (jetzt )?(eingeloggt|auf der seite|angemeldet)"
    r"|login (war |erfolgreich|geklappt)"
    r"|seite (ist |wurde )?(geöffnet|geladen|aufgerufen)"
    r"|browser (ist |wurde )?(geöffnet|gestartet)"
    r"|ich habe (die )?aufgabe (erledigt|ausgeführt|abgeschlossen)"
    r"|ich habe (mich )?bei .+ angemeldet"
    r"|successfully (logged in|navigated|opened)"
    # Future/claim theater (common LLM failure mode)
    r"|ich starte (die |jetzt die |nun die )?browser"
    r"|ich starte (jetzt |nun )?(die )?browser[- ]?automation"
    r"|ich werde (jetzt |nun )?(die )?browser"
    r"|ich melde mich an und hole"
    r"|ich (öffne|navigiere) (jetzt |nun )?(den )?browser"
    r"|browser[- ]?automation[,.]? (melde|starte|hole)"
    r")\b"
)

# Owner short confirms that should resume a pending browser mission
_OWNER_CONFIRM_RE = re.compile(
    r"(?is)^\s*("
    r"ich bestätige( es)?|bestätigt|bestätigung"
    r"|ja[,.]?\s*(mach|los|fortfahren|weiter|bitte)"
    r"|ok[,.]?\s*(mach|los|fortfahren|weiter)?"
    r"|mach (es|weiter|jetzt)"
    r"|fortfahren|weiter so|go ahead|do it|confirmed"
    r"|ja$"
    r")\s*[.!]?\s*$"
)

_EVIDENCE_MARKERS = (
    "[Browser]",
    "[Evidence]",
    "[Mission]",
    "[Provider]",
    "Aktuelle URL:",
    "Steps:",
    "ok=true",
    "ok=false",
)


@dataclass
class MissionSpec:
    """Parsed owner mission from natural language."""

    kind: str
    title: str
    target_url: str = ""
    target_label: str = ""
    login_user: Optional[str] = None
    login_password: Optional[str] = None
    wants_background: bool = False
    bounty_authorized_only: bool = True
    raw: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        # Never persist plaintext password into mission JSON via to_dict callers
        # that write to disk — callers should strip login_password first.
        return d


@dataclass
class StoredMission:
    id: str
    kind: str
    title: str
    status: str = "active"  # active | paused | done | failed
    goal_id: str = ""
    target_url: str = ""
    login_user: str = ""
    # password never stored here — only in browser cred store
    steps_done: int = 0
    last_evidence: str = ""
    last_error: str = ""
    created_at: str = ""
    updated_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StoredMission":
        return cls(
            id=str(data.get("id") or ""),
            kind=str(data.get("kind") or KIND_GENERIC),
            title=str(data.get("title") or ""),
            status=str(data.get("status") or "active"),
            goal_id=str(data.get("goal_id") or ""),
            target_url=str(data.get("target_url") or ""),
            login_user=str(data.get("login_user") or ""),
            steps_done=int(data.get("steps_done") or 0),
            last_evidence=str(data.get("last_evidence") or ""),
            last_error=str(data.get("last_error") or ""),
            created_at=str(data.get("created_at") or ""),
            updated_at=str(data.get("updated_at") or ""),
            metadata=dict(data.get("metadata") or {}),
        )


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _new_id() -> str:
    return f"msn_{uuid.uuid4().hex[:10]}"


def missions_enabled() -> bool:
    raw = str(os.getenv("ISAAC_EXECUTION_MISSIONS", "1") or "1").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def max_missions_per_tick() -> int:
    raw = os.getenv("ISAAC_MISSION_MAX_PER_TICK")
    if raw is None or str(raw).strip() == "":
        return 1
    try:
        return max(1, min(5, int(raw)))
    except (TypeError, ValueError):
        return 1


# ── Target / credential extraction ───────────────────────────────────────────

def normalize_target(token: str) -> Optional[str]:
    """Map nickname or host token to https URL."""
    raw = (token or "").strip().strip("\"'").rstrip(".,;:!?")
    if not raw:
        return None
    first = raw.split()[0].strip().rstrip(".,;:!?") if raw.split() else raw
    lower = first.lower()
    if lower.startswith(("http://", "https://")):
        return first
    # strip path for known lookup
    key = lower.split("/")[0]
    key = key.replace("www.", "")
    if key in KNOWN_TARGETS:
        return KNOWN_TARGETS[key]
    # partial match (hacker.one etc.)
    for nick, url in KNOWN_TARGETS.items():
        if nick in key or key in nick:
            return url
    if "." in key or key == "localhost":
        return f"https://{first}"
    # bare word that looks like a site name
    if re.fullmatch(r"[a-z0-9-]{2,40}", key):
        return f"https://{key}.com"
    return None


def extract_credentials(text: str) -> tuple[Optional[str], Optional[str]]:
    """Extract optional login user/password from free text.

    Supports:
      login: u@x passwort: p
      email-looking token + separate password-like token after login verbs
    Never logs secrets.
    """
    raw = text or ""
    user = None
    password = None
    user_m = re.search(
        r"\b(?:login|user|username|email|e-mail)\s*:\s*(\S+)",
        raw,
        re.I,
    )
    if user_m:
        user = user_m.group(1).strip().strip("\"'")
    pass_m = re.search(
        r"\b(?:passwort|password|passwd|pass|pw)\s*:\s*(\S+)",
        raw,
        re.I,
    )
    if pass_m:
        password = pass_m.group(1).strip().strip("\"'")

    if not user:
        email_m = re.search(
            r"\b([A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,})\b",
            raw,
        )
        if email_m:
            user = email_m.group(1)

    if user and not password:
        # After email, a non-trivial token that is not a common stopword
        after = raw[raw.lower().find(user.lower()) + len(user) :]
        # Explicit label already handled; try bare trailing password-like token
        candidates = re.findall(r"\S+", after)
        stop = {
            "und", "bitte", "dann", "bei", "auf", "zu", "mit", "dich", "mich",
            "einloggen", "anmelden", "login", "passwort", "password", "pw",
            "gehe", "geh", "öffne", "oeffne", "kannst", "du", "sollst",
        }
        for tok in candidates:
            t = tok.strip(".,;:!?\"'")
            if not t or t.lower() in stop:
                continue
            if "@" in t:
                continue
            if re.fullmatch(r"https?://\S+", t, re.I):
                continue
            # password-ish: length >= 6 or mixed
            if len(t) >= 6:
                password = t
                break

    return user, password


def _find_target_label(text: str) -> tuple[str, str]:
    """Return (label, url) from text, or ("", "")."""
    tl = (text or "").lower()
    # Prefer known bounty/sites by name
    for nick, url in KNOWN_TARGETS.items():
        if nick in tl or nick.replace(".", "") in tl:
            return nick, url
    # URL-like tokens
    url_m = re.search(r"(https?://[^\s]+|www\.[^\s]+|[a-z0-9.-]+\.[a-z]{2,}(?:/[^\s]*)?)", tl, re.I)
    if url_m:
        token = url_m.group(1).rstrip(".,;:!?")
        url = normalize_target(token)
        if url:
            return token, url
    # "gehe auf X" / "öffne X"
    m = re.search(
        r"(?:gehe? (?:auf|zu)|öffne|oeffne|besuche|navigiere zu|browser auf)\s+([a-z0-9][a-z0-9.\-]{1,60})",
        tl,
        re.I,
    )
    if m:
        token = m.group(1).strip().rstrip(".,;:!?")
        url = normalize_target(token)
        if url:
            return token, url
    return "", ""


def detect_mission(text: str) -> Optional[MissionSpec]:
    """Detect actionable owner mission from natural language.

    Returns None for pure chat/explanatory questions.
    """
    raw = (text or "").strip()
    if not raw or len(raw) < 3:
        return None
    tl = raw.lower()

    # Explanatory / non-action: "erkläre mir hackerone" → not a mission
    if re.match(r"^(?:erklä|erklae|was ist|was bedeutet|wie funktioniert)", tl):
        return None

    user, password = extract_credentials(raw)
    label, url = _find_target_label(raw)
    has_login = any(m in tl for m in LOGIN_MARKERS) or bool(user and password)
    has_nav = any(m in tl for m in NAVIGATE_MARKERS) or bool(url)
    has_bounty = any(m in tl for m in BOUNTY_MARKERS)
    has_work_verb = any(
        v in tl
        for v in (
            "erarbeit",
            "selbstständig",
            "selbststandig",
            "eigenständig",
            "eigenstandig",
            "autonom",
            "im hintergrund",
            "background",
            "weiterarbeiten",
            "suche belohnung",
            "finde belohnung",
            "verdien",
        )
    )

    if not (has_login or has_nav or has_bounty):
        # bare "log dich bei google ein …" without navigate marker still caught by login
        return None

    # Prefer login URL for google login missions
    if has_login and label in {"google", "gmail", "accounts.google"}:
        url = "https://accounts.google.com/signin/v2/identifier"
        label = label or "google"

    if has_bounty and has_work_verb:
        if not url:
            # default program hub if only "bug bounty" said
            for nick in ("hackerone", "bugcrowd", "yeswehack", "intigriti"):
                if nick in tl:
                    url = KNOWN_TARGETS[nick]
                    label = nick
                    break
            if not url:
                url = KNOWN_TARGETS["hackerone"]
                label = "hackerone"
        return MissionSpec(
            kind=KIND_BOUNTY_RESEARCH,
            title=f"Bug-Bounty Mission: {label or 'authorized programs'}",
            target_url=url,
            target_label=label or "hackerone",
            login_user=user,
            login_password=password,
            wants_background=True,
            bounty_authorized_only=True,
            raw=raw,
            metadata={"authorized_only": True},
        )

    if has_login and (url or label):
        if not url and label:
            url = normalize_target(label) or ""
        return MissionSpec(
            kind=KIND_BROWSER_LOGIN,
            title=f"Login: {label or url}",
            target_url=url or "",
            target_label=label,
            login_user=user,
            login_password=password,
            wants_background=False,
            raw=raw,
        )

    if has_nav and url:
        wants_bg = has_work_verb or has_bounty
        kind = KIND_BOUNTY_RESEARCH if has_bounty else KIND_BROWSER_NAVIGATE
        return MissionSpec(
            kind=kind,
            title=f"Browser: {label or url}",
            target_url=url,
            target_label=label,
            login_user=user,
            login_password=password,
            wants_background=wants_bg,
            bounty_authorized_only=has_bounty,
            raw=raw,
        )

    if has_login and user:
        # login without clear target
        return MissionSpec(
            kind=KIND_BROWSER_LOGIN,
            title="Login (Ziel unklar)",
            target_url="",
            target_label="",
            login_user=user,
            login_password=password,
            wants_background=False,
            raw=raw,
            metadata={"needs_target": True},
        )

    return None


def is_browser_mission(text: str) -> bool:
    """True if text should route to browser/mission path (not pure chat)."""
    # Legacy explicit prefixes
    tl = (text or "").lower().strip()
    if tl.startswith("browser:") or tl.startswith("browser "):
        return True
    if any(tl.startswith(p) for p in ("browser auf", "öffne im browser", "navigiere zu")):
        return True
    spec = detect_mission(text)
    if not spec:
        return False
    return spec.kind in {
        KIND_BROWSER_NAVIGATE,
        KIND_BROWSER_LOGIN,
        KIND_BOUNTY_RESEARCH,
    }


def mission_to_browser_parse(spec: MissionSpec) -> Optional[dict[str, Any]]:
    """Convert MissionSpec to the simple browser request dict shape."""
    if not spec or not spec.target_url:
        return None
    return {
        "instance_id": "mission-browse",
        "url": spec.target_url,
        "name": spec.title[:80] or "Mission Browse",
        "extract": True,
        "login_user": spec.login_user,
        "login_password": spec.login_password,
        "mission_kind": spec.kind,
        "wants_background": spec.wants_background,
        "bounty_authorized_only": spec.bounty_authorized_only,
    }


# ── Evidence ──────────────────────────────────────────────────────────────────

def format_evidence_block(
    *,
    source: str,
    ok: bool,
    url: str = "",
    current_url: str = "",
    steps: Optional[list] = None,
    excerpt: str = "",
    error: str = "",
    extra_lines: Optional[list[str]] = None,
) -> str:
    """Build a machine-readable evidence block for owner-facing replies."""
    lines = [
        "[Evidence]",
        f"source={source}",
        f"ok={'true' if ok else 'false'}",
    ]
    if url:
        lines.append(f"requested_url={url}")
    if current_url:
        lines.append(f"current_url={current_url}")
    if steps is not None:
        lines.append(f"steps={len(steps)}")
    if error:
        lines.append(f"error={redact_secrets(str(error)[:300])}")
    if extra_lines:
        lines.extend(extra_lines)
    body = "\n".join(lines)
    if excerpt:
        body += f"\n\n--- Seitenauszug ---\n{excerpt[:3500]}"
    return body


def redact_secrets(text: str) -> str:
    """Redact password-like and credential labels from free text."""
    out = text or ""
    out = re.sub(
        r"(?i)(passwort|password|passwd|pass|pw)\s*:\s*\S+",
        r"\1: ***",
        out,
    )
    out = re.sub(
        r"(?i)(login|user|username|email|e-mail)\s*:\s*(\S+)",
        lambda m: f"{m.group(1)}: ***" if "@" not in m.group(2) else f"{m.group(1)}: {m.group(2)[:2]}***",
        out,
    )
    # Bare email keep domain only for readability? Keep local partially
    return out


def has_tool_evidence(text: str) -> bool:
    t = text or ""
    return any(m in t for m in _EVIDENCE_MARKERS)


def looks_like_fake_tool_success(text: str) -> bool:
    if has_tool_evidence(text):
        return False
    return bool(_FAKE_SUCCESS_RE.search(text or ""))


def is_owner_confirm(text: str) -> bool:
    """True for short owner confirms that may resume a pending browser mission."""
    return bool(_OWNER_CONFIRM_RE.match((text or "").strip()))


def extract_browser_command_hint(*texts: str) -> str:
    """Best-effort reconstruct an explicit browser: command from free text."""
    blob = " ".join(t for t in texts if t).strip()
    if not blob:
        return ""
    # Already explicit
    low = blob.lower()
    if low.startswith("browser:") or low.startswith("browser "):
        return blob if low.startswith("browser:") else ("browser: " + blob.split(None, 1)[-1])
    # URL present
    m = re.search(r"https?://[^\s\"'<>]+", blob, re.I)
    if m:
        url = m.group(0).rstrip(".,;:)")
        rest = blob[m.end() :].strip()
        # Drop theater verbs from rest
        rest = re.sub(
            r"(?is)\b(ich starte|browser[- ]?automation|melde mich|danach|brauchst du).*$",
            "",
            rest,
        ).strip()
        cmd = f"browser: {url}"
        if rest and len(rest) < 80:
            cmd = f"{cmd}  {rest}"
        return cmd
    # Known nicknames
    low_full = blob.lower()
    for nick, url in KNOWN_TARGETS.items():
        if nick in low_full:
            extra = ""
            if "api" in low_full and "key" in low_full.replace("-", ""):
                extra = " hole API keys"
            elif "login" in low_full or "anmeld" in low_full:
                extra = " login"
            return f"browser: {url}{extra}"
    return ""


def save_pending_browser_mission(
    command: str,
    *,
    source: str = "",
    title: str = "",
    ttl_s: float = 1800.0,
) -> dict[str, Any]:
    """Persist a browser command for owner confirm resume."""
    cmd = (command or "").strip()
    if not cmd:
        return {}
    if not cmd.lower().startswith("browser"):
        cmd = f"browser: {cmd}"
    payload = {
        "command": cmd,
        "title": (title or cmd)[:120],
        "source": source or "unknown",
        "created_ts": time.time(),
        "expires_s": float(ttl_s),
    }
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        PENDING_BROWSER_PATH.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        AuditLog.action(
            "ExecutionContract",
            "pending_browser_saved",
            f"source={source} cmd={cmd[:100]}",
            erfolg=True,
        )
    except Exception as exc:
        log.debug("pending browser save failed: %s", exc)
        return {}
    return payload


def load_pending_browser_mission() -> Optional[dict[str, Any]]:
    """Load non-expired pending browser mission, or None."""
    if not PENDING_BROWSER_PATH.exists():
        return None
    try:
        raw = json.loads(PENDING_BROWSER_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(raw, dict):
        return None
    cmd = (raw.get("command") or "").strip()
    if not cmd:
        return None
    created = float(raw.get("created_ts") or 0)
    expires = float(raw.get("expires_s") or 1800)
    if created and (time.time() - created) > expires:
        clear_pending_browser_mission()
        return None
    return raw


def clear_pending_browser_mission() -> None:
    try:
        if PENDING_BROWSER_PATH.exists():
            PENDING_BROWSER_PATH.unlink()
    except Exception as exc:
        log.debug("pending browser clear failed: %s", exc)


def apply_anti_hallucination(
    user_input: str,
    antwort: str,
    *,
    tools_ran: bool = False,
) -> str:
    """Strip or rewrite hallucinated tool/browser success claims.

    If the user asked for an action and the model claims success without
    evidence markers (and tools_ran is False), replace with honest status.
    """
    raw = antwort or ""
    if tools_ran or has_tool_evidence(raw):
        return raw
    if not looks_like_fake_tool_success(raw):
        return raw

    mission = detect_mission(user_input) if user_input else None
    # Also trigger on clear action verbs even without full mission detect
    tl = (user_input or "").lower()
    action_like = bool(mission) or any(
        m in tl for m in LOGIN_MARKERS + NAVIGATE_MARKERS + BOUNTY_MARKERS
    )
    # Browser-theater in the model answer itself counts as action-like
    answer_browser_claim = bool(
        re.search(
            r"(?is)browser[- ]?automation|ich starte.*(browser|navigation)|api[- ]?keys?",
            raw,
        )
    )
    # Try to stash a concrete resume command for owner confirm
    hint = extract_browser_command_hint(user_input, raw)
    if hint:
        save_pending_browser_mission(
            hint,
            source="anti_hallucination",
            title=hint[:80],
        )

    if not action_like and not answer_browser_claim:
        # Soft scrub: remove fake-success sentences only
        cleaned = _FAKE_SUCCESS_RE.sub(
            "[Hinweis: Kein Tool-Lauf — Erfolg nicht verifiziert]",
            raw,
        )
        if hint:
            cleaned += (
                "\n\n[Pending] Browser-Mission vorgemerkt.\n"
                f"  Befehl: {hint}\n"
                "Zum Ausführen: **Ich bestätige**"
            )
        return cleaned

    honest = (
        "[Execution Contract] Kein Tool/Browser-Lauf mit Evidenz in diesem Turn.\n"
        "Ich behaupte keinen Login/Navigation-Erfolg ohne [Evidence]/Browser]-Block.\n"
        "Formuliere die Anfrage als Mission, z. B.:\n"
        "  • Browser: google.de login: user@x passwort: …\n"
        "  • Gehe auf hackerone und arbeite im Hintergrund an autorisierten Programmen\n"
        "  • Log dich bei Google ein login: … passwort: …\n"
    )
    if hint:
        honest += (
            f"\n[Pending] Vorgemerkte Mission:\n  {hint}\n"
            "Zum echten Start: **Ich bestätige**\n"
        )
    return honest


def anti_hallucination_system_note() -> str:
    return (
        "[Execution Contract — bindend]\n"
        "- Behaupte NIEMALS Browser-, Login-, Tool- oder Datei-Erfolg ohne echten Tool-Lauf.\n"
        "- Ohne [Browser]/[Evidence]/[Mission]-Block: kein „ich habe mich eingeloggt/geöffnet“.\n"
        "- Wenn Tools deaktiviert oder fehlgeschlagen: ehrlich sagen, was fehlt "
        "(browser_automation, Playwright, Free-Cloud-Limit).\n"
        "- Passwörter niemals wiederholen oder in Klartext loggen.\n"
        "- Bug-Bounty nur in autorisierten, in-scope Programmen; kein unautorisiertes Scannen.\n"
    )


# ── Mission store + background tick ───────────────────────────────────────────

class MissionStore:
    def __init__(self, path: Path = MISSIONS_PATH):
        self.path = path
        self.missions: dict[str, StoredMission] = {}
        self.load()

    def load(self) -> None:
        self.missions = {}
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            items = data.get("missions") if isinstance(data, dict) else data
            for item in items or []:
                if not isinstance(item, dict):
                    continue
                m = StoredMission.from_dict(item)
                if m.id:
                    self.missions[m.id] = m
        except Exception as exc:
            log.warning("MissionStore load failed: %s", exc)

    def save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "missions": [m.to_dict() for m in self.missions.values()],
                "updated_at": _now(),
            }
            self.path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            try:
                self.path.chmod(0o600)
            except OSError:
                pass
        except Exception as exc:
            log.warning("MissionStore save failed: %s", exc)

    def list_active(self) -> list[StoredMission]:
        return [m for m in self.missions.values() if m.status == "active"]

    def add(
        self,
        *,
        kind: str,
        title: str,
        target_url: str = "",
        login_user: str = "",
        goal_id: str = "",
        metadata: Optional[dict[str, Any]] = None,
    ) -> StoredMission:
        m = StoredMission(
            id=_new_id(),
            kind=kind,
            title=title[:200],
            status="active",
            goal_id=goal_id or "",
            target_url=target_url or "",
            login_user=login_user or "",
            created_at=_now(),
            updated_at=_now(),
            metadata=dict(metadata or {}),
        )
        self.missions[m.id] = m
        self.save()
        AuditLog.action("ExecutionContract", "mission_add", f"{m.id}:{m.kind}:{m.title[:60]}")
        return m

    def update(self, mission_id: str, **fields: Any) -> Optional[StoredMission]:
        m = self.missions.get(mission_id)
        if not m:
            return None
        for k, v in fields.items():
            if hasattr(m, k) and k != "id":
                setattr(m, k, v)
        m.updated_at = _now()
        self.missions[m.id] = m
        self.save()
        return m


_store: Optional[MissionStore] = None


def get_mission_store() -> MissionStore:
    global _store
    if _store is None:
        _store = MissionStore()
    return _store


def enqueue_mission_from_spec(
    spec: MissionSpec,
    *,
    goal_id: str = "",
) -> StoredMission:
    """Persist mission for background work (no password stored)."""
    store = get_mission_store()
    meta = dict(spec.metadata or {})
    meta["bounty_authorized_only"] = bool(spec.bounty_authorized_only)
    return store.add(
        kind=spec.kind,
        title=spec.title,
        target_url=spec.target_url,
        login_user=spec.login_user or "",
        goal_id=goal_id,
        metadata=meta,
    )


def ensure_goal_for_mission(spec: MissionSpec) -> str:
    """Create or reuse an owner goal for long-running missions. Returns goal_id."""
    try:
        from goal_store import get_goal_store

        store = get_goal_store()
        title = spec.title[:120]
        active = store.list_goals(status="active")
        for g in active or []:
            gt = (g.title or "").lower()
            if title.lower() == gt or title.lower() in gt:
                return g.id
            if spec.target_label and spec.target_label in gt:
                return g.id

        desc = (
            f"Owner-Mission: {spec.kind}. "
            f"Ziel-URL: {spec.target_url or '—'}. "
        )
        if spec.kind == KIND_BOUNTY_RESEARCH:
            desc += (
                "Nur autorisierte, in-scope Bug-Bounty-Programme. "
                "Kein unautorisiertes Scannen, kein Out-of-Scope-Test."
            )
        goal = store.add_owner_goal(
            title,
            description=desc,
            source="mission",
            owner_confirmed=True,
            priority=0.85 if spec.kind == KIND_BOUNTY_RESEARCH else 0.7,
        )
        return goal.id
    except Exception as exc:
        log.debug("ensure_goal_for_mission: %s", exc)
        return ""


async def run_mission_tick(
    *,
    on_note: Optional[Any] = None,
    browser_enabled: bool = True,
) -> dict[str, Any]:
    """Background tick: advance at most N active missions with real browser steps."""
    if not missions_enabled():
        return {"ok": True, "enabled": False, "advanced": []}

    store = get_mission_store()
    active = store.list_active()
    if not active:
        return {"ok": True, "enabled": True, "advanced": [], "active": 0}

    advanced: list[dict[str, Any]] = []
    cap = max_missions_per_tick()

    for mission in active[:cap]:
        result = await _advance_one_mission(
            mission,
            browser_enabled=browser_enabled,
            on_note=on_note,
        )
        advanced.append(result)

    return {
        "ok": True,
        "enabled": True,
        "active": len(active),
        "advanced": advanced,
    }


async def _advance_one_mission(
    mission: StoredMission,
    *,
    browser_enabled: bool,
    on_note: Optional[Any],
) -> dict[str, Any]:
    store = get_mission_store()
    mid = mission.id

    if not browser_enabled:
        evidence = format_evidence_block(
            source="mission_tick",
            ok=False,
            url=mission.target_url,
            error="browser_automation deaktiviert (Free-Cloud oder Runtime-Setting)",
        )
        store.update(mid, last_evidence=evidence, last_error="browser_disabled")
        note = f"[Mission] {mission.title[:50]}: Browser aus — warte."
        if on_note:
            on_note(note)
        try:
            from owner_notify import OwnerBlocker, KIND_BROWSER_DISABLED, notify_owner_blocker
            await notify_owner_blocker(
                OwnerBlocker(
                    kind=KIND_BROWSER_DISABLED,
                    title=f"Mission blockiert: {mission.title[:60]}",
                    detail="Browser-Automation aus — Isaac kann die Mission nicht fortsetzen.",
                    need="enable_browser_or_local_runtime",
                    mission_id=mid,
                    goal_id=mission.goal_id,
                    source="mission_tick",
                    cooldown_key=f"browser_disabled|{mid}",
                ),
                on_note=on_note,
            )
        except Exception as exc:
            log.debug("owner_notify mission browser: %s", exc)
        return {"id": mid, "ok": False, "error": "browser_disabled"}

    if not mission.target_url:
        store.update(mid, status="failed", last_error="no_target_url")
        try:
            from owner_notify import OwnerBlocker, KIND_MISSING_TARGET, notify_owner_blocker
            await notify_owner_blocker(
                OwnerBlocker(
                    kind=KIND_MISSING_TARGET,
                    title=f"Mission ohne Ziel-URL: {mission.title[:60]}",
                    detail="Isaac braucht eine konkrete URL/Zielseite vom Owner.",
                    need="url_or_target",
                    mission_id=mid,
                    goal_id=mission.goal_id,
                    source="mission_tick",
                ),
                on_note=on_note,
            )
        except Exception as exc:
            log.debug("owner_notify missing target: %s", exc)
        return {"id": mid, "ok": False, "error": "no_target_url"}

    # Safety: bounty missions stay navigate/extract only unless explicit flow
    try:
        from browser import get_browser

        browser = get_browser()
        actions: list[dict[str, Any]] = [
            {"action": "goto", "url": mission.target_url},
            {
                "action": "extract_text",
                "selector": "body",
                "save_as": "page_text",
            },
        ]
        # Login attempt only if credentials already stored for domain
        result = await browser.run_flow(
            f"mission-{mid}",
            mission.target_url,
            actions,
            name=mission.title[:60] or mid,
        )
        ok = bool(result.get("ok"))
        excerpt = (result.get("memory") or {}).get("page_text", "")[:2000]
        evidence = format_evidence_block(
            source="mission_tick",
            ok=ok,
            url=mission.target_url,
            current_url=str(result.get("current_url") or ""),
            steps=result.get("steps") or [],
            excerpt=excerpt if ok else "",
            error=str(result.get("error") or ""),
            extra_lines=[
                f"mission_id={mid}",
                f"kind={mission.kind}",
                f"step={mission.steps_done + 1}",
            ],
        )
        store.update(
            mid,
            steps_done=mission.steps_done + 1,
            last_evidence=evidence[:4000],
            last_error="" if ok else str(result.get("error") or "flow_failed")[:300],
        )
        # After first successful open of bounty hub, leave active for further ticks
        # but don't spam forever: pause after 5 successful extracts without new owner input
        m2 = store.missions.get(mid)
        if m2 and m2.steps_done >= 5:
            store.update(mid, status="paused", last_error="step_cap_wait_owner")
            try:
                from owner_notify import OwnerBlocker, KIND_MISSION_STUCK, notify_owner_blocker
                await notify_owner_blocker(
                    OwnerBlocker(
                        kind=KIND_MISSION_STUCK,
                        title=f"Mission wartet auf dich: {mission.title[:60]}",
                        detail=(
                            "Isaac hat mehrere Browser-Schritte gemacht und pausiert. "
                            "Nächste Credentials/Keys/URLs oder Anweisung im Chat geben."
                        ),
                        need="owner_decision_or_data",
                        mission_id=mid,
                        goal_id=mission.goal_id,
                        source="mission_tick",
                        cooldown_key=f"mission_step_cap|{mid}",
                    ),
                    on_note=on_note,
                )
            except Exception as exc:
                log.debug("owner_notify step_cap: %s", exc)

        # Hard fail with login/credential hints → push once
        if not ok:
            err_l = str(result.get("error") or "").lower()
            excerpt_l = (excerpt or "").lower()
            blob = f"{err_l}\n{excerpt_l}"
            try:
                from owner_notify import maybe_notify_from_text
                await maybe_notify_from_text(
                    blob,
                    source="mission_tick",
                    mission_id=mid,
                    goal_id=mission.goal_id,
                    on_note=on_note,
                )
            except Exception as exc:
                log.debug("owner_notify fail infer: %s", exc)

        note = (
            f"[Mission] {mission.title[:40]} step={mission.steps_done + 1} "
            f"ok={ok} url={result.get('current_url') or mission.target_url}"
        )
        if on_note:
            on_note(note)
        AuditLog.action(
            "ExecutionContract",
            "mission_tick",
            f"{mid} ok={ok} steps={mission.steps_done + 1}",
            erfolg=ok,
        )
        # Bind outcome to goal if present
        if mission.goal_id and ok:
            try:
                from goal_store import get_goal_store

                gs = get_goal_store()
                # light touch: log via memory if available
                from memory import get_memory

                get_memory().log_development_event(
                    event_type="mission_tick",
                    target_kind="owner_goal",
                    target_key=mission.goal_id,
                    reason=f"mission {mid} step ok",
                    confidence_after=0.5,
                    metadata={"mission_id": mid, "url": result.get("current_url")},
                )
            except Exception:
                pass
        return {"id": mid, "ok": ok, "evidence_len": len(evidence)}
    except Exception as exc:
        err = str(exc)[:300]
        evidence = format_evidence_block(
            source="mission_tick",
            ok=False,
            url=mission.target_url,
            error=err,
        )
        store.update(mid, last_evidence=evidence, last_error=err)
        if on_note:
            on_note(f"[Mission] {mission.title[:40]} Fehler: {err[:80]}")
        return {"id": mid, "ok": False, "error": err}


def format_mission_accept(spec: MissionSpec, *, mission_id: str = "", goal_id: str = "") -> str:
    lines = [
        f"[Mission] Angenommen: {spec.title}",
        f"kind={spec.kind}",
    ]
    if spec.target_url:
        lines.append(f"target={spec.target_url}")
    if spec.login_user:
        lines.append(f"login_user={spec.login_user}")
    if mission_id:
        lines.append(f"mission_id={mission_id}")
    if goal_id:
        lines.append(f"goal_id={goal_id}")
    if spec.kind == KIND_BOUNTY_RESEARCH:
        lines.append(
            "policy=authorized_programs_only — kein unautorisiertes Scannen / Out-of-Scope"
        )
    if spec.wants_background:
        lines.append("background=yes — Hintergrund-Ticks führen weitere Schritte aus")
    return "\n".join(lines)
