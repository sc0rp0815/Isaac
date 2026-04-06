"""
Isaac – Browser-Automation (Playwright)
=========================================
Kernstück des Multi-Instanz-Modus.

Jede KI-Instanz = eine URL = ein isolierter Browser-Context.
Isaac navigiert zu den URLs, loggt sich ein, schickt Nachrichten
und liest Antworten aus — wie ein Mensch, aber automatisiert.

Architektur:
  BrowserManager        → verwaltet alle Instanzen
  KIInstance            → eine KI-Chat-Session (ein Browser-Context)
  LoginProfile          → gespeicherte Login-Daten pro Domain
  SiteAdapter           → URL-spezifische Selektoren (erweiterbar)

Instanzen sind vollständig isoliert:
  - Eigene Cookies / Sessions
  - Eigene LocalStorage
  - Kein Cross-Contamination zwischen Instanzen

Auto-Login:
  - Credentials in encrypted local store
  - Pro Domain: Username, Passwort, Login-URL, Selektoren
  - Wird beim Start automatisch durchgeführt
"""

import asyncio
import json
import time
import logging
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional, Callable

from config  import get_config, DATA_DIR
from audit   import AuditLog
from privilege import get_gate, isaac_ctx

log = logging.getLogger("Isaac.Browser")

# Credentials-Datei (verschlüsselt gespeichert)
CREDS_PATH = DATA_DIR / "browser_creds.json"


# ── Login-Profil ───────────────────────────────────────────────────────────────
@dataclass
class LoginProfile:
    domain:        str
    login_url:     str
    username:      str
    password:      str   # Wird verschlüsselt gespeichert
    user_selector: str   = "input[type='email'], input[name='email'], input[name='username']"
    pass_selector: str   = "input[type='password']"
    submit_selector: str = "button[type='submit'], input[type='submit']"
    logged_in_check: str = ""  # CSS-Selector der nach Login sichtbar ist
    extra_steps:   list  = field(default_factory=list)  # Für 2FA etc.


# ── Site-Adapter ──────────────────────────────────────────────────────────────
# Bekannte KI-Chat-Seiten: URL-Pattern → Chat-Selektoren
SITE_ADAPTERS: dict[str, dict] = {
    "chat.openai.com": {
        "input":    "#prompt-textarea",
        "send":     "button[data-testid='send-button']",
        "response": "[data-message-author-role='assistant']:last-child",
        "wait_ms":  3000,
    },
    "claude.ai": {
        "input":    "div[contenteditable='true']",
        "send":     "button[aria-label='Send message']",
        "response": "[data-is-streaming='false']:last-child",
        "wait_ms":  5000,
    },
    "gemini.google.com": {
        "input":    "rich-textarea",
        "send":     "button.send-button",
        "response": "model-response:last-child .response-content",
        "wait_ms":  4000,
    },
    "copilot.microsoft.com": {
        "input":    "#userInput",
        "send":     "button#sendButton",
        "response": ".ac-textBlock:last-child",
        "wait_ms":  5000,
    },
    "huggingface.co": {
        "input":    "textarea",
        "send":     "button[type='submit']",
        "response": ".message.bot:last-child",
        "wait_ms":  4000,
    },
    "poe.com": {
        "input":    "textarea[class*='GrowingTextArea']",
        "send":     "button[class*='SendButton']",
        "response": "[class*='Message_humanMessageBubble']:last-child",
        "wait_ms":  4000,
    },
    "you.com": {
        "input":    "textarea[placeholder*='Ask']",
        "send":     "button[aria-label='Submit']",
        "response": "[data-testid='youchat-text']:last-child",
        "wait_ms":  5000,
    },
    "perplexity.ai": {
        "input":    "textarea",
        "send":     "button[aria-label='Submit']",
        "response": ".prose:last-child",
        "wait_ms":  6000,
    },
    "mistral.ai": {
        "input":    "textarea",
        "send":     "button[type='submit']",
        "response": ".assistant-message:last-child",
        "wait_ms":  4000,
    },
    "groq.com": {
        "input":    "textarea",
        "send":     "button[aria-label='Send']",
        "response": ".message-content:last-child",
        "wait_ms":  3000,
    },
    # Fallback für unbekannte Sites
    "_default": {
        "input":    "textarea, input[type='text']",
        "send":     "button[type='submit'], button:last-child",
        "response": "main p:last-child, .response:last-child, .message:last-child",
        "wait_ms":  5000,
    },
}


def get_adapter(url: str) -> dict:
    for domain, adapter in SITE_ADAPTERS.items():
        if domain != "_default" and domain in url:
            return adapter
    return SITE_ADAPTERS["_default"]


