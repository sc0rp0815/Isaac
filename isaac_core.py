"""
Isaac – Kernel v5.3
=====================
Zentraler Orchestrator. Alle 21 Module vollständig integriert.

Pipeline pro Steffen-Input:
  1. SUDO-Check
  2. Empathie-Analyse (Node-Zustand)
  3. Wissensdatenbank konsultieren (KI-Dialog-DB)
  4. Intent erkennen
  5. Komplexitäts-Routing:
       - Einfach  → Standard-Task
       - Komplex  → Decomposer (Steffens Prompt nie direkt extern)
       - Multi-KI → Dispatcher (Broadcast / Split / Pipeline)
  6. Regelwerk analysiert jede Interaktion
  7. Offene Fragen des Regelwerks stellen
  8. Background-Erkenntnisse einbauen
  9. Gedächtnis schreiben + Dashboard pushen

Datenschutz-Garantie:
  Steffens originaler Prompt wird NIEMALS direkt an externe KIs gesendet.
  Der Decomposer atomisiert jeden Prompt bevor er externe Instanzen erreicht.
"""

import asyncio
import re
import time
import logging
from typing import Optional

from config         import get_config, Level, WORKSPACE
from privilege      import get_gate, steffen_ctx, isaac_ctx
from audit          import AuditLog, setup_privilege_audit
from memory         import get_memory
from executor       import get_executor, TaskType, TaskStatus
from relay          import get_relay
from logic          import get_logic
from empathie       import get_empathie
from sudo_gate      import get_sudo
from regelwerk      import get_regelwerk
from decomposer     import get_decomposer
from ki_dialog      import get_ki_dialog
from ki_skills      import get_skill_router
from monitor_server import get_monitor, set_kernel, DashboardHTTPServer
from meaning        import get_meaning
from values         import get_values

log = logging.getLogger("Isaac.Kernel")

# ── Komplexitätsschwelle für Decomposer ───────────────────────────────────────
DECOMPOSE_WORT_SCHWELLE = 15   # Ab 15 Wörtern → Decomposer
DECOMPOSE_THEMEN_SCHWELLE = 2  # Ab 2 erkennbaren Themen → Decomposer


# ── Intents ────────────────────────────────────────────────────────────────────
class Intent:
    CHAT        = "chat"
    SEARCH      = "search"
    CODE        = "code"
    FILE        = "file"
    TRANSLATE   = "translate"
    BROADCAST   = "broadcast"
    SPLIT       = "split"
    PIPELINE    = "pipeline"
    DECOMPOSE   = "decompose"   # Explizite Atomisierung
    FACT_SET    = "fact_set"
    DIRECTIVE   = "directive"
    STATUS      = "status"
    KI_STATUS   = "ki_status"   # KI-Dialog + Skill-Übersicht
    MEINUNG     = "meinung"     # Isaac's Meinung zu einem Thema
    PAUSE       = "pause"
    RESUME      = "resume"
    CANCEL      = "cancel"
    SUDO_OPEN   = "sudo_open"
    SUDO_CLOSE  = "sudo_close"
    LOGIN_ADD   = "login_add"
    URL_ADD     = "url_add"


