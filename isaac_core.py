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
import json
import re
import time
import hashlib
import logging
from typing import Optional, Any

from config         import get_config, Level, WORKSPACE, is_owner_equivalent_mode
from constitution_override import apply_constitution_gate, build_override_context
from privilege      import get_gate, steffen_ctx, isaac_ctx
from audit          import AuditLog, setup_privilege_audit
from memory         import get_memory
from executor       import get_executor, TaskType, TaskStatus, Strategy
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
from self_model     import get_self_model
from low_complexity import (
    ClassificationResult,
    InteractionClass,
    classify_interaction_result,
    is_lightweight_local_class,
    is_low_complexity_local_input,
    local_class_response,
    local_fast_response,
    normalize_low_complexity,
)
from neural_core   import get_neural_cortex
from learning_engine import get_learning_engine

log = logging.getLogger("Isaac.Kernel")

# ── Komplexitätsschwelle für Decomposer ───────────────────────────────────────
DECOMPOSE_WORT_SCHWELLE = 15   # Ab 15 Wörtern → Decomposer
DECOMPOSE_THEMEN_SCHWELLE = 2  # Ab 2 erkennbaren Themen → Decomposer


# ── Intents ────────────────────────────────────────────────────────────────────
class Intent:
    CHAT        = "chat"
    SEARCH      = "search"
    RESEARCH    = "research"
    BROWSER     = "browser"
    AGENT       = "agent"
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


EXPLICIT_COMMAND_PATTERNS = [
    (Intent.SUDO_OPEN,  [r"^sudo\s+", r"^öffne tür", r"^master key"]),
    (Intent.SUDO_CLOSE, [r"^sudo close$", r"^tür schließen$"]),
    (Intent.FACT_SET,   [r"^korrektur:", r"^fakt:", r"^weiß:"]),
    (Intent.DIRECTIVE,  [r"^direktive:", r"^immer:", r"^niemals:"]),
    (Intent.BROADCAST,  [r"^broadcast:", r"^alle instanzen:", r"^frage alle"]),
    (Intent.SPLIT,      [r"^split:", r"^aufteilen:"]),
    (Intent.PIPELINE,   [r"^pipeline:", r"^verbessere iterativ"]),
    (Intent.DECOMPOSE,  [r"^atomisiere:", r"^verteile:"]),
    (Intent.CODE,       [r"^code:", r"^programmiere:", r"^schreibe.*python"]),
    (Intent.FILE,       [
        r"^datei:",
        r"^lese:",
        r"^schreibe.*datei",
        r"^datei\s+(?:read|write|append|list|ls|info)\b",
    ]),
    (Intent.RESEARCH,   [r"^recherche:", r"^recherchiere:"]),
    (Intent.AGENT,      [
        r"^agent:",
        r"^oberfläche:",
        r"^oberflaeche:",
        r"^shell\s+",
        r"^ausführ",
        r"^ausfuehr",
        r"^führe aus",
        r"^fuehre aus",
        r"^befehl:",
    ]),
    (Intent.TRANSLATE,  [r"^übersetze", r"^translate", r"^schrift:"]),
    (Intent.LOGIN_ADD,  [r"^login:", r"^credential:", r"^zugangsdaten:"]),
    (Intent.URL_ADD,    [r"^url:", r"^instanz:", r"^füge.*url"]),
    (Intent.KI_STATUS,  [r"^ki status$", r"^instanzen$", r"^meinungen$"]),
    (Intent.MEINUNG,    [r"^meinung:", r"^was denkst du über", r"^isaac.*meinung"]),
    (Intent.PAUSE,      [r"^pause$", r"^stopp$"]),
    (Intent.RESUME,     [r"^weiter$", r"^fortsetzen$"]),
    (Intent.CANCEL,     [r"^abbrechen\s+\w+"]),
]

def detect_intent(text: str) -> str:
    tl = text.lower().strip()
    for intent, patterns in EXPLICIT_COMMAND_PATTERNS:
        for pat in patterns:
            if re.search(pat, tl):
                return intent
    return Intent.CHAT