# ── KI-Instanz ────────────────────────────────────────────────────────────────
@dataclass
class KIInstance:
    id:         str
    url:        str
    name:       str
    aktiv:      bool  = False
    eingeloggt: bool  = False
    fehler:     int   = 0
    letzter_einsatz: float = 0.0
    antworten:  int   = 0
    avg_latenz: float = 0.0
    context     = None   # playwright BrowserContext
    page        = None   # playwright Page

    def to_dict(self) -> dict:
        return {
            "id":        self.id,
            "url":       self.url,
            "name":      self.name,
            "aktiv":     self.aktiv,
            "eingeloggt": self.eingeloggt,
            "fehler":    self.fehler,
            "antworten": self.antworten,
            "avg_latenz": round(self.avg_latenz, 2),
        }

    def update_latenz(self, sek: float):
        n = self.antworten + 1
        self.avg_latenz = (self.avg_latenz * self.antworten + sek) / n
        self.antworten  = n


# ── Browser-Manager ───────────────────────────────────────────────────────────
class BrowserManager:
    """
    Verwaltet alle KI-Browser-Instanzen.

    Beim Start:
      1. Playwright initialisieren
      2. Für jede konfigurierte URL: Browser-Context erstellen
      3. Auto-Login wenn Credentials vorhanden
      4. Instanzen als "bereit" markieren

    Dispatcher nutzt dann ask_instance() oder broadcast().
    """

    def __init__(self):
        self.cfg        = get_config()
        self._instances: dict[str, KIInstance] = {}
        self._pw        = None    # playwright instance
        self._browser   = None   # chromium browser
        self._creds:    dict[str, LoginProfile] = {}
        self._bereit    = False
        self._lock      = asyncio.Lock()
        self._load_creds()
        log.info("BrowserManager initialisiert")

    # ── Startup ───────────────────────────────────────────────────────────────
    async def start(self, urls: list[dict]):
        """
        urls = [{"id": "claude1", "url": "https://claude.ai", "name": "Claude #1"}, ...]
        """
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            log.error(
                "Playwright nicht installiert!\n"
                "Installiere mit: pip install playwright && playwright install chromium"
            )
            return

        log.info(f"Browser startet mit {len(urls)} Instanzen...")
        self._pw      = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(
            headless      = self.cfg.browser.headless,
            slow_mo       = self.cfg.browser.slowmo,
            args          = [
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
            ]
        )

        # Instanzen sequentiell erstellen (nicht alle gleichzeitig)
        for ui in urls:
            try:
                inst = await self._create_instance(ui)
                self._instances[inst.id] = inst
                await asyncio.sleep(1.5)   # Sanfter Start
            except Exception as e:
                log.error(f"Instanz {ui.get('id')} fehlgeschlagen: {e}")

        self._bereit = True
        log.info(
            f"BrowserManager bereit │ "
            f"{len([i for i in self._instances.values() if i.aktiv])} Instanzen aktiv"
        )

    async def _create_instance(self, ui: dict) -> KIInstance:
        inst = KIInstance(
            id   = ui["id"],
            url  = ui["url"],
            name = ui.get("name", ui["id"]),
        )

        # Isolierter Context (eigene Cookies, Session, Storage)
        inst.context = await self._browser.new_context(
            viewport         = {"width": 1280, "height": 900},
            user_agent       = (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            java_script_enabled = True,
            ignore_https_errors = True,
        )
        inst.page = await inst.context.new_page()

        # Automation-Detection deaktivieren
        await inst.page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            window.chrome = {runtime: {}};
        """)

        # Zur URL navigieren
        log.info(f"Instanz {inst.id}: Lade {inst.url}")
        try:
            await inst.page.goto(inst.url, wait_until="networkidle", timeout=30000)
            inst.aktiv = True
        except Exception as e:
            log.warning(f"Instanz {inst.id}: Navigation fehlgeschlagen: {e}")
            inst.fehler += 1

        # Auto-Login versuchen
        if inst.aktiv:
            await self._auto_login(inst)

        AuditLog.instance(inst.id, "created", detail=inst.url)
        return inst

    # ── Auto-Login ─────────────────────────────────────────────────────────────
    async def _auto_login(self, inst: KIInstance):
        """Loggt sich automatisch ein wenn Credentials vorhanden."""
        from urllib.parse import urlparse
        domain = urlparse(inst.url).netloc

        cred = self._creds.get(domain) or self._creds.get(
            domain.replace("www.", "")
        )
        if not cred:
            log.debug(f"Keine Credentials für {domain}")
            return

        log.info(f"Auto-Login: {inst.id} @ {domain}")
        try:
            # Login-Seite aufrufen
            await inst.page.goto(cred.login_url, wait_until="networkidle",
                                 timeout=20000)
            await asyncio.sleep(1.5)

            # Username eingeben
            try:
                await inst.page.fill(cred.user_selector, cred.username)
                await asyncio.sleep(0.5)
            except Exception:
                log.warning(f"Username-Feld nicht gefunden: {cred.user_selector}")

            # Passwort eingeben
            try:
                await inst.page.fill(cred.pass_selector, cred.password)
                await asyncio.sleep(0.5)
            except Exception:
                log.warning(f"Passwort-Feld nicht gefunden")

            # Absenden
            try:
                await inst.page.click(cred.submit_selector)
                await inst.page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                log.warning(f"Submit fehlgeschlagen")

            # Erfolg prüfen
            await asyncio.sleep(2)
            if cred.logged_in_check:
                try:
                    await inst.page.wait_for_selector(
                        cred.logged_in_check, timeout=8000
                    )
                    inst.eingeloggt = True
                    log.info(f"✓ Login {inst.id} @ {domain}")
                except Exception:
                    log.warning(f"Login-Check fehlgeschlagen: {inst.id}")
            else:
                # Kein Check-Selector → Annahme: OK wenn kein Error
                inst.eingeloggt = True
                log.info(f"✓ Login {inst.id} @ {domain} (kein Check)")

            # Zurück zur Chat-URL
            if inst.url != cred.login_url:
                await inst.page.goto(inst.url, wait_until="networkidle",
                                     timeout=20000)

            AuditLog.instance(inst.id, "logged_in", detail=domain)

        except Exception as e:
            log.error(f"Auto-Login fehlgeschlagen {inst.id}: {e}")
            AuditLog.error("Browser", f"Login {inst.id}", str(e)[:100])

    # ── Nachricht senden ───────────────────────────────────────────────────────
    async def ask_instance(self, instance_id: str,
                           prompt: str,
                           timeout: float = 60.0) -> str:
        """
        Schickt einen Prompt an eine KI-Instanz per Browser.
        Gibt die Antwort als Text zurück.
        """
        inst = self._instances.get(instance_id)
        if not inst or not inst.aktiv:
            return f"[Browser] Instanz {instance_id} nicht verfügbar"

        async with self._lock:
            t0 = time.monotonic()
            try:
                adapter = get_adapter(inst.url)
                page    = inst.page

                # Input-Feld finden und füllen
                await page.wait_for_selector(
                    adapter["input"], timeout=10000
                )

                # Eingabe simulieren (menschlich)
                await page.click(adapter["input"])
                await asyncio.sleep(0.3)

                # Text schrittweise eingeben (weniger detektierbar)
                await page.fill(adapter["input"], "")
                await page.type(adapter["input"], prompt, delay=15)
                await asyncio.sleep(0.5)

                # Senden (Enter oder Button)
                try:
                    await page.click(adapter["send"], timeout=3000)
                except Exception:
                    await page.keyboard.press("Enter")

                # Auf Antwort warten
                await asyncio.sleep(adapter["wait_ms"] / 1000)

                # Antwort lesen
                antwort = await self._extract_response(page, adapter, timeout)

                latenz = time.monotonic() - t0
                inst.update_latenz(latenz)
                inst.letzter_einsatz = time.monotonic()

                AuditLog.instance(instance_id, "answered",
                                  detail=f"{len(antwort.split())} Wörter")
                return antwort

            except Exception as e:
                inst.fehler += 1
                log.error(f"Instanz {instance_id}: {e}")
                AuditLog.error("Browser", f"ask:{instance_id}", str(e)[:100])

                # Neustart versuchen wenn zu viele Fehler
                if inst.fehler >= self.cfg.browser.max_errors_per_instance:
                    await self._restart_instance(inst)
                return f"[Browser-Fehler:{instance_id}] {e}"

    async def _extract_response(self, page, adapter: dict,
                                 timeout: float) -> str:
        """Wartet und extrahiert die KI-Antwort."""
        deadline = time.monotonic() + timeout
        selector = adapter["response"]

        while time.monotonic() < deadline:
            try:
                # Auf Response-Element warten
                el = await page.wait_for_selector(selector, timeout=5000)
                if el:
                    text = await el.inner_text()
                    if text and len(text.strip()) > 10:
                        # Prüfen ob noch gestreamt wird
                        await asyncio.sleep(1.5)
                        text2 = await el.inner_text()
                        if text == text2:   # Stabil → fertig
                            return text.strip()
            except Exception:
                pass
            await asyncio.sleep(1.0)

        # Fallback: letzten sichtbaren Text nehmen
        try:
            text = await page.inner_text("body")
            # Nur letzten Teil (Antwort ist meist am Ende)
            return text[-2000:].strip()
        except Exception:
            return "[Keine Antwort extrahiert]"

    # ── Broadcast ─────────────────────────────────────────────────────────────
    async def broadcast(self, prompt: str,
                        instance_ids: Optional[list] = None,
                        stagger_ms: int = 1500) -> dict[str, str]:
        """
        Sendet einen Prompt an mehrere Instanzen.
        Mit konfigurierbarer Latenz zwischen Anfragen (kein Ban-Risiko).
        """
        ids = instance_ids or [
            i.id for i in self._instances.values() if i.aktiv
        ]

        ergebnisse = {}
        tasks      = []

        for i, iid in enumerate(ids):
            # Stagger: jede Anfrage mit Verzögerung starten
            delay = (i * stagger_ms) / 1000.0
            tasks.append(self._delayed_ask(iid, prompt, delay))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        for iid, result in zip(ids, results):
            if isinstance(result, Exception):
                ergebnisse[iid] = f"[Fehler: {result}]"
            else:
                ergebnisse[iid] = result

        return ergebnisse

    async def _delayed_ask(self, iid: str, prompt: str,
                           delay: float) -> str:
        await asyncio.sleep(delay)
        return await self.ask_instance(iid, prompt)

    # ── Instanz neustarten ────────────────────────────────────────────────────
    async def _restart_instance(self, inst: KIInstance):
        log.warning(f"Neustart: {inst.id}")
        try:
            if inst.context:
                await inst.context.close()
            inst.fehler  = 0
            inst.aktiv   = False
            inst.context = await self._browser.new_context(
                viewport={"width": 1280, "height": 900}
            )
            inst.page = await inst.context.new_page()
            await inst.page.goto(inst.url, wait_until="networkidle",
                                 timeout=30000)
            inst.aktiv = True
            await self._auto_login(inst)
            AuditLog.instance(inst.id, "restarted")
        except Exception as e:
            log.error(f"Neustart {inst.id} fehlgeschlagen: {e}")

    # ── Credentials verwalten ─────────────────────────────────────────────────
    def add_credential(self, domain: str, login_url: str,
                       username: str, password: str,
                       logged_in_check: str = "") -> bool:
        """Fügt Login-Daten für eine Domain hinzu."""
        self._creds[domain] = LoginProfile(
            domain          = domain,
            login_url       = login_url,
            username        = username,
            password        = password,
            logged_in_check = logged_in_check,
        )
        self._save_creds()
        log.info(f"Credentials gespeichert: {domain}")
        return True

    def remove_credential(self, domain: str):
        self._creds.pop(domain, None)
        self._save_creds()

    def _load_creds(self):
        if not CREDS_PATH.exists():
            return
        try:
            data = json.loads(CREDS_PATH.read_text())
            for domain, d in data.items():
                self._creds[domain] = LoginProfile(**d)
            log.info(f"Credentials geladen: {len(self._creds)} Domains")
        except Exception as e:
            log.warning(f"Credentials laden: {e}")

    def _save_creds(self):
        try:
            CREDS_PATH.parent.mkdir(parents=True, exist_ok=True)
            data = {k: asdict(v) for k, v in self._creds.items()}
            CREDS_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False))
            # Nur Owner-Zugriff
            import stat
            CREDS_PATH.chmod(stat.S_IRUSR | stat.S_IWUSR)
        except Exception as e:
            log.warning(f"Credentials speichern: {e}")

    # ── Status ────────────────────────────────────────────────────────────────
    def add_url(self, url_config: dict):
        """Fügt eine neue URL-Konfiguration hinzu (dynamisch)."""
        # Wird beim nächsten start() oder manuell initiiert
        self._pending_urls = getattr(self, "_pending_urls", [])
        self._pending_urls.append(url_config)

    def list_instances(self) -> list[dict]:
        return [i.to_dict() for i in self._instances.values()]

    def get_active_ids(self) -> list[str]:
        return [i.id for i in self._instances.values() if i.aktiv]

    def stats(self) -> dict:
        inst = list(self._instances.values())
        return {
            "total":     len(inst),
            "aktiv":     sum(1 for i in inst if i.aktiv),
            "eingeloggt": sum(1 for i in inst if i.eingeloggt),
            "bereit":    self._bereit,
            "creds":     len(self._creds),
        }

    async def close(self):
        for inst in self._instances.values():
            try:
                if inst.context:
                    await inst.context.close()
            except Exception:
                pass
        if self._browser:
            await self._browser.close()
        if self._pw:
            await self._pw.stop()
        log.info("BrowserManager geschlossen")


# ── Singleton ─────────────────────────────────────────────────────────────────
_browser_mgr: Optional[BrowserManager] = None

def get_browser() -> BrowserManager:
    global _browser_mgr
    if _browser_mgr is None:
        _browser_mgr = BrowserManager()
    return _browser_mgr