PATTERNS = [
    (Intent.SUDO_OPEN,  [r"^sudo\s+", r"^öffne tür", r"^master key"]),
    (Intent.SUDO_CLOSE, [r"^sudo close$", r"^tür schließen$"]),
    (Intent.FACT_SET,   [r"^korrektur:", r"^fakt:", r"^weiß:"]),
    (Intent.DIRECTIVE,  [r"^direktive:", r"^immer:", r"^niemals:"]),
    (Intent.SEARCH,     [r"^suche:", r"^recherchier", r"^finde.*internet", r"^search:"]),
    (Intent.BROADCAST,  [r"^broadcast:", r"^alle instanzen:", r"^frage alle"]),
    (Intent.SPLIT,      [r"^split:", r"^aufteilen:"]),
    (Intent.PIPELINE,   [r"^pipeline:", r"^verbessere iterativ"]),
    (Intent.DECOMPOSE,  [r"^atomisiere:", r"^verteile:"]),
    (Intent.CODE,       [r"^code:", r"^programmiere:", r"^schreibe.*python"]),
    (Intent.FILE,       [r"^datei:", r"^lese:", r"^schreibe.*datei"]),
    (Intent.TRANSLATE,  [r"übersetze", r"^schrift:", r"alphabet"]),
    (Intent.LOGIN_ADD,  [r"^login:", r"^credential:", r"^zugangsdaten:"]),
    (Intent.URL_ADD,    [r"^url:", r"^instanz:", r"^füge.*url"]),
    (Intent.KI_STATUS,  [r"^ki status$", r"^instanzen$", r"^meinungen$"]),
    (Intent.MEINUNG,    [r"^meinung:", r"^was denkst du über", r"^isaac.*meinung"]),
    (Intent.STATUS,     [r"^status$", r"^info$", r"^hilfe$"]),
    (Intent.PAUSE,      [r"^pause$", r"^stopp$"]),
    (Intent.RESUME,     [r"^weiter$", r"^fortsetzen$"]),
    (Intent.CANCEL,     [r"^abbrechen\s+\w+"]),
]


def detect_intent(text: str) -> str:
    tl = text.lower().strip()
    for intent, patterns in PATTERNS:
        for pat in patterns:
            if re.search(pat, tl):
                return intent
    return Intent.CHAT


def braucht_decomposer(text: str, intent: str) -> bool:
    """Entscheidet ob ein Prompt atomisiert werden soll."""
    if intent in (Intent.CODE, Intent.FILE, Intent.SEARCH,
                  Intent.BROADCAST, Intent.SPLIT, Intent.PIPELINE,
                  Intent.DECOMPOSE):
        return False   # Eigene Handler
    wortanzahl = len(text.split())
    und_count  = len(re.findall(r'\s+(?:und|sowie|außerdem|auch)\s+',
                                text, re.I))
    return wortanzahl >= DECOMPOSE_WORT_SCHWELLE or und_count >= DECOMPOSE_THEMEN_SCHWELLE


