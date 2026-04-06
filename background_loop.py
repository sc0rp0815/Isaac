"""
Isaac – Background Loop v3.1-mobile
======================================
Mobile-optimiert:
  - Alle Intervalle verdoppelt/verdreifacht
  - Intensive Operationen nur bei Ladegerät angeschlossen
  - Akku-Sparmodus ab 30% (vorher 20%)
  - Kein paralleles Ollama im Background
"""

import asyncio
import time
import logging
import json
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path

from config    import get_config, DATA_DIR
from audit     import AuditLog
from regelwerk import get_regelwerk
from ki_dialog import get_ki_dialog

log = logging.getLogger("Isaac.Background")

STATE_PATH = DATA_DIR / "background_state.json"


@dataclass
class BackgroundState:
    letzter_health:     float = 0.0
    letzter_knowledge:  float = 0.0
    letzter_ki_dialog:  float = 0.0
    letzter_diskussion: float = 0.0
    letzter_research:   float = 0.0
    letzter_dump:       float = 0.0
    letzter_ideen:      float = 0.0
    zyklen:             int   = 0
    dialoge_gesamt:     int   = 0
    diskussionen_gesamt: int  = 0
    ideen_gesamt:       int   = 0


@dataclass
class Idee:
    idee_id:     str
    summary:     str
    value_score: float
    topic:       str
    source:      str
    ts:          str  = field(default_factory=lambda: time.strftime("%Y-%m-%d %H:%M:%S"))
    gemeldet:    bool = False