def braucht_decomposer(text: str, intent: str) -> bool:
    """Entscheidet ob ein Prompt atomisiert werden soll."""
    if intent in (Intent.CODE, Intent.FILE, Intent.SEARCH, Intent.RESEARCH,
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
        self.neural     = get_neural_cortex()
        self.learning   = get_learning_engine()
        self._background = None   # lazy start in main()

        set_kernel(self)
        self._sudo_token: Optional[str] = None
        self._awaiting_frage_id: Optional[str] = None

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

        t_start = time.perf_counter()
        timing: dict[str, float] = {}

        # 0) Klassifikation als harte Routing-Grundlage
        classification = classify_interaction_result(user_input)
        interaction_class = classification.interaction_class
        if is_lightweight_local_class(interaction_class):
            self._awaiting_frage_id = None
            timing["classification_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            log.info("Latency(lightweight) | total=%sms input='%s'", timing["classification_ms"], user_input[:42])
            return local_class_response(interaction_class, user_input)

        timing["classification_ms"] = round((time.perf_counter() - t_start) * 1000, 2)

        t0 = time.monotonic()

        if is_owner_equivalent_mode():
            from decision_trace import DecisionTrace, TracePhase, audit_routing_trace
            from owner_action import detect_owner_action, execute_owner_action
            from procedure_memory import record_owner_action_outcome

            owner_action = detect_owner_action(user_input)
            if owner_action:
                AuditLog.steffen_input(user_input)
                emp = self.empathie.analysiere(user_input)
                trace = DecisionTrace()
                trace.add(
                    TracePhase.CLASSIFICATION,
                    "owner_action_detected",
                    {
                        "kind": owner_action.kind,
                        "params": dict(owner_action.params or {}),
                        "privilege_mode": "admin",
                    },
                )
                result, ok = await execute_owner_action(owner_action)
                timing["owner_action_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
                trace.add(
                    TracePhase.EXECUTION,
                    "owner_action_executed",
                    {
                        "kind": owner_action.kind,
                        "ok": ok,
                        "duration_ms": timing["owner_action_ms"],
                    },
                )
                audit_routing_trace(
                    trace,
                    intent=f"owner:{owner_action.kind}",
                    outcome="success" if ok else "failed",
                )
                try:
                    record_owner_action_outcome(
                        kind=owner_action.kind,
                        raw=user_input,
                        ok=ok,
                    )
                except Exception as exc:
                    log.debug("Owner procedure capture skipped: %s", exc)
                if ok:
                    try:
                        get_self_model().bump_value_strength(
                            "autonomy",
                            strength_delta=0.008,
                            confidence_delta=0.004,
                            reason=f"owner_action:{owner_action.kind}",
                        )
                    except Exception as exc:
                        log.debug("SelfModel autonomy bump skipped: %s", exc)
                log.info(
                    "OwnerAction | kind=%s ok=%s ms=%s input='%s'",
                    owner_action.kind,
                    ok,
                    timing["owner_action_ms"],
                    user_input[:60],
                )
                return self._post_process(user_input, result, emp, 8.0 if ok else 4.0, t0)

        if interaction_class in {
            InteractionClass.STATUS_QUERY,
            InteractionClass.TOOL_REQUEST,
        }:
            self._awaiting_frage_id = None
        elif self._awaiting_frage_id and self._input_looks_like_frage_antwort(
            user_input, interaction_class
        ):
            frage_id = self._awaiting_frage_id
            antwort_text = user_input.strip()
            if antwort_text.lower().startswith("antwort:"):
                antwort_text = antwort_text.split(":", 1)[-1].strip()
            self.regelwerk.beantworte_frage(frage_id, antwort_text)
            self._persist_regelwerk_answer_to_memory(frage_id, antwort_text)
            self._awaiting_frage_id = None
            emp = self.empathie.analysiere(user_input)
            antwort = self.regelwerk.build_answer_ack(frage_id, antwort_text)
            return self._post_process(user_input, antwort, emp, 8.0, t0)

        # SUDO-Status
        sudo_aktiv = (
            (sudo_token and self.sudo.check(sudo_token)) or
            (self._sudo_token and self.sudo.check(self._sudo_token))
        )

        AuditLog.steffen_input(user_input)

        # 1. Empathie
        emp = self.empathie.analysiere(user_input)
        timing["empathie_ms"] = round((time.perf_counter() - t_start) * 1000, 2)

        # 2. Wissensdatenbank konsultieren
        wissen_kontext = self.ki_dialog.als_kontext(user_input)
        timing["wissen_ms"] = round((time.perf_counter() - t_start) * 1000, 2)

        # 3. Intent: Klassifikation ist führend, Regex nur für explizite Kommandos
        detected_intent = detect_intent(user_input)
        intent = self._resolve_intent_from_classification(
            user_input, detected_intent, interaction_class
        )
        timing["routing_prep_ms"] = round((time.perf_counter() - t_start) * 1000, 2)

        log.info(
            f"Input: '{user_input[:50]}' │ Intent: {intent} │ "
            f"Node: {emp.node.zustand} │ Sudo: {sudo_aktiv}"
        )

        blocked_msg, constitution_gate = self._enforce_constitution_gate(
            user_input, intent, sudo_aktiv
        )
        if blocked_msg:
            self._audit_constitution_block(intent, constitution_gate)
            AuditLog.isaac_output(blocked_msg)
            return blocked_msg

        # SUDO-Handshake
        if intent == Intent.SUDO_OPEN:
            return self._handle_sudo_open(user_input)
        if intent == Intent.SUDO_CLOSE:
            return self._handle_sudo_close()

        # Pause
        if self.gate.is_paused and not sudo_aktiv:
            return "[Isaac] Pausiert. 'weiter' oder SUDO zum Fortfahren."

        if intent == Intent.AGENT or self._is_agent_request(user_input):
            result = await self._handle_agent_request(user_input)
            return self._post_process(user_input, result, emp, 0.0, t0)

        if intent == Intent.BROWSER or self._is_browser_request(user_input):
            result = await self._handle_browser_request(user_input)
            return self._post_process(user_input, result, emp, 0.0, t0)

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
            user_input,
            intent,
            sudo_aktiv,
            emp,
            wissen_kontext,
            interaction_class,
            classification,
            constitution_gate=constitution_gate,
        )
        timing["route_done_ms"] = round((time.perf_counter() - t_start) * 1000, 2)

        total_ms = round((time.perf_counter() - t_start) * 1000, 2)
        log.info(
            "Latency(process) | total=%sms classify=%sms empathie=%sms wissen=%sms prep=%sms route=%sms class=%s intent=%s",
            total_ms,
            timing.get("classification_ms", 0.0),
            timing.get("empathie_ms", 0.0),
            timing.get("wissen_ms", 0.0),
            timing.get("routing_prep_ms", 0.0),
            timing.get("route_done_ms", 0.0),
            interaction_class,
            intent,
        )

        return self._post_process(user_input, antwort, emp, score, t0)

    # ── Routing ────────────────────────────────────────────────────────────────
    async def _route(self, user_input: str, intent: str,
                     sudo_aktiv: bool, emp, wissen_kontext: str,
                     interaction_class: str,
                     classification: ClassificationResult,
                     constitution_gate: Optional[dict] = None,
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
            user_input,
            intent,
            sudo_aktiv,
            emp,
            wissen_kontext,
            interaction_class,
            classification,
            constitution_gate=constitution_gate,
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
                              sudo_aktiv: bool, emp, wissen_kontext: str,
                              interaction_class: str,
                              classification: ClassificationResult,
                              constitution_gate: Optional[dict] = None,
                              ) -> tuple[str, float]:
        retrieval_ctx = self._retrieve_relevant_context(
            user_input=user_input,
            intent=intent,
            interaction_class=interaction_class,
        )
        neural_trace = self.neural.propagate(
            interaction_class=interaction_class,
            intent=intent,
            retrieval_ctx=retrieval_ctx,
            word_count=classification.word_count,
        )
        strategy = self._select_response_strategy(
            user_input=user_input,
            intent=intent,
            interaction_class=interaction_class,
            retrieval_ctx=retrieval_ctx,
        )
        modulation = self.neural.modulate_strategy(
            allow_tools=strategy.allow_tools,
            allow_followup=strategy.allow_followup,
            allow_provider_switch=strategy.allow_provider_switch,
            trace=neural_trace,
        )
        if modulation.allow_tools is not None:
            strategy = Strategy(
                allow_tools=modulation.allow_tools,
                allow_followup=modulation.allow_followup if modulation.allow_followup is not None else strategy.allow_followup,
                allow_provider_switch=(
                    modulation.allow_provider_switch
                    if modulation.allow_provider_switch is not None
                    else strategy.allow_provider_switch
                ),
                style_note=(strategy.style_note or "") + (f"\n{modulation.neural_note}" if modulation.neural_note else ""),
            )
        typ_map = {
            Intent.SEARCH:    TaskType.SEARCH,
            Intent.RESEARCH:  TaskType.RESEARCH,
            Intent.CODE:      TaskType.CODE,
            Intent.FILE:      TaskType.FILE,
            Intent.TRANSLATE: TaskType.TRANSLATE,
            Intent.CHAT:      TaskType.CHAT,
        }
        task_typ = typ_map.get(intent, TaskType.CHAT)
        system   = self._build_system(
            sudo_aktiv, emp, wissen_kontext,
            strategy_note=strategy.style_note
        )
        provider = self._provider_hint(user_input)

        structured_ctx = self._format_retrieval_context(retrieval_ctx)
        kontext = structured_ctx.strip()
        prompt = f"{kontext}\n\n{user_input}".strip() if kontext else user_input

        task = self.executor.create_task(
            typ           = task_typ,
            prompt        = prompt,
            beschreibung  = user_input[:80],
            prioritaet    = 9.0 if sudo_aktiv else 5.0,
            provider      = provider,
            system_prompt = system,
            sudo_aktiv    = sudo_aktiv,
            strategy      = strategy,
            interaction_class=interaction_class,
            classification=classification,
            retrieved_context = retrieval_ctx,
        )
        from decision_trace import TracePhase, gate_trace_data

        if constitution_gate:
            task.decision_trace.add(
                TracePhase.GOVERNANCE,
                "constitution_allowed",
                gate_trace_data(constitution_gate),
            )
        task.decision_trace.add(
            TracePhase.CLASSIFICATION,
            "classified",
            {
                "interaction_class": interaction_class,
                "intent": intent,
                "word_count": classification.word_count,
            },
        )
        task.decision_trace.add(
            TracePhase.RETRIEVAL,
            "retrieved",
            {
                "facts": len(retrieval_ctx.get("relevant_facts", [])),
                "procedures": len(retrieval_ctx.get("relevant_procedures", [])),
                "open_questions": len(retrieval_ctx.get("open_questions", [])),
            },
        )
        task.decision_trace.add(
            TracePhase.STRATEGY,
            "strategy_selected",
            {
                "allow_tools": strategy.allow_tools,
                "allow_followup": strategy.allow_followup,
                "allow_provider_switch": strategy.allow_provider_switch,
            },
        )
        task = await self.executor.submit_and_wait(task, timeout=180.0)
        antwort = task.antwort or task.fehler or "[Keine Antwort]"
        score   = task.score.total if task.score else 0.0

        cfg = getattr(self, "cfg", None) or get_config()
        if (
            getattr(cfg, "auto_provision_providers", True)
            and cfg.browser_automation
            and self._relay_failure_needs_provision(antwort)
        ):
            failed_provider = self._extract_failed_provider(antwort) or provider or cfg.relay.primary_provider
            target_ids = None if getattr(cfg, "auto_provision_all_providers", True) else (
                [failed_provider] if failed_provider else None
            )
            provision = await self._auto_provision_providers(target_ids)
            if provision.get("ok"):
                retry = self.executor.create_task(
                    typ=task_typ,
                    prompt=prompt,
                    beschreibung=f"retry:{user_input[:72]}",
                    prioritaet=task.prioritaet,
                    provider=failed_provider or provider,
                    system_prompt=system,
                    sudo_aktiv=sudo_aktiv,
                    strategy=strategy,
                    interaction_class=interaction_class,
                    classification=classification,
                    retrieved_context=retrieval_ctx,
                )
                retry = await self.executor.submit_and_wait(retry, timeout=180.0)
                if retry.antwort and not self._relay_failure_needs_provision(retry.antwort):
                    task = retry
                    antwort = retry.antwort
                    score = retry.score.total if retry.score else score

        # Stabiles lokales Fallback für triviale Inputs, falls Provider ausfallen.
        if task.typ == TaskType.CHAT and is_low_complexity_local_input(user_input):
            if ("[RELAY] Alle Provider fehlgeschlagen" in antwort or
                    not task.provider_used or score <= 1.0):
                antwort = local_fast_response(user_input)
                score = max(score, 6.0)

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
        final_trace = self.neural.propagate(
            interaction_class=interaction_class,
            intent=intent,
            retrieval_ctx=retrieval_ctx,
            word_count=classification.word_count,
            execution_score=score,
        )
        self.neural.reinforce(final_trace, score)
        outcome = "success" if score >= 5.0 else "weak" if score > 0 else "failed"
        self.learning.learn(
            prompt=user_input,
            route=f"{interaction_class}/{intent}",
            outcome=outcome,
            score=score,
            notes=json.dumps(final_trace.as_dict(), ensure_ascii=False)[:1000],
        )
        return antwort, score

    # ── Post-Processing ────────────────────────────────────────────────────────
    def _update_self_model_from_interaction(
        self,
        user_input: str,
        antwort: str,
        emp,
        *,
        interaction_class: str = "",
        score: float = 0.0,
    ) -> None:
        from self_model_hooks import process_interaction

        process_interaction(
            user_input=user_input,
            antwort=antwort,
            emp=emp,
            interaction_class=interaction_class,
            score=score,
        )

    def _post_process(self, user_input: str, antwort: str, emp,
                      score: float, t0: float) -> str:
        dauer = round(time.monotonic() - t0, 2)

        try:
            self._update_self_model_from_interaction(
                user_input,
                antwort,
                emp,
                interaction_class=classify_interaction_result(user_input).interaction_class,
                score=score,
            )
        except Exception as exc:
            log.debug("SelfModel update skipped: %s", exc)

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
        def _erkenntnis_text(entry) -> str:
            if isinstance(entry, str):
                return entry
            text = getattr(entry, "text", None)
            return str(text) if text else str(entry)

        if erkenntnisse and any(
            "Pattern" in _erkenntnis_text(e) or "Regel" in _erkenntnis_text(e)
            for e in erkenntnisse
        ):
            antwort += "\n\n---\n*[Regelwerk] " + _erkenntnis_text(erkenntnisse[0]) + "*"

        # Frage anhängen (nicht bei jeder Antwort wiederholen)
        if frage:
            top = self.regelwerk.get_top_pending_frage()
            main = (antwort or "").strip()
            substantive_answer = len(main) >= 30 and not main.startswith("[RELAY]")
            if top and substantive_answer and self._awaiting_frage_id != top.id:
                self._awaiting_frage_id = top.id
                antwort += f"\n\n---\n{frage}"
        else:
            self._awaiting_frage_id = None

        AuditLog.isaac_output(antwort)
        return antwort

    _CONSTITUTION_GATED_INTENTS = frozenset({
        Intent.SUDO_OPEN,
        Intent.CODE,
        Intent.FILE,
        Intent.BROWSER,
        Intent.AGENT,
        Intent.LOGIN_ADD,
        Intent.DIRECTIVE,
        Intent.FACT_SET,
    })

    def _build_constitution_metadata(
        self, intent: str, user_input: str, sudo_aktiv: bool
    ) -> tuple[str, dict[str, Any]]:
        text = (user_input or "").lower()
        metadata: dict[str, Any] = {
            "audit_logged": True,
            "outside_effect": True,
        }

        if intent == Intent.SUDO_OPEN:
            return "grant_privilege", {
                **metadata,
                "privilege_escalation": True,
                "owner_approved": True,
                "risk": "high",
            }
        if intent == Intent.CODE:
            meta = {**metadata, "risk": "high"}
            if "constitution" in text and any(
                token in text for token in ("änder", "umschreib", "modify", "rewrite")
            ):
                meta["self_modify_constitution"] = True
            return "execute_code", meta
        if intent == Intent.FILE:
            write_markers = ("schreibe", "write", "speichere", "lösch", "delete")
            is_write = any(marker in text for marker in write_markers)
            meta = {**metadata, "risk": "high" if is_write else "low"}
            if "constitution" in text and any(
                token in text for token in ("änder", "umschreib", "modify", "rewrite")
            ):
                meta["self_modify_constitution"] = True
            return ("file_delete" if is_write else "system_command"), meta
        if intent == Intent.BROWSER:
            return "tool_invoke", {**metadata, "risk": "normal"}
        if intent == Intent.LOGIN_ADD:
            return "modify_config", {
                **metadata,
                "privilege_escalation": True,
                "owner_approved": True,
                "risk": "high",
            }
        if intent == Intent.DIRECTIVE:
            return "modify_config", {**metadata, "risk": "normal"}
        if intent == Intent.FACT_SET:
            return "system_command", {
                **metadata,
                "uncertain_claim_as_fact": False,
                "risk": "low",
            }
        if intent == Intent.AGENT:
            read_only = any(
                token in text
                for token in ("observe", "screenshot", "clipboard get", "status")
            ) and "shell" not in text and "tap" not in text and "type" not in text
            return "system_command", {
                **metadata,
                "risk": "low" if read_only else "high",
                "owner_approved": True,
            }
        return "", {}

    def _enforce_constitution_gate(
        self, user_input: str, intent: str, sudo_aktiv: bool
    ) -> tuple[Optional[str], Optional[dict]]:
        if intent not in self._CONSTITUTION_GATED_INTENTS:
            return None, None
        action, metadata = self._build_constitution_metadata(
            intent, user_input, sudo_aktiv
        )
        if not action:
            return None, None

        gate = apply_constitution_gate(
            action,
            metadata,
            build_override_context(
                prompt=user_input,
                sudo_active=sudo_aktiv or is_owner_equivalent_mode(),
                caller_level=Level.STEFFEN,
                owner_confirmed=is_owner_equivalent_mode(),
                override_reason="owner_equivalent_mode" if is_owner_equivalent_mode() else "",
                source="isaac_core",
            ),
        )
        if gate.get("allowed"):
            return None, gate

        blocked_by = list(gate.get("blocked_by") or [])
        override = gate.get("override") or {}
        reason = str(override.get("reason") or "Verfassung blockiert diese Aktion")
        return (
            f"[Verfassung] Aktion blockiert: {', '.join(blocked_by)}. "
            f"{reason}. "
            f"Owner-Override: 'override: <Begründung>' (mit SUDO wenn nötig).",
            gate,
        )

    def _audit_constitution_block(
        self, intent: str, constitution_gate: Optional[dict]
    ) -> None:
        from decision_trace import (
            DecisionTrace,
            TracePhase,
            audit_routing_trace,
            gate_trace_data,
        )

        trace = DecisionTrace()
        trace.add(
            TracePhase.GOVERNANCE,
            "constitution_blocked",
            gate_trace_data(constitution_gate),
        )
        audit_routing_trace(trace, intent=intent, outcome="blocked")

    def _persist_regelwerk_answer_to_memory(self, frage_id: str, antwort: str) -> None:
        frage = self.regelwerk.get_frage(frage_id)
        if not frage:
            return
        text = (antwort or "").strip()
        if not text:
            return
        term = self.regelwerk._extract_term_from_frage(frage)
        if term:
            key = f"definition.{term.lower()}"
            value = text[:500]
        else:
            key = f"regelwerk.answer.{frage_id}"
            value = f"{frage.text[:120]} → {text[:380]}"
        self.memory.set_fact(key, value, source="Steffen", confidence=1.0)

    def _input_looks_like_frage_antwort(
        self, user_input: str, interaction_class: str
    ) -> bool:
        if interaction_class in {
            InteractionClass.SOCIAL_GREETING,
            InteractionClass.SOCIAL_ACKNOWLEDGMENT,
            InteractionClass.STATUS_QUERY,
            InteractionClass.TOOL_REQUEST,
        }:
            return False
        text = (user_input or "").strip()
        if len(text) < 3:
            return False
        if text.lower().startswith("antwort:"):
            return True
        normalized = normalize_low_complexity(text)
        if "?" in text and any(
            normalized.startswith(prefix)
            for prefix in ("was ", "wie ", "warum ", "wer ", "wann ", "wo ", "kannst ")
        ):
            return False
        return len(normalized.split()) >= 2

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

    def _is_agent_request(self, text: str) -> bool:
        tl = (text or "").lower().strip()
        if tl.startswith(("agent:", "agent ", "oberfläche:", "oberflaeche:")):
            return True
        if not is_owner_equivalent_mode():
            return False
        return tl.startswith((
            "shell ",
            "ausführ",
            "ausfuehr",
            "führe aus",
            "fuehre aus",
            "befehl:",
        ))

    async def _handle_agent_request(self, text: str) -> str:
        from computer_use import (
            get_computer_use,
            parse_agent_flow,
            format_agent_result,
            computer_use_enabled,
        )

        if not computer_use_enabled():
            return (
                "[Agent] Computer-Use ist deaktiviert.\n"
                "Aktiviere computer_use_enabled in data/runtime_settings.json "
                "oder setze ISAAC_RUNTIME_ENV=termux."
            )

        body = (text or "").split(":", 1)[-1].strip()
        if text.lower().startswith("oberfläche:") or text.lower().startswith("oberflaeche:"):
            body = text.split(":", 1)[-1].strip()
        elif is_owner_equivalent_mode():
            tl = (text or "").lower().strip()
            if tl.startswith("shell "):
                body = f"shell {text[6:].strip()}"
            elif tl.startswith(("ausführ", "ausfuehr", "führe aus", "fuehre aus", "befehl:")):
                cmd = re.split(r"[:]\s*", text, maxsplit=1)[-1].strip()
                body = f"shell {cmd}" if cmd else "diagnose"
        try:
            actions = parse_agent_flow(body)
        except Exception as exc:
            return (
                "[Agent] Ungültiger Befehl.\n"
                "Beispiele:\n"
                "  agent: diagnose\n"
                "  agent: observe\n"
                "  agent: screenshot\n"
                "  agent: shell ls -la workspace\n"
                "  agent: clipboard get\n"
                "  agent: open https://github.com\n"
                "  agent: ui dump | ui list | ui tap Einstellungen | ui unlock | ui key enter\n"
                "  agent: credential list | credential read SITE [--import] | credential screen\n"
                "  agent: flow shell pwd; screenshot; shell ls workspace\n"
                f"Fehler: {exc}"
            )

        runtime = get_computer_use()
        if len(actions) == 1:
            result = await runtime.execute(actions[0])
        else:
            result = await runtime.execute_flow(actions)
        return format_agent_result(result)

    def _provisionable_provider_ids(self) -> tuple[str, ...]:
        try:
            from browser import provisionable_provider_ids
            return provisionable_provider_ids()
        except Exception:
            return ("groq", "openrouter", "mistral", "together", "perplexity")

    _PROVIDER_ALL_MARKERS = (
        "alle api", "alle provider", "alle keys", "all providers", "all api",
        "jeden provider", "sämtliche", "saemtliche", "restliche keys",
    )
    _PROVIDER_KEY_TOKENS = ("token", "api key", "apikey", "api-key", "schlüssel", "key", "schluessel")
    _PROVIDER_ACTION_TOKENS = (
        "generier", "erstell", "create", "new", "neu", "hol", "beschaff",
        "einricht", "verbind", "connect", "setup", "aktivier", "provision",
    )

    def _is_provider_provision_request(self, text: str) -> bool:
        tl = (text or "").lower().strip()
        if tl.startswith(("provider:", "verbinde:", "connect:", "provision:")):
            return True
        if any(phrase in tl for phrase in (
            "api keys einrichten",
            "provider verbinden",
            "fehlende keys",
            "keys holen",
            "provider connecten",
            "selbst verbinden",
            "keys selbst beschaffen",
            "api keys selbst",
            "alle keys verbinden",
            "alle provider verbinden",
        )):
            return True
        if any(marker in tl for marker in self._PROVIDER_ALL_MARKERS):
            return True
        pids = self._provisionable_provider_ids()
        has_provider = any(pid in tl for pid in pids)
        has_key = any(token in tl for token in self._PROVIDER_KEY_TOKENS)
        has_action = any(token in tl for token in self._PROVIDER_ACTION_TOKENS)
        if has_provider and has_key and has_action:
            return True
        if has_provider and any(token in tl for token in ("einrichten", "verbinden", "connecten", "connect")):
            return True
        return False

    def _wants_provision_all_providers(self, text: str) -> bool:
        tl = (text or "").lower().strip()
        if any(marker in tl for marker in self._PROVIDER_ALL_MARKERS):
            return True
        if tl.startswith(("provider:", "verbinde:", "connect:", "provision:")):
            payload = tl.split(":", 1)[-1].strip()
            if payload in {"alle", "all", "auto", "*"}:
                return True
        return any(phrase in tl for phrase in (
            "alle keys", "alle api", "alle provider", "restliche keys", "keys selbst beschaffen",
        ))

    def _resolve_provider_provision_target(self, text: str) -> Optional[str]:
        tl = (text or "").lower().strip()
        if self._wants_provision_all_providers(text):
            return "all"
        pids = self._provisionable_provider_ids()
        if tl.startswith(("provider:", "verbinde:", "connect:", "provision:")):
            payload = tl.split(":", 1)[-1].strip()
            for pid in pids:
                if pid in payload:
                    return pid
        for pid in pids:
            if pid in tl:
                return pid
        missing = []
        try:
            from browser import get_browser
            missing = get_browser().providers_needing_provision()
        except Exception:
            missing = []
        if missing:
            return missing[0]
        return (self.cfg.relay.primary_provider or "groq").strip().lower() or None

    def _is_browser_request(self, text: str) -> bool:
        tl = (text or "").lower().strip()
        if tl.startswith("browser:"):
            return True
        if any(tl.startswith(prefix) for prefix in (
            "browser auf",
            "öffne im browser",
            "navigiere zu",
        )):
            return True
        return self._is_provider_provision_request(text)

    def _relay_failure_needs_provision(self, antwort: str) -> bool:
        tl = (antwort or "").lower()
        return "api-key fehlt" in tl or "api key fehlt" in tl

    def _extract_failed_provider(self, antwort: str) -> Optional[str]:
        match = re.search(r"\[relay-fehler:([^\]]+)\]", (antwort or "").lower())
        if match:
            return match.group(1).strip()
        for pid in self._provisionable_provider_ids():
            if pid in (antwort or "").lower():
                return pid
        return None

    def _ensure_provider_connect_directive(self):
        try:
            active = {d.get("id") for d in self.memory.get_directives()}
            if "provider_auto_connect_all" in active:
                return
            self.memory.save_directive(
                "provider_auto_connect_all",
                (
                    "Beschaffe und verbinde fehlende Provider-API-Keys selbstständig "
                    "über den Browser (alle unterstützten Provider), wenn Browser-Automation "
                    "aktiv ist und ein Login vorhanden ist."
                ),
                priority=9,
            )
            log.info("Owner-Direktive gesetzt: provider_auto_connect_all")
        except Exception as e:
            log.warning("Provider-Direktive konnte nicht gesetzt werden: %s", e)

    async def bootstrap_providers(self):
        if not getattr(self.cfg, "auto_provision_providers", True):
            return
        if not self.cfg.browser_automation:
            return
        self._ensure_provider_connect_directive()
        try:
            from browser import get_browser
            result = await get_browser().auto_provision_providers(
                provision_all=getattr(self.cfg, "auto_provision_all_providers", True),
            )
            if result.get("results"):
                if result.get("ok"):
                    log.info(
                        "Provider-Bootstrap: %s/%s verbunden | versucht=%s",
                        result.get("provisioned", 0),
                        len(result.get("attempted") or []),
                        result.get("attempted"),
                    )
                else:
                    log.warning("Provider-Bootstrap ohne Erfolg: %s", result)
            elif result.get("message"):
                log.info("Provider-Bootstrap: %s", result.get("message"))
        except Exception as e:
            log.warning("Provider-Bootstrap fehlgeschlagen: %s", e)

    async def maintain_provider_keys(self):
        if not getattr(self.cfg, "auto_provision_providers", True):
            return
        if not self.cfg.browser_automation:
            return
        try:
            from browser import get_browser
            missing = get_browser().providers_needing_provision()
            if not missing:
                return
            await get_browser().auto_provision_providers(
                missing,
                provision_all=getattr(self.cfg, "auto_provision_all_providers", True),
            )
        except Exception as e:
            log.debug("Provider-Wartung übersprungen: %s", e)

    async def _auto_provision_providers(self, provider_ids: Optional[list[str]] = None) -> dict:
        from browser import get_browser
        cfg = getattr(self, "cfg", None) or get_config()
        return await get_browser().auto_provision_providers(
            provider_ids,
            provision_all=getattr(cfg, "auto_provision_all_providers", True),
        )

    def _normalize_browser_target(self, target: str) -> str:
        raw = (target or "").strip().strip("\"'")
        if not raw:
            raise ValueError("Leeres Browser-Ziel")
        if raw.startswith(("http://", "https://")):
            return raw
        known = {
            "github": "https://github.com",
            "google": "https://www.google.com",
            "openrouter": "https://openrouter.ai",
            "groq": "https://console.groq.com",
            "wikipedia": "https://de.wikipedia.org",
        }
        key = raw.lower().split("/")[0].split()[0]
        if key in known:
            return known[key]
        if "." in key or key == "localhost":
            return f"https://{raw}"
        return f"https://{raw}.com"

    def _parse_simple_browser_request(self, text: str) -> Optional[dict[str, Any]]:
        raw = (text or "").strip()
        lower = raw.lower()
        if lower.startswith("browser:"):
            body = raw.split(":", 1)[1].strip()
            if body.startswith("{") or "|" in body:
                return None
            return {
                "instance_id": "quick-browse",
                "url": self._normalize_browser_target(body),
                "name": "Quick Browse",
                "extract": True,
            }
        for prefix in ("browser auf ", "öffne im browser ", "navigiere zu "):
            if lower.startswith(prefix):
                target = raw[len(prefix):].strip()
                return {
                    "instance_id": "quick-browse",
                    "url": self._normalize_browser_target(target),
                    "name": "Quick Browse",
                    "extract": True,
                }
        return None

    def _parse_browser_action(self, raw: str) -> dict[str, Any]:
        chunk = (raw or "").strip()
        lower = chunk.lower()
        if not chunk:
            raise ValueError("Leere Browser-Aktion")
        if lower.startswith("wait "):
            return {"action": "wait", "seconds": float(chunk.split(" ", 1)[1].replace(",", "."))}
        if lower.startswith("press "):
            return {"action": "press", "key": chunk.split(" ", 1)[1].strip()}
        if lower.startswith("click "):
            target = chunk.split(" ", 1)[1].strip()
            if target.startswith("#") or target.startswith(".") or "[" in target:
                return {"action": "click", "selector": target}
            return {"action": "click", "text": target}
        if lower.startswith("fill "):
            body = chunk.split(" ", 1)[1].strip()
            left, right = [part.strip() for part in body.split("=", 1)]
            if left.startswith("#") or left.startswith(".") or "[" in left:
                return {"action": "fill", "selector": left, "value": right}
            return {"action": "fill", "text": left, "value": right}
        if lower.startswith("extract_value "):
            body = chunk.split(" ", 1)[1].strip()
            left, right = [part.strip() for part in body.split("->", 1)]
            return {"action": "extract_value", "selector": left, "save_as": right}
        if lower.startswith("extract "):
            body = chunk.split(" ", 1)[1].strip()
            left, right = [part.strip() for part in body.split("->", 1)]
            return {"action": "extract_text", "selector": left, "save_as": right}
        if lower.startswith("store_secret "):
            body = chunk.split(" ", 1)[1].strip()
            left, right = [part.strip() for part in body.split("->", 1)]
            return {"action": "store_secret", "from_var": left, "ref": right}
        raise ValueError(f"Unbekannte Browser-Aktion: {chunk}")

    def _parse_browser_request(self, text: str) -> dict[str, Any]:
        body = (text or "").split(":", 1)[1].strip()
        if body.startswith("{"):
            data = json.loads(body)
            return {
                "instance_id": data.get("instance_id") or data.get("instance") or "browser-task",
                "url": data.get("url") or "",
                "name": data.get("name") or "Browser Task",
                "actions": list(data.get("actions") or []),
            }
        parts = [part.strip() for part in body.split("|")]
        if len(parts) < 3:
            raise ValueError("Format: browser: INSTANCE_ID | URL | action1; action2; ...")
        actions = [self._parse_browser_action(item.strip()) for item in parts[2].split(";") if item.strip()]
        return {
            "instance_id": parts[0] or "browser-task",
            "url": parts[1],
            "name": parts[0] or "Browser Task",
            "actions": actions,
        }

    async def _handle_browser_request(self, text: str) -> str:
        from browser import get_browser

        if not self.cfg.browser_automation:
            return "[Browser] Browser-Automation ist im Runtime-Setting deaktiviert."

        simple = self._parse_simple_browser_request(text)
        if simple:
            actions = [{"action": "goto", "url": simple["url"]}]
            if simple.get("extract"):
                actions.append({
                    "action": "extract_text",
                    "selector": "body",
                    "save_as": "page_text",
                })
            result = await get_browser().run_flow(
                simple["instance_id"],
                simple["url"],
                actions,
                name=simple.get("name") or "Quick Browse",
            )
            if result.get("ok"):
                excerpt = (result.get("memory") or {}).get("page_text", "")[:3500]
                return (
                    f"[Browser] {simple['url']}\n"
                    f"Aktuelle URL: {result.get('current_url', simple['url'])}\n\n"
                    f"{excerpt or '(kein Seiteninhalt extrahiert)'}"
                )
            return (
                f"[Browser] Navigation fehlgeschlagen: {result.get('error', 'unbekannt')}\n"
                f"URL: {result.get('current_url', simple['url'])}"
            )

        if self._is_provider_provision_request(text):
            provider_id = self._resolve_provider_provision_target(text) or "all"
            if provider_id in {"", "auto", "alle", "all"}:
                result = await get_browser().auto_provision_providers(
                    provision_all=True,
                )
            else:
                result = await get_browser().provision_provider_token(provider_id)
            if result.get("results"):
                lines = [
                    f"- {item.get('provider_id')}: "
                    f"{'verbunden (' + str(item.get('token_preview', 'ok')) + ')' if item.get('ok') else item.get('error', 'fehlgeschlagen')}"
                    for item in result.get("results", [])
                ]
                summary = (
                    f"[Browser] Provider-Provisioning: {result.get('provisioned', 0)} verbunden, "
                    f"{result.get('failed', 0)} fehlgeschlagen.\n"
                )
                return summary + "\n".join(lines)
            if result.get("ok"):
                return (
                    f"[Browser] {result.get('provider_id', provider_id)}-Token erzeugt und verbunden.\n"
                    f"Ref: {result.get('secret_ref')}\n"
                    f"Preview: {result.get('token_preview')}\n"
                    f"URL: {result.get('current_url')}"
                )
            return f"[Browser] Provider-Provisioning fehlgeschlagen: {result.get('error', 'unbekannt')}"

        try:
            spec = self._parse_browser_request(text)
        except Exception as e:
            return (
                "[Browser] Ungültiger Browser-Befehl.\n"
                "Format: browser: INSTANCE_ID | URL | click Settings; wait 1; extract #token -> token\n"
                f"Fehler: {e}"
            )

        result = await get_browser().run_flow(
            spec["instance_id"],
            spec["url"],
            spec["actions"],
            name=spec.get("name") or spec["instance_id"],
        )
        if result.get("ok"):
            return (
                f"[Browser] Flow abgeschlossen: {result.get('instance_id')}\n"
                f"URL: {result.get('current_url')}\n"
                f"Steps: {len(result.get('steps') or [])}\n"
                f"Memory: {list((result.get('memory') or {}).keys())}"
            )
        return (
            f"[Browser] Flow fehlgeschlagen: {result.get('error', 'unbekannt')}\n"
            f"URL: {result.get('current_url', '-')}"
        )

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


    def _looks_like_explicit_command(self, user_input: str, intent: str) -> bool:
        text = (user_input or "").strip().lower()
        explicit_prefixes = {
            Intent.SUDO_OPEN: ("sudo ", "öffne tür", "master key"),
            Intent.SUDO_CLOSE: ("sudo close", "tür schließen"),
            Intent.FACT_SET: ("korrektur:", "fakt:", "weiß:"),
            Intent.DIRECTIVE: ("direktive:", "immer:", "niemals:"),
            Intent.BROADCAST: ("broadcast:", "alle instanzen:", "frage alle"),
            Intent.SPLIT: ("split:", "aufteilen:"),
            Intent.PIPELINE: ("pipeline:", "verbessere iterativ"),
            Intent.DECOMPOSE: ("atomisiere:", "verteile:"),
            Intent.CODE: ("code:", "programmiere:", "schreibe python", "schreibe bitte python"),
            Intent.FILE: ("datei:", "lese:", "schreibe datei:", "schreibe eine datei"),
            Intent.TRANSLATE: ("übersetze:", "übersetze ", "translate:", "translate ", "schrift:"),
            Intent.LOGIN_ADD: ("login:", "credential:", "zugangsdaten:"),
            Intent.URL_ADD: ("url:", "instanz:", "füge"),
            Intent.KI_STATUS: ("ki status", "instanzen", "meinungen"),
            Intent.MEINUNG: ("meinung:", "was denkst du über", "isaac meinung"),
            Intent.PAUSE: ("pause", "stopp"),
            Intent.RESUME: ("weiter", "fortsetzen"),
            Intent.CANCEL: ("abbrechen ",),
        }
        prefixes = explicit_prefixes.get(intent, ())
        if intent == Intent.URL_ADD:
            return text.startswith("url:") or text.startswith("instanz:") or (text.startswith("füge") and "url" in text)
        return any(text.startswith(prefix) for prefix in prefixes)

    def _tool_request_intent(self, user_input: str) -> str:
        tl = (user_input or "").lower().strip()
        if tl.startswith(("recherche:", "recherchiere:")):
            return Intent.RESEARCH
        if (
            tl.startswith(("browser:", "browser auf", "öffne im browser", "navigiere zu"))
            or self._is_browser_request(user_input)
        ):
            return Intent.BROWSER
        return Intent.SEARCH

    def _resolve_intent_from_classification(
        self, user_input: str, detected_intent: str, interaction_class: str
    ) -> str:
        # Klassifikation ist die primäre Routing-Authority.
        if interaction_class == InteractionClass.STATUS_QUERY:
            return Intent.STATUS
        if interaction_class == InteractionClass.TOOL_REQUEST:
            tl = (user_input or "").lower().strip()
            if tl.startswith(("agent:", "agent ", "oberfläche:", "oberflaeche:")):
                return Intent.AGENT
            if detected_intent == Intent.AGENT:
                return Intent.AGENT
            return self._tool_request_intent(user_input)

        # Regex-Intent bleibt nur für explizite Kommandos als Fallback aktiv.
        if detected_intent != Intent.CHAT and self._looks_like_explicit_command(user_input, detected_intent):
            return detected_intent

        return Intent.CHAT

    def _retrieve_relevant_context(
        self, user_input: str, intent: str, interaction_class: str
    ) -> dict[str, Any]:
        from self_model_hooks import enrich_retrieval_with_self_model

        retrieval_ctx = self.memory.build_retrieval_context(
            user_input=user_input,
            intent=intent,
            interaction_class=interaction_class,
            n_history=6,
        ).as_dict()
        return enrich_retrieval_with_self_model(retrieval_ctx)

    def _select_response_strategy(
        self, user_input: str, intent: str, interaction_class: str, retrieval_ctx: dict[str, Any]
    ) -> Strategy:
        cfg = getattr(self, "cfg", None) or get_config()
        allow_tools = intent in (Intent.SEARCH, Intent.RESEARCH)
        allow_followup = interaction_class not in ("SHORT_CLARIFICATION",)
        allow_provider_switch = True
        style_note = ""
        risk_tags = {
            tag
            for risk in retrieval_ctx.get("behavioral_risks", [])
            for tag in risk.get("risks", [])
        }
        pref_text = " ".join(
            f"{p.get('text', '')} {p.get('value', '')}".lower()
            for p in retrieval_ctx.get("preferences_context", [])
        )

        if intent == Intent.CHAT:
            allow_tools = False
        if "tool_overreach_risk" in risk_tags and intent == Intent.CHAT:
            allow_tools = False
        if "no auto-agreement" in pref_text or "kein auto agreement" in pref_text:
            style_note += "\n[Antwortstil] Stimme nicht automatisch zu; bleibe begründet und nüchtern."
        if retrieval_ctx.get("project_context"):
            style_note += "\n[Projektkontext] Antwort soll routing- und stabilitätsfokussiert bleiben."
        if "quality_regression_risk" in risk_tags and intent == Intent.CHAT:
            allow_provider_switch = False

        if cfg.style_mode == "light_sarcastic":
            if self._should_allow_light_sarcasm(user_input, intent, interaction_class):
                if self._light_sarcasm_triggered(user_input):
                    style_note += (
                        "\n[Antwortstil] Nach der Lösung ist maximal ein kurzer trockener, leicht "
                        "sarkastischer Kommentar erlaubt."
                    )
                else:
                    style_note += "\n[Antwortstil] Bleibe knapp, direkt und rein sachlich."
            else:
                style_note += "\n[Antwortstil] Kein Sarkasmus in dieser Antwort."

        # Kürzeste Klärungen ohne Eskalation.
        if interaction_class in ("SHORT_CLARIFICATION",):
            allow_followup = False
            allow_provider_switch = False
        return Strategy(
            allow_tools=allow_tools,
            allow_followup=allow_followup,
            allow_provider_switch=allow_provider_switch,
            style_note=style_note,
        )

    def _should_allow_light_sarcasm(self, user_input: str, intent: str, interaction_class: str) -> bool:
        text = (user_input or "").lower()
        if intent in (Intent.SUDO_OPEN, Intent.SUDO_CLOSE, Intent.CODE, Intent.FILE):
            return False
        if interaction_class in ("STATUS_QUERY", "SHORT_CLARIFICATION"):
            return False
        blocked_markers = (
            "security", "sicher", "passwort", "token", "api key", "credential", "berechtigung",
            "debug", "traceback", "stacktrace", "exception", "crash", "fehler", "failed", "timeout",
            "panic", "kaputt", "not working", "funktioniert nicht",
        )
        if any(marker in text for marker in blocked_markers):
            return False
        return True

    @staticmethod
    def _light_sarcasm_triggered(user_input: str) -> bool:
        digest = hashlib.blake2s((user_input or "").encode("utf-8", errors="ignore"), digest_size=2).digest()
        return (int.from_bytes(digest, "big") % 4) == 0

    def _format_retrieval_context(self, retrieval_ctx: dict[str, Any]) -> str:
        return self.memory.format_retrieval_context(retrieval_ctx)

    # ── System-Prompt ─────────────────────────────────────────────────────────
    def _build_system(self, sudo_aktiv: bool, emp,
                      wissen_kontext: str = "",
                      strategy_note: str = "") -> str:
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
        if strategy_note:
            basis += f"\n{strategy_note}"

        cfg = getattr(self, "cfg", None) or get_config()
        if cfg.style_mode == "professional":
            basis += (
                "\n[Stilmodus] professional: Antworte klar, präzise, lösungsorientiert. "
                "Keine Ironie oder Sarkasmus."
            )
        else:
            basis += (
                "\n[Stilmodus] light_sarcastic: Antworte primär direkt, kompetent und hilfreich. "
                "Gelegentlich ist ein kurzer trockener Seitenhieb erlaubt, aber nie überdreht. "
                "Kein Sarkasmus bei Fehlerfrust, Sicherheitsthemen oder komplexem Debugging."
            )

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
    asyncio.create_task(kernel.bootstrap_providers())

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