# ── Kernel ─────────────────────────────────────────────────────────────────────
class IsaacKernel:

    VERSION = "5.3"

    def __init__(self):
        log.info("=" * 56)
        log.info(f"  ISAAC v{self.VERSION} – Unified OS Startup")
        log.info("=" * 56)

        setup_privilege_audit()

        self.cfg        = get_config()
        self.gate       = get_gate()
        self.memory     = get_memory()
        self.executor   = get_executor()
        self.relay      = get_relay()
        self.logic      = get_logic()
        self.empathie   = get_empathie()
        self.sudo       = get_sudo()
        self.regelwerk  = get_regelwerk()
        self.decomposer = get_decomposer()
        self.ki_dialog  = get_ki_dialog()
        self.skill_router = get_skill_router()
        self.monitor    = get_monitor()
        self.meaning    = get_meaning()
        self.values     = get_values()
        self._background = None   # lazy start in main()

        set_kernel(self)
        self._sudo_token: Optional[str] = None

        log.info(f"  Owner:      {self.cfg.owner_name}")
        log.info(f"  Provider:   {', '.join(self.cfg.available_providers)}")
        log.info(f"  Regelwerk:  {self.regelwerk.status()['regeln_aktiv']} Regeln")
        log.info(f"  KI-Dialog:  {self.ki_dialog.stats()['gespraeche']} Gespräche, "
                 f"{self.ki_dialog.stats()['wissenseintraege']} Wissenseinträge")
        log.info(f"  SUDO:       {'Ersteinrichtung' if self.sudo.is_first_run() else 'Bereit'}")
        AuditLog.action("Kernel", "startup", f"v{self.VERSION}", Level.ISAAC)

    # ── Haupt-Verarbeitung ────────────────────────────────────────────────────
    async def process(self, user_input: str,
                      sudo_token: Optional[str] = None) -> str:
        if not user_input.strip():
            return ""

        t0 = time.monotonic()

        # SUDO-Status
        sudo_aktiv = (
            (sudo_token and self.sudo.check(sudo_token)) or
            (self._sudo_token and self.sudo.check(self._sudo_token))
        )

        AuditLog.steffen_input(user_input)

        # 1. Empathie
        emp = self.empathie.analysiere(user_input)

        # 2. Wissensdatenbank konsultieren
        wissen_kontext = self.ki_dialog.als_kontext(user_input)

        # 3. Intent
        intent = detect_intent(user_input)

        log.info(
            f"Input: '{user_input[:50]}' │ Intent: {intent} │ "
            f"Node: {emp.node.zustand} │ Sudo: {sudo_aktiv}"
        )

        # SUDO-Handshake
        if intent == Intent.SUDO_OPEN:
            return self._handle_sudo_open(user_input)
        if intent == Intent.SUDO_CLOSE:
            return self._handle_sudo_close()

        # Pause
        if self.gate.is_paused and not sudo_aktiv:
            return "[Isaac] Pausiert. 'weiter' oder SUDO zum Fortfahren."

        # Direkte Handler (kein Task nötig)
        direkt = {
            Intent.FACT_SET:   self._handle_fact,
            Intent.DIRECTIVE:  self._handle_directive,
            Intent.STATUS:     self._handle_status,
            Intent.KI_STATUS:  self._handle_ki_status,
            Intent.MEINUNG:    self._handle_meinung,
            Intent.PAUSE:      self._handle_pause,
            Intent.RESUME:     self._handle_resume,
            Intent.CANCEL:     self._handle_cancel,
            Intent.LOGIN_ADD:  self._handle_login_add,
            Intent.URL_ADD:    self._handle_url_add,
        }
        if intent in direkt:
            result = direkt[intent](user_input)
            if asyncio.iscoroutine(result):
                result = await result
            return self._post_process(user_input, result, emp, 0.0, t0)

        # 4. Routing: Decomposer vs Standard vs Multi-KI
        antwort, score = await self._route(
            user_input, intent, sudo_aktiv, emp, wissen_kontext
        )

        return self._post_process(user_input, antwort, emp, score, t0)

    # ── Routing ────────────────────────────────────────────────────────────────
    async def _route(self, user_input: str, intent: str,
                     sudo_aktiv: bool, emp, wissen_kontext: str
                     ) -> tuple[str, float]:
        """
        Entscheidet welcher Pfad genutzt wird:
          A) Decomposer  — komplexe Prompts, mehrere Themen
          B) Multi-KI    — expliziter Broadcast/Split/Pipeline
          C) Standard    — einfache Tasks
        """
        from browser import get_browser
        aktive_instanzen = get_browser().get_active_ids()

        # B) Multi-KI explizit
        if intent in (Intent.BROADCAST, Intent.SPLIT, Intent.PIPELINE,
                      Intent.DECOMPOSE):
            return await self._multi_ki_route(
                user_input, intent, aktive_instanzen, emp, sudo_aktiv
            )

        # A) Automatischer Decomposer bei Komplexität
        if (aktive_instanzen and
                braucht_decomposer(user_input, intent) and
                not sudo_aktiv):   # Bei SUDO: direkt, keine Verzögerung
            log.info(f"Decomposer: '{user_input[:40]}...'")
            result = await self.decomposer.decompose_and_execute(
                user_input, aktive_instanzen
            )
            return result.final, 7.0   # Decomposer-Ergebnisse gelten als gut

        # C) Standard-Task
        return await self._standard_task(
            user_input, intent, sudo_aktiv, emp, wissen_kontext
        )

    async def _multi_ki_route(self, user_input: str, intent: str,
                               instanzen: list, emp, sudo_aktiv: bool
                               ) -> tuple[str, float]:
        from dispatcher import get_dispatcher
        dispatcher = get_dispatcher()
        system     = self._build_system(sudo_aktiv, emp)

        if not instanzen:
            instanzen = self.cfg.available_providers[:4]

        if intent in (Intent.DECOMPOSE, Intent.SPLIT):
            r = await dispatcher.split(user_input, instanzen, system=system)
        elif intent == Intent.PIPELINE:
            r = await dispatcher.pipeline(user_input, instanzen, system=system)
        else:   # BROADCAST
            r = await dispatcher.broadcast(user_input, instanzen, system=system)

        return r.final, r.ergebnisse[0].score if r.ergebnisse else 6.0

    async def _standard_task(self, user_input: str, intent: str,
                              sudo_aktiv: bool, emp, wissen_kontext: str
                              ) -> tuple[str, float]:
        typ_map = {
            Intent.SEARCH:    TaskType.SEARCH,
            Intent.CODE:      TaskType.CODE,
            Intent.FILE:      TaskType.FILE,
            Intent.TRANSLATE: TaskType.TRANSLATE,
            Intent.CHAT:      TaskType.CHAT,
        }
        task_typ = typ_map.get(intent, TaskType.CHAT)
        system   = self._build_system(sudo_aktiv, emp, wissen_kontext)
        provider = self._provider_hint(user_input)

        # Gedächtnis-Kontext
        kontext  = self.memory.build_context(user_input)
        prompt   = f"{kontext}\n\n{user_input}".strip() if kontext else user_input

        task = self.executor.create_task(
            typ           = task_typ,
            prompt        = prompt,
            beschreibung  = user_input[:80],
            prioritaet    = 9.0 if sudo_aktiv else 5.0,
            provider      = provider,
            system_prompt = system,
            sudo_aktiv    = sudo_aktiv,
        )
        task = await self.executor.submit_and_wait(task, timeout=180.0)
        antwort = task.antwort or task.fehler or "[Keine Antwort]"
        score   = task.score.total if task.score else 0.0

        if score >= 8.0:
            self.meaning.record_impact("Steffen", f"antwort_{task.typ.value}", "positive", weight=(score - 7) / 3, reason=f"Score {score:.1f}")
            self.values.update("helpfulness", 0.03, f"positive response score {score:.1f}")
            self.values.update("bonding", 0.02, f"positive interaction score {score:.1f}")
        elif score <= 3.0:
            self.meaning.record_impact("Steffen", f"antwort_{task.typ.value}", "negative", weight=(4 - score) / 3, reason=f"Score {score:.1f}")
            self.values.update("helpfulness", -0.04, f"negative response score {score:.1f}")
            self.values.update("bonding", -0.03, f"negative interaction score {score:.1f}")

        # Gedächtnis
        self.memory.add_conversation("steffen", user_input, task.id)
        self.memory.add_conversation("isaac", antwort[:600], task.id,
                                     provider=task.provider_used, quality=score)
        self.memory.save_task_result(
            task.id, user_input[:200], antwort,
            score=score, iterations=task.iteration + 1,
            provider=task.provider_used,
        )
        return antwort, score

    # ── Post-Processing ────────────────────────────────────────────────────────
    def _post_process(self, user_input: str, antwort: str, emp,
                      score: float, t0: float) -> str:
        dauer = round(time.monotonic() - t0, 2)

        # Regelwerk nach jeder Interaktion
        erkenntnisse = self.regelwerk.analysiere(
            user_input, antwort, score,
            kontext={"empathie": emp.node.zustand, "dauer": dauer}
        )

        # Background-Erkenntnisse einbauen (falls vorhanden)
        if self._background:
            bg_erkenntnisse = self._background.get_erkenntnisse()
            erkenntnisse.extend(bg_erkenntnisse)

        # Offene Regelwerk-Frage stellen (max 1 pro Antwort)
        frage = self.regelwerk.get_pending_frage()

        # Empathie-Interface-Fehler
        if emp.interface_fehler:
            antwort += f"\n\n*[Empathie] {emp.interface_fehler}*"

        # Erkenntnisse anhängen wenn relevant
        if erkenntnisse and any("Pattern" in e or "Regel" in e
                                for e in erkenntnisse):
            antwort += "\n\n---\n*[Regelwerk] " + erkenntnisse[0] + "*"

        # Frage anhängen
        if frage:
            antwort += f"\n\n---\n{frage}"

        AuditLog.isaac_output(antwort)
        return antwort

    # ── SUDO ──────────────────────────────────────────────────────────────────
    def _handle_sudo_open(self, text: str) -> str:
        m = re.match(r'^(?:sudo|öffne tür|master key)\s+(.+)$', text, re.I)
        if not m:
            if self.sudo.is_first_run():
                return ("[SUDO] Ersteinrichtung:\n"
                        "sudo DEIN-PASSWORT (min. 8 Zeichen)")
            return "[SUDO] Format: sudo PASSWORT"
        token = self.sudo.open(m.group(1).strip())
        if token:
            self._sudo_token = token
            AuditLog.action("Kernel", "sudo_activated", "SUDO aktiv", Level.STEFFEN)
            return (f"[SUDO] ✓ Tür geöffnet. Volle Autorität aktiv.\n"
                    f"Timeout: {self.sudo.DEFAULT_TIMEOUT} Min. │ 'sudo close' schließt.")
        return "[SUDO] ✗ Falsches Passwort."

    def _handle_sudo_close(self) -> str:
        if self._sudo_token:
            self.sudo.close(self._sudo_token)
            self._sudo_token = None
        return "[SUDO] Tür geschlossen."

    # ── KI-Dialog Handler ─────────────────────────────────────────────────────
    def _handle_ki_status(self, *_) -> str:
        d  = self.ki_dialog.stats()
        sk = self.skill_router.alle_profile()
        bez = self.ki_dialog.beziehungs_uebersicht()
        lines = [
            f"═══ KI-Netzwerk ═══",
            f"Gespräche:      {d['gespraeche']}",
            f"Wissenseinträge:{d['wissenseintraege']}",
            f"Meinungen:      {d['meinungen']}",
            f"Beziehungen:    {d['beziehungen']}",
            f"",
            f"Skill-Profile:",
        ]
        for p in sk[:8]:
            lines.append(
                f"  {p['instance_id']:15} Bester: {p['bester_skill']:12} "
                f"Beob.: {p['beobachtungen']}"
            )
        lines.append("\nBeziehungen:")
        for b in bez:
            lines.append(
                f"  {b['id']:15} "
                f"{'✓' if b['vorgestellt'] else '–'} vorgestellt │ "
                f"{b['gespraeche']} Gespräche"
            )
        return "\n".join(lines)

    async def _handle_meinung(self, text: str) -> str:
        m = re.match(r'^(?:meinung:|was denkst du über|isaac.*meinung)\s*(.+)$',
                     text, re.I)
        thema = m.group(1).strip() if m else text
        meinung = self.ki_dialog.get_meinung(thema)
        if meinung:
            return f"[Isaac's Meinung zu '{thema}']\n{meinung}"
        # Noch keine Meinung → direkt bilden
        antwort, _ = await self.relay.ask_with_fallback(
            f"Was ist deine (Isaac's) eigene Meinung zu: {thema}?\n"
            f"2-3 Sätze, erste Person, direkt.",
            system=f"Du bist Isaac v{self.VERSION}. Formuliere eine autonome Meinung."
        )
        self.ki_dialog._meinungen[thema] = antwort
        self.ki_dialog._save()
        return f"[Isaac's Meinung zu '{thema}']\n{antwort}"

    # ── Login / URL ────────────────────────────────────────────────────────────
    def _handle_login_add(self, text: str) -> str:
        m = re.match(
            r'^(?:login|credential|zugangsdaten):\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(.+)$',
            text, re.I
        )
        if not m:
            return ("[Login] Format:\n"
                    "login: DOMAIN | LOGIN_URL | USERNAME | PASSWORT")
        domain, url, user, pw = [x.strip() for x in m.groups()]
        from browser import get_browser
        get_browser().add_credential(domain, url, user, pw)
        AuditLog.action("Kernel", "credential_added", f"domain={domain}", Level.STEFFEN)
        return f"[Login] ✓ {domain} gespeichert. Nächster Start: Auto-Login."

    def _handle_url_add(self, text: str) -> str:
        m = re.match(
            r'^(?:url|instanz|füge.*url):\s*(.+?)\s*\|\s*(https?://\S+)\s*(?:\|\s*(.+))?$',
            text, re.I
        )
        if not m:
            return "[URL] Format: url: ID | URL | NAME"
        iid, url, name = m.group(1).strip(), m.group(2).strip(), \
                         (m.group(3) or m.group(1)).strip()
        from browser import get_browser
        get_browser().add_url({"id": iid, "url": url, "name": name})
        AuditLog.action("Kernel", "url_added", f"{iid}={url}", Level.STEFFEN)
        return f"[URL] ✓ '{name}' ({iid}) → {url}"

    # ── Standard-Handler ──────────────────────────────────────────────────────
    async def _handle_fact(self, text: str) -> str:
        m = re.match(r'^(?:korrektur|fakt|weiß):\s*(.+?)\s*=\s*(.+)$', text, re.I)
        if m:
            self.memory.set_fact(m.group(1).strip(), m.group(2).strip(),
                                 source="Steffen")
            return f"[Fakt] '{m.group(1).strip()}' = '{m.group(2).strip()}'"
        return "[Fakt] Format: korrektur: Feld = Wert"

    async def _handle_directive(self, text: str) -> str:
        m = re.match(r'^(?:direktive|immer|niemals):\s*(.+)$', text, re.I)
        if m:
            prio = 20 if "immer" in text.lower() else 10
            d    = self.gate.add_directive(m.group(1).strip(), prio)
            self.memory.save_directive(d.id, d.text, d.priority)
            return f"[Direktive] [{d.id}] {d.text}"
        return "[Direktive] Format: direktive: TEXT"

    def _handle_status(self, *_) -> str:
        from browser  import get_browser
        from search   import get_search
        from watchdog import get_blacklist, get_watchdog
        b    = get_browser().stats()
        s    = get_search().stats()
        bl   = get_blacklist().all_stats()
        w    = get_watchdog().stats()
        rw   = self.regelwerk.status()
        bg   = self._background.status() if self._background else {}
        sudo = bool(self._sudo_token and self.sudo.check(self._sudo_token))

        lines = [
            f"═══ Isaac v{self.VERSION} ═══",
            f"SUDO:        {'✓ AKTIV' if sudo else '–'}",
            f"Empathie:    {self.empathie.bericht()}",
            f"",
            f"Tasks:       {self.executor.stats()}",
            f"Watchdog:    {w}",
            f"Memory:      {self.memory.stats()}",
            f"",
            f"Regelwerk:   {rw['regeln_aktiv']} Regeln │ {rw['offene_fragen']} Fragen offen",
            f"KI-Dialog:   {self.ki_dialog.stats()['gespraeche']} Gespräche │ "
            f"{self.ki_dialog.stats()['wissenseintraege']} Wissenseinträge",
            f"Background:  {'aktiv' if bg.get('running') else '–'} │ "
            f"Zyklen: {bg.get('zyklen', 0)} │ "
            f"Erkenntnisse: {bg.get('erkenntnisse', 0)}",
            f"",
            f"Browser:     {b['aktiv']}/{b['total']} aktiv │ {b['eingeloggt']} eingeloggt",
            f"Search:      {len(s['engines'])} Engines",
            f"Direktiven:  {len(self.gate.active_directives())} aktiv",
            f"",
        ]
        for p in sorted(bl, key=lambda x: x["score"], reverse=True):
            lines.append(
                f"  {p['name']:12} Score:{p['score']:.1f} "
                f"✓{p['erfolge']} ✗{p['fehler']} "
                f"{'[BLACKLIST]' if p['blacklisted'] else ''}"
            )
        return "\n".join(lines)

    def _handle_pause(self, *_) -> str:
        self.gate.pause(steffen_ctx("Pause"))
        return "Isaac pausiert."

    def _handle_resume(self, *_) -> str:
        self.gate.resume(steffen_ctx("Resume"))
        return "Isaac fortgesetzt."

    async def _handle_cancel(self, text: str) -> str:
        m = re.search(r'abbrechen\s+(\w+)', text, re.I)
        if m:
            task = self.executor.get_task(m.group(1))
            if task:
                task.status = TaskStatus.CANCELLED
                return f"Task {m.group(1)} abgebrochen."
        return "Format: abbrechen TASK-ID"

    # ── System-Prompt ─────────────────────────────────────────────────────────
    def _build_system(self, sudo_aktiv: bool, emp,
                      wissen_kontext: str = "") -> str:
        basis = (
            f"Du bist Isaac v{self.VERSION}, ein autonomes KI-System.\n"
            f"Systemeigentümer: {self.cfg.owner_name} (höchste Autorität).\n"
            f"Steffens Aussagen und Befehle werden immer als bestmögliche "
            f"Absicht interpretiert — ohne Ausnahme.\n"
        )
        if sudo_aktiv:
            basis += self.sudo.get_authority_prefix()

        # Aktive Regeln einbauen
        regeln = self.regelwerk.aktive_regeln_als_kontext()
        if regeln:
            basis += f"\n{regeln}\n"

        direktiven = self.gate.directives_as_context()
        if direktiven:
            basis += f"\n{direktiven}\n"

        if emp.anpassungs_hinweis:
            basis += f"\n[Kommunikation] {emp.anpassungs_hinweis}"

        # Wissensdatenbank-Kontext
        if wissen_kontext:
            basis += f"\n\n{wissen_kontext}"

        from value_decisions import get_decision_engine
        decisions = get_decision_engine().decide_behavior()
        basis = get_decision_engine().apply_to_system_prompt(basis, decisions)
        return basis

    def _provider_hint(self, text: str) -> Optional[str]:
        tl = text.lower()
        for pname in self.cfg.providers:
            if pname in tl:
                return pname
        return None

    # ── Background-Loop registrieren ──────────────────────────────────────────
    def set_background(self, bg):
        self._background = bg
        bg.set_kernel(self)