class BackgroundLoop:

    # MOBILE: Alle Intervalle deutlich größer
    HEALTH_INTERVAL     = 120      # 2 Minuten
    KNOWLEDGE_INTERVAL  = 600      # 10 Minuten
    IDEEN_INTERVAL      = 900      # 15 Minuten
    KI_DIALOG_INTERVAL  = 1200     # 20 Minuten
    DISKUSSION_INTERVAL = 1800     # 30 Minuten
    RESEARCH_INTERVAL   = 2400     # 40 Minuten
    DUMP_INTERVAL       = 600      # 10 Minuten
    TICK                = 30       # MOBILE: Größerer Tick-Abstand

    # MOBILE: Sparmodus ab 30%
    AKKU_MULTIPLIKATOR = 3
    AKKU_MIN_PROZENT   = 30

    DISKUSSIONS_THEMEN = [
        "Wie entwickelt sich künstliche Intelligenz in den nächsten 10 Jahren?",
        "Was sind die größten ethischen Herausforderungen bei autonomen KI-Systemen?",
        "Wie unterscheiden sich verschiedene Ansätze des maschinellen Lernens?",
        "Welche Rolle spielen Emergenz und Selbstorganisation in komplexen Systemen?",
        "Wie kann Vertrauen zwischen Menschen und KI-Systemen aufgebaut werden?",
        "Welche Protokolle brauchen KIs für effiziente gegenseitige Kommunikation?",
    ]

    def __init__(self):
        self.state        = self._load_state()
        self._running     = False
        self._task:       Optional[asyncio.Task] = None
        self._kernel      = None
        self._puffer:     list = []
        self._ideenqueue: list = []
        self._themen_idx  = 0
        log.info("BackgroundLoop v3.1-mobile initialisiert")

    def set_kernel(self, kernel):
        self._kernel = kernel

    async def start(self):
        self._running = True
        self._task    = asyncio.create_task(self._loop())
        log.info(f"BackgroundLoop gestartet (Tick: {self.TICK}s)")
        AuditLog.action("Background", "start", "BackgroundLoop v3.1-mobile aktiv")

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except Exception:
                pass
        self._dump_state()
        log.info("BackgroundLoop gestoppt")

    async def _akku_status(self) -> dict:
        try:
            proc = await asyncio.create_subprocess_exec(
                "termux-battery-status",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=3.0)
            data    = json.loads(stdout.decode())
            plugged = data.get("plugged", "UNPLUGGED") != "UNPLUGGED"
            prozent = int(data.get("percentage", 100))
            return {"plugged": plugged, "prozent": prozent}
        except Exception:
            return {"plugged": True, "prozent": 100}

    def _intervall(self, basis: int, akku: dict) -> int:
        if akku["plugged"]:
            return basis
        return basis * self.AKKU_MULTIPLIKATOR

    def _notiere(self, text: str):
        self._puffer.append(text)
        AuditLog.action("Background", "note", text[:200])

    def get_erkenntnisse(self) -> list[str]:
        """Liefert gesammelte Erkenntnisse und leert den Puffer danach."""
        out = list(self._puffer)
        self._puffer.clear()
        return out

    def _safe_offene_fragen(self) -> list:
        """Kompatibilitätsschicht für unterschiedliche Regelwerk-APIs."""
        try:
            regelwerk = get_regelwerk()
            if hasattr(regelwerk, 'offene_fragen'):
                res = regelwerk.offene_fragen()
                return list(res) if res is not None else []
            if hasattr(regelwerk, '_offene_fragen'):
                res = regelwerk._offene_fragen()
                return list(res) if res is not None else []
        except Exception as e:
            AuditLog.action("Background", "warn", f"offene_fragen fallback: {e}")
        return []

    # ── Haupt-Loop ─────────────────────────────────────────────────────────────
    async def _loop(self):
        while self._running:
            try:
                now  = time.monotonic()
                akku = await self._akku_status()
                self.state.zyklen += 1

                # Akku-Sparmodus
                if not akku["plugged"] and akku["prozent"] < self.AKKU_MIN_PROZENT:
                    if now - self.state.letzter_health > self.HEALTH_INTERVAL:
                        await self._health_check()
                        self.state.letzter_health = now
                    await asyncio.sleep(self.TICK * 3)
                    continue

                # Health Check
                if now - self.state.letzter_health > self._intervall(self.HEALTH_INTERVAL, akku):
                    await self._health_check()
                    self.state.letzter_health = now

                # Knowledge Check (nur bei Ladegerät)
                if akku["plugged"] and now - self.state.letzter_knowledge > self.KNOWLEDGE_INTERVAL:
                    await self._knowledge_check()
                    self.state.letzter_knowledge = now

                # KI-Dialog (nur bei Ladegerät)
                if akku["plugged"] and now - self.state.letzter_ki_dialog > self.KI_DIALOG_INTERVAL:
                    await self._ki_dialog_zyklus()
                    self.state.letzter_ki_dialog = now

                # Diskussion (nur bei Ladegerät + vollem Akku)
                if (akku["plugged"] and akku["prozent"] > 50 and
                        now - self.state.letzter_diskussion > self.DISKUSSION_INTERVAL):
                    await self._diskussions_zyklus()
                    self.state.letzter_diskussion = now

                # Wertgesteuerte Entscheidungen alle 30 Minuten
                if now - getattr(self, "_last_value_decision", 0) > 1800:
                    from value_decisions import get_decision_engine
                    decisions = get_decision_engine().decide_behavior()
                    self._notiere(f"Verhaltensanpassung: {decisions}")
                    self._last_value_decision = now

                # State Dump
                if now - self.state.letzter_dump > self.DUMP_INTERVAL:
                    self._dump_state()
                    self.state.letzter_dump = now

                await asyncio.sleep(self.TICK)

            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(f"Background-Loop Fehler: {e}", exc_info=True)
                await asyncio.sleep(60)

    # ── Health Check ─────────────────────────────────────────────────────────
    async def _health_check(self):
        try:
            from relay import get_relay
            relay = get_relay()
            # Prüfe ob Ollama erreichbar ist
            r = await relay.ask(
                "Antwort: OK",
                system   = "Antworte nur mit 'OK'.",
                provider = "ollama",
                task_id  = "health",
            )
            ok = "OK" in r or not r.startswith("[RELAY")
            if not ok:
                log.warning(f"Health-Check: Ollama meldet Fehler: {r[:80]}")
            else:
                log.debug("Health-Check: OK")

            from instincts import get_instincts
            from meaning import get_meaning
            get_instincts().update_from_system({
                "recent_errors": 0 if ok else 1,
                "open_questions": len(self._safe_offene_fragen()),
                "steffen_engagement": get_meaning().get_bonding("Steffen"),
            })
        except Exception as e:
            log.warning(f"Health-Check: {e}")

    # ── Knowledge Check ───────────────────────────────────────────────────────
    async def _knowledge_check(self):
        try:
            regelwerk = get_regelwerk()
            fragen = self._safe_offene_fragen()
            if fragen and self._kernel:
                for frage in fragen[:1]:
                    self._puffer.append(frage)
        except Exception as e:
            log.debug(f"Knowledge-Check: {e}")

    # ── KI-Dialog Zyklus ─────────────────────────────────────────────────────
    async def _ki_dialog_zyklus(self):
        try:
            ki_dialog = get_ki_dialog()
            await ki_dialog.spontaner_dialog()
            self.state.dialoge_gesamt += 1
            log.info(f"KI-Dialog Zyklus #{self.state.dialoge_gesamt}")
        except Exception as e:
            log.debug(f"KI-Dialog: {e}")

    # ── Diskussions-Zyklus ────────────────────────────────────────────────────
    async def _diskussions_zyklus(self):
        try:
            thema = self.DISKUSSIONS_THEMEN[
                self._themen_idx % len(self.DISKUSSIONS_THEMEN)
            ]
            self._themen_idx += 1
            ki_dialog = get_ki_dialog()
            await ki_dialog.multi_diskussion(thema)
            self.state.diskussionen_gesamt += 1
            log.info(f"Diskussion #{self.state.diskussionen_gesamt}: {thema[:50]}")
        except Exception as e:
            log.debug(f"Diskussion: {e}")

    # ── State Dump ────────────────────────────────────────────────────────────
    def _dump_state(self):
        try:
            data = {
                "letzter_health":     self.state.letzter_health,
                "letzter_ki_dialog":  self.state.letzter_ki_dialog,
                "zyklen":             self.state.zyklen,
                "dialoge_gesamt":     self.state.dialoge_gesamt,
                "ideen_gesamt":       self.state.ideen_gesamt,
            }
            STATE_PATH.write_text(json.dumps(data, indent=2))
        except Exception:
            pass

    def _load_state(self) -> BackgroundState:
        try:
            if STATE_PATH.exists():
                data = json.loads(STATE_PATH.read_text())
                return BackgroundState(**{k: v for k, v in data.items()
                                          if k in BackgroundState.__dataclass_fields__})
        except Exception:
            pass
        return BackgroundState()

    # ── Öffentliche API ───────────────────────────────────────────────────────
    def get_puffer(self) -> list:
        puffer = self._puffer[:]
        self._puffer.clear()
        return puffer

    def get_ideen(self, min_score: float = 6.5) -> list:
        return [
            {"idee_id": i.idee_id, "summary": i.summary,
             "score": i.value_score, "topic": i.topic, "gemeldet": i.gemeldet}
            for i in self._ideenqueue if i.value_score >= min_score
        ]

    def status(self) -> dict:
        return {
            "running":           self._running,
            "zyklen":            self.state.zyklen,
            "dialoge_gesamt":    self.state.dialoge_gesamt,
            "diskussionen":      self.state.diskussionen_gesamt,
            "ideen_gesamt":      self.state.ideen_gesamt,
            "ideen_queue":       len(self._ideenqueue),
            "puffer":            len(self._puffer),
        }


_background: Optional[BackgroundLoop] = None

def get_background() -> BackgroundLoop:
    global _background
    if _background is None:
        _background = BackgroundLoop()
    return _background