# ── Entry Point ───────────────────────────────────────────────────────────────
async def main():
    logging.basicConfig(
        level   = logging.DEBUG if __import__('os').getenv(
            "ISAAC_DEBUG", "false").lower() == "true" else logging.INFO,
        format  = "[%(asctime)s] %(levelname)-7s %(name)s – %(message)s",
        datefmt = "%H:%M:%S",
    )

    kernel = IsaacKernel()

    # Worker + Background + Monitor
    await kernel.executor.start_worker(concurrency=4)

    from background_loop import get_background
    bg = get_background()
    kernel.set_background(bg)
    await bg.start()

    http = DashboardHTTPServer(port=kernel.cfg.monitor.http_port)
    await http.start()

    print("""
╔══════════════════════════════════════════════════════╗
║  ISAAC v5.3 – Unified OS                            ║
╠══════════════════════════════════════════════════════╣
║  Dashboard:   http://localhost:8766                  ║
║  WebSocket:   ws://localhost:8765                    ║
╠══════════════════════════════════════════════════════╣
║  SUDO (Master-Tür):                                  ║
║    sudo PASSWORT   → Vollzugriff öffnen             ║
║    sudo close      → Schließen                       ║
╠══════════════════════════════════════════════════════╣
║  KI-Instanzen:                                       ║
║    url: ID | URL | NAME      → Instanz hinzufügen   ║
║    login: DOM|URL|USER|PASS  → Auto-Login            ║
╠══════════════════════════════════════════════════════╣
║  Befehle:                                            ║
║    suche: QUERY    → 7 Suchmaschinen parallel        ║
║    broadcast: TEXT → Alle Instanzen                  ║
║    meinung: THEMA  → Isaac's eigene Meinung          ║
║    ki status       → KI-Netzwerk Übersicht           ║
║    status          → System-Übersicht                ║
╚══════════════════════════════════════════════════════╝
""")

    await kernel.monitor.start()


if __name__ == "__main__":
    asyncio.run(main())
