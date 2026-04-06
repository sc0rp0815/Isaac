"""
Isaac – Executor v2.0
=======================
Task-Engine. Vollständig async. Keine blockierenden Calls.

Korrekturen gegenüber v1:
  - asyncio.create_subprocess_exec statt subprocess.run (Event Loop safe)
  - Task-Persistenz in SQLite (überleben Neustarts)
  - Watchdog-Integration (Hang-Detection, Neustart)
  - Dispatcher-Integration (Multi-KI-Verteilung)
  - Pre-Flight-Validation vor Ausführung
  - Korrekte Callback-Sicherheit (asyncio.create_task nur im Event Loop)
"""

import asyncio
import time
import re
import uuid
import json
import logging
import ast
import os
import tempfile
from pathlib import Path
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Callable, Any

from config    import get_config, WORKSPACE, Level
from privilege import get_gate, isaac_ctx, task_ctx
from audit     import AuditLog
from logic     import get_logic, QualityScore, FollowUpDecision
from relay     import get_relay
from tool_runtime import select_live_tool_for_task, run_selected_tool
from task_tool_state import get_task_tool_state_store
from low_complexity import is_low_complexity_local_input

log = logging.getLogger("Isaac.Executor")

_ALLOWED_IMPORTS = {"math", "json", "random", "statistics", "collections", "itertools", "functools", "datetime"}
_FORBIDDEN_NAMES = {"eval", "exec", "compile", "open", "input", "breakpoint", "help", "__import__"}
_FORBIDDEN_ATTRS = {"system", "popen", "spawn", "remove", "unlink", "rmtree", "kill", "fork", "chmod", "chown"}


def _normalize_code(raw: str) -> str:
    raw = re.sub(r"```python\n?", "", raw)
    raw = re.sub(r"```\n?", "", raw)
    return raw.strip()


def _fingerprint(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())[:800]


def _limit_subprocess_resources():
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_CPU, (5, 5))
        resource.setrlimit(resource.RLIMIT_FSIZE, (1_000_000, 1_000_000))
        resource.setrlimit(resource.RLIMIT_NOFILE, (16, 16))
        resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024))
    except Exception:
        pass


def _validate_generated_code(code: str) -> tuple[bool, str]:
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return False, f"Syntaxfehler im generierten Code: {e.msg}"

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [alias.name.split(".", 1)[0] for alias in node.names]
            if any(name not in _ALLOWED_IMPORTS for name in names):
                return False, f"Import nicht erlaubt: {', '.join(names)}"
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in _FORBIDDEN_NAMES:
                return False, f"Aufruf nicht erlaubt: {node.func.id}()"
            if isinstance(node.func, ast.Attribute) and node.func.attr in _FORBIDDEN_ATTRS:
                return False, f"Attribut nicht erlaubt: .{node.func.attr}"
        elif isinstance(node, ast.Attribute) and node.attr.startswith('__'):
            return False, "Dunder-Zugriff nicht erlaubt"
    return True, ""


class TaskStatus(Enum):
    QUEUED     = "queued"
    RUNNING    = "running"
    EVALUATING = "evaluating"
    FOLLOWUP   = "followup"
    DONE       = "done"
    FAILED     = "failed"
    CANCELLED  = "cancelled"


class TaskType(Enum):
    CHAT       = "chat"
    SEARCH     = "search"
    ANALYSIS   = "analysis"
    TRANSLATE  = "translate"
    CODE       = "code"
    PLAN       = "plan"
    FILE       = "file"
    AGGREGATE  = "aggregate"
    BROADCAST  = "broadcast"   # Multi-KI
    SPLIT      = "split"       # Multi-KI aufgeteilt
    PIPELINE   = "pipeline"    # Multi-KI iterativ


@dataclass
class Task:
    id:            str
    typ:           TaskType
    prompt:        str
    beschreibung:  str
    prioritaet:    float = 5.0
    provider:      Optional[str] = None
    parent_id:     Optional[str] = None
    system_prompt: str           = ""
    sudo_aktiv:    bool          = False   # SUDO-Modus

    status:        TaskStatus = TaskStatus.QUEUED
    iteration:     int        = 0
    erstellt:      str        = field(default_factory=lambda: time.strftime("%Y-%m-%d %H:%M:%S"))
    gestartet:     str        = ""
    abgeschlossen: str        = ""
    antwort:       str        = ""
    provider_used: str        = ""
    score:         Optional[QualityScore] = None
    followup:      Optional[FollowUpDecision] = None
    fehler:        str        = ""
    sub_task_ids:  list       = field(default_factory=list)
    dauer_sek:     float      = 0.0
    progress:      float      = 0.0
    log_entries:   list       = field(default_factory=list)
    used_tools:    list       = field(default_factory=list)
    tool_strategy: dict       = field(default_factory=dict)

    # Watchdog
    _last_watchdog_progress: float = 0.0

    def log(self, msg: str):
        self.log_entries.append({"ts": time.strftime("%H:%M:%S"), "msg": msg})
        if len(self.log_entries) > 50:
            self.log_entries = self.log_entries[-50:]

    def to_dict(self) -> dict:
        return {
            "id":            self.id,
            "typ":           self.typ.value,
            "beschreibung":  self.beschreibung,
            "prioritaet":    self.prioritaet,
            "status":        self.status.value,
            "iteration":     self.iteration,
            "erstellt":      self.erstellt,
            "gestartet":     self.gestartet,
            "abgeschlossen": self.abgeschlossen,
            "provider":      self.provider_used or self.provider or "auto",
            "score":         round(self.score.total, 2) if self.score else None,
            "score_detail":  self.score.as_dict() if self.score else None,
            "followup_mode": self.followup.mode if self.followup else None,
            "parent_id":     self.parent_id,
            "sub_tasks":     len(self.sub_task_ids),
            "dauer":         round(self.dauer_sek, 2),
            "progress":      round(self.progress, 3),
            "antwort_kurz":  self.antwort[:200] if self.antwort else "",
            "fehler":        self.fehler[:100] if self.fehler else "",
            "log":           self.log_entries[-10:],
            "used_tools":    self.used_tools[-8:],
            "tool_strategy": self.tool_strategy or {},
            "sudo":          self.sudo_aktiv,
        }


class Executor:
    def __init__(self):
        self._tasks:    dict[str, Task]          = {}
        self._queue:    asyncio.PriorityQueue    = asyncio.PriorityQueue()
        self._running:  set[str]                 = set()
        self._callbacks: list[Callable]          = []
        self._loop:     Optional[asyncio.AbstractEventLoop] = None
        self.logic      = get_logic()
        self.relay      = get_relay()
        self.gate       = get_gate()
        self._watchdog  = None   # lazy
        self._dispatcher= None   # lazy
        self._search    = None   # lazy
        self._tool_state = get_task_tool_state_store()
        self._load_persisted_tasks()
        log.info("Executor v2.0 online")

    def _get_watchdog(self):
        if not self._watchdog:
            from watchdog import get_watchdog
            self._watchdog = get_watchdog()
            self._watchdog.set_executor(self)
        return self._watchdog

    def _get_dispatcher(self):
        if not self._dispatcher:
            from dispatcher import get_dispatcher
            self._dispatcher = get_dispatcher()
        return self._dispatcher

    def _get_search(self):
        if not self._search:
            from search import get_search
            self._search = get_search()
        return self._search

    # ── Task erstellen ─────────────────────────────────────────────────────────
    def create_task(self, typ: TaskType, prompt: str,
                    beschreibung: str = "", prioritaet: float = 5.0,
                    provider: Optional[str] = None,
                    parent_id: Optional[str] = None,
                    system_prompt: str = "",
                    sudo_aktiv: bool = False) -> Task:
        task = Task(
            id            = self.next_task_id(),
            typ           = typ,
            prompt        = prompt,
            beschreibung  = beschreibung or prompt[:80],
            prioritaet    = prioritaet,
            provider      = provider,
            parent_id     = parent_id,
            system_prompt = system_prompt,
            sudo_aktiv    = sudo_aktiv,
        )
        self._tasks[task.id] = task
        AuditLog.task(task.id, "created", task.beschreibung[:100])
        return task


    def next_task_id(self) -> str:
        return uuid.uuid4().hex[:8]

    async def submit(self, task: Task) -> Task:
        await self._queue.put((-task.prioritaet, task.id))
        task.log("In Queue")
        self._notify(task)
        return task

    async def submit_and_wait(self, task: Task,
                              timeout: float = 180.0) -> Task:
        await self.submit(task)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if task.status in (TaskStatus.DONE, TaskStatus.FAILED,
                               TaskStatus.CANCELLED):
                return task
            await asyncio.sleep(0.3)
        task.status = TaskStatus.FAILED
        task.fehler = "Timeout"
        return task

    # ── Worker ────────────────────────────────────────────────────────────────
    async def start_worker(self, concurrency: int = 4):
        self._loop = asyncio.get_running_loop()
        log.info(f"Worker gestartet (concurrency={concurrency})")
        sem = asyncio.Semaphore(concurrency)

        # Watchdog starten
        await self._get_watchdog().start()

        async def _run():
            while True:
                try:
                    _, task_id = await asyncio.wait_for(
                        self._queue.get(), timeout=5.0
                    )
                    task = self._tasks.get(task_id)
                    if task and task.status == TaskStatus.QUEUED:
                        self._running.add(task_id)
                        asyncio.create_task(self._with_sem(task, sem))
                except asyncio.TimeoutError:
                    pass
                except Exception as e:
                    log.error(f"Worker: {e}")

        asyncio.create_task(_run())

    async def _with_sem(self, task: Task, sem: asyncio.Semaphore):
        async with sem:
            await self._execute(task)
        self._running.discard(task.id)

    # ── Pre-Flight-Validation ─────────────────────────────────────────────────
    def _preflight(self, task: Task) -> Optional[str]:
        """
        Prüft einen Task bevor er ausgeführt wird.
        Gibt None zurück wenn OK, sonst Fehlermeldung.
        Wenn SUDO aktiv: Steffen's Befehl — immer OK.
        """
        if task.sudo_aktiv:
            return None  # Steffen hat autorisiert. Keine weitere Prüfung.

        wortanzahl = len(task.prompt.split())
        if wortanzahl < 1:
            return "Leerer Prompt"

        return None

    # ── Haupt-Execute ─────────────────────────────────────────────────────────
    async def _execute(self, task: Task):
        preflight_fehler = self._preflight(task)
        if preflight_fehler:
            task.status = TaskStatus.FAILED
            task.fehler = preflight_fehler
            self._notify(task)
            return

        task.status    = TaskStatus.RUNNING
        task.gestartet = time.strftime("%Y-%m-%d %H:%M:%S")
        task.progress  = 0.1
        t0             = time.monotonic()
        task.log(f"Start │ {task.typ.value} │ sudo={task.sudo_aktiv}")
        state = self._tool_state.get_or_create(task.id, task.prompt)
        if state.status not in ("idle", "done", "failed"):
            self._tool_state.mark_resume(task.id)
        self._tool_state.set_status(task.id, "running")
        task.tool_strategy = self._tool_state.get_or_create(task.id).to_dict()
        self._notify(task)
        AuditLog.task(task.id, "running", task.beschreibung[:80])

        try:
            if task.typ == TaskType.FILE:
                await self._execute_file(task)
            elif task.typ == TaskType.CODE:
                await self._execute_code(task)
            elif task.typ == TaskType.SEARCH:
                await self._execute_search(task)
            elif task.typ in (TaskType.BROADCAST, TaskType.SPLIT,
                              TaskType.PIPELINE):
                await self._execute_multi_ki(task)
            else:
                await self._execute_ai(task)
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.fehler = str(e)[:200]
            task.log(f"Fehler: {e}")
            AuditLog.error("Executor", str(e), f"task={task.id}")
        finally:
            task.dauer_sek     = round(time.monotonic() - t0, 2)
            task.abgeschlossen = time.strftime("%Y-%m-%d %H:%M:%S")
            task.progress      = 1.0
            self._tool_state.set_status(task.id, task.status.value)
            task.tool_strategy = self._tool_state.get_or_create(task.id).to_dict()
            self._persist_task(task)
            self._notify(task)

    def _should_try_tool(self, task: Task, prompt: str, iteration: int) -> bool:
        if task.typ in (TaskType.FILE, TaskType.BROADCAST, TaskType.SPLIT, TaskType.PIPELINE):
            return False
        if task.typ == TaskType.CHAT and is_low_complexity_local_input(prompt):
            return False
        p = (prompt or '').lower()
        hotwords = ("suche", "search", "recherche", "internet", "web", "browser", "github", "api", "tool", "mcp", "wetter", "resource", "datei")
        return iteration == 0 or any(hw in p for hw in hotwords)

    def _tool_context_block(self, tool_name: str, tool_kind: str, via: str, result: dict) -> str:
        content = (result.get('content') or result.get('error') or '').strip()[:2200]
        return (
            "\n\n[Tool-Kontext]\n"
            f"Tool: {tool_name}\n"
            f"Typ: {tool_kind} via {via}\n"
            f"Ergebnis:\n{content}\n"
            "[/Tool-Kontext]"
        )

    async def _maybe_use_tool(self, task: Task, prompt: str, iteration: int, used_tool_ids: set[str]) -> tuple[str, str]:
        if not self._should_try_tool(task, prompt, iteration):
            return "", ""
        selection = await select_live_tool_for_task(task, prompt, iteration)
        if not selection or selection.get("identifier") in used_tool_ids:
            return "", ""
        task.log(f"Tool-Auswahl: {selection.get('name')} [{selection.get('kind')}/{selection.get('category')}]")
        self._notify(task)
        result = await run_selected_tool(selection, prompt)
        identifier = selection.get("identifier", "")
        name = selection.get("name", identifier)
        kind = selection.get("kind", "")
        category = selection.get("category", "general")
        via = result.get('via') or selection.get('source') or kind
        self._tool_state.record_call(
            task.id, source=selection.get("source", "unknown"), identifier=identifier, name=name,
            feature_type=selection.get("mcp_feature", "tool"), ok=bool(result.get('ok')), category=category,
            kind=kind, note=result.get('error', '') or result.get('via', ''), status_code=result.get('status_code'),
            output=result.get('content', '') or result.get('error', '')
        )
        task.tool_strategy = self._tool_state.get_or_create(task.id).to_dict()
        if not result.get('ok'):
            task.log(f"Tool fehlgeschlagen: {name} – {result.get('error', 'unbekannt')}")
            return "", ""
        used_tool_ids.add(identifier)
        tool_note = {
            "tool_id": identifier,
            "name": name,
            "kind": kind,
            "category": category,
            "via": via,
            "status_code": result.get('status_code'),
            "source": selection.get('source'),
        }
        task.used_tools.append(tool_note)
        task.used_tools = task.used_tools[-12:]
        task.log(f"Tool genutzt: {name}")
        AuditLog.action("Executor", "tool_used", f"task={task.id} tool={name}", Level.ISAAC)
        next_input = self._tool_state.generate_next_input(task.id, task.prompt, name, result.get('content', '') or '')
        return self._tool_context_block(name, kind, via, result), next_input

    # ── AI-Task ───────────────────────────────────────────────────────────────
    async def _execute_ai(self, task: Task):
        system = self._build_system(task)
        current_prompt = task.prompt
        current_prov = task.provider
        antwort = ""
        last_score_total = -1.0
        stale_rounds = 0
        seen_answers: set[str] = set()
        used_tool_ids: set[str] = set()

        for iteration in range(get_config().logic.max_followup_rounds + 1):
            if task.status == TaskStatus.CANCELLED:
                task.log("Vor Ausführung abgebrochen")
                return

            task.iteration = iteration
            task.progress = 0.1 + (iteration / (get_config().logic.max_followup_rounds + 1)) * 0.7
            task.status = TaskStatus.RUNNING
            task.log(f"Iter {iteration}: → {current_prov or 'auto'}")
            self._notify(task)

            tool_context, generated_next_input = await self._maybe_use_tool(task, current_prompt, iteration, used_tool_ids)
            effective_prompt = current_prompt + tool_context if tool_context else current_prompt
            antwort, prov = await self.relay.ask_with_fallback(
                effective_prompt, system, preferred=current_prov, task_id=task.id
            )
            task.provider_used = prov

            if task.status == TaskStatus.CANCELLED:
                task.log("Während Provider-Aufruf abgebrochen")
                return

            fp = _fingerprint(antwort)
            if fp in seen_answers and iteration > 0:
                task.log("Loop-Schutz: identische Antwort erkannt")
                break
            seen_answers.add(fp)

            if antwort.startswith("[RELAY") and iteration >= 1:
                task.log("Loop-Schutz: wiederholter Relay-Fehler")
                task.status = TaskStatus.FAILED
                task.fehler = antwort[:200]
                return

            self._get_watchdog().record_progress(task.id)

            task.status = TaskStatus.EVALUATING
            score = self.logic.evaluate(antwort, task.prompt, task.id)
            task.score = score
            task.log(f"Score: {score.summary()}")
            self._notify(task)

            if score.total <= last_score_total + 0.2:
                stale_rounds += 1
            else:
                stale_rounds = 0
            last_score_total = score.total

            if score.acceptable or iteration >= get_config().logic.max_followup_rounds:
                break

            # Kein Follow-up/Provider-Switching für triviale Kurz-Chats.
            if task.typ == TaskType.CHAT and is_low_complexity_local_input(task.beschreibung):
                break

            decision = self.logic.decide_followup(antwort, task.prompt, score, iteration, prov, task.id)
            task.followup = decision
            task.status = TaskStatus.FOLLOWUP
            task.log(f"Nachfrage: {decision.mode} – {decision.reason}")
            self._notify(task)

            if not decision.needed:
                break

            if stale_rounds >= 2:
                task.log("Loop-Schutz: Qualität verbessert sich nicht weiter")
                break

            if decision.mode == "decompose" and decision.sub_tasks:
                results = await self._execute_sub_tasks(task, decision.sub_tasks, prov)
                antwort = self._aggregate(results)
                break

            if decision.switch_provider or stale_rounds >= 1:
                from watchdog import get_blacklist
                ranked = [p for p in get_blacklist().ranked_providers(prov) if p != prov]
                if ranked:
                    current_prov = ranked[0]
                    task.log(f"Provider: {prov} → {current_prov}")

            queued_next_input = self._tool_state.pop_next_input(task.id)
            if generated_next_input and not queued_next_input:
                queued_next_input = generated_next_input
            if queued_next_input:
                current_prompt = queued_next_input
                task.log("Nächster Input aus Tool-Ergebnis generiert")
            elif decision.followup_prompt:
                current_prompt = decision.followup_prompt

            task.tool_strategy = self._tool_state.get_or_create(task.id).to_dict()
            await asyncio.sleep(get_config().relay.min_interval)

        task.tool_strategy = self._tool_state.get_or_create(task.id).to_dict()
        if task.used_tools:
            tool_lines = ", ".join(f"{t['name']} ({t['kind']})" for t in task.used_tools[-4:])
            antwort = f"[Tools genutzt: {tool_lines}]\n\n" + antwort
        task.antwort = antwort
        if task.status != TaskStatus.FAILED:
            task.status = TaskStatus.DONE
        AuditLog.task(
            task.id,
            "done" if task.status == TaskStatus.DONE else "failed",
            f"score={task.score.total:.1f} iter={task.iteration+1}" if task.score else f"iter={task.iteration+1}",
            score=task.score.total if task.score else 0.0,
            iteration=task.iteration
        )

    # ── Search-Task ───────────────────────────────────────────────────────────
    async def _execute_search(self, task: Task):
        """Echte Websuche über MultiSearch."""
        task.log("Websuche gestartet")
        search = self._get_search()
        result = await search.search(
            task.prompt,
            max_hits=10,
            load_fulltext=True,
        )
        task.progress = 0.6
        self._notify(task)

        # Suchergebnisse an KI zur Synthese schicken
        kontext = result.als_kontext(max_hits=8)
        synth_prompt = (
            f"Basierend auf diesen Suchergebnissen, beantworte: {task.prompt}\n\n"
            f"Suchergebnisse:\n{kontext}\n\n"
            f"Antworte ausführlich, strukturiert, mit Quellenangaben."
        )
        antwort, prov = await self.relay.ask_with_fallback(
            synth_prompt,
            system="Du bist ein Recherche-Synthesizer. "
                   "Fasse Suchergebnisse zu einer vollständigen Antwort zusammen.",
            task_id=task.id
        )
        task.antwort       = antwort
        task.provider_used = prov
        task.status        = TaskStatus.DONE
        task.score         = self.logic.evaluate(antwort, task.prompt, task.id)
        task.log(f"Suche: {len(result.hits)} Hits aus {result.quellen}")

    # ── Multi-KI-Task ─────────────────────────────────────────────────────────
    async def _execute_multi_ki(self, task: Task):
        """Verteilt Task auf mehrere KI-Instanzen."""
        dispatcher = self._get_dispatcher()
        from browser import get_browser
        browser    = get_browser()
        instance_ids = browser.get_active_ids()

        if not instance_ids:
            # Fallback: API-Provider als "Instanzen"
            instance_ids = get_config().available_providers[:4]

        task.log(f"Multi-KI: {len(instance_ids)} Instanzen")
        self._notify(task)

        system = self._build_system(task)

        if task.typ == TaskType.BROADCAST:
            result = await dispatcher.broadcast(
                task.prompt, instance_ids, system=system
            )
        elif task.typ == TaskType.SPLIT:
            result = await dispatcher.split(
                task.prompt, instance_ids, system=system
            )
        elif task.typ == TaskType.PIPELINE:
            result = await dispatcher.pipeline(
                task.prompt, instance_ids, system=system
            )

        task.antwort = result.final
        task.status  = TaskStatus.DONE
        task.score   = self.logic.evaluate(result.final, task.prompt, task.id)
        task.log(
            f"Multi-KI done: {result.n_instanzen} Instanzen, "
            f"{result.dauer:.1f}s"
        )

    # ── Code-Ausführung (ASYNC, kein blocking!) ───────────────────────────────
    async def _execute_code(self, task: Task):
        """Generiert Python-Code und führt ihn eingeschränkt im Isolated-Mode aus."""
        ctx = isaac_ctx("Executor", f"Code ausführen: task {task.id}")
        self.gate.require("execute_code", ctx)

        code_prompt = (
            f"Schreibe Python-Code für:\n{task.prompt}\n\n"
            "Antworte NUR mit dem Code ohne Erklärungen oder Markdown."
        )
        raw_code, prov = await self.relay.ask_with_fallback(code_prompt, task_id=task.id)
        task.provider_used = prov
        code = _normalize_code(raw_code)

        ok, reason = _validate_generated_code(code)
        if not ok:
            task.antwort = f"[CODE] Geblockt: {reason}"
            task.status = TaskStatus.FAILED
            AuditLog.action("Executor", "code_blocked", reason, Level.ISAAC, erfolg=False)
            return

        exec_dir = WORKSPACE / ".isaac_exec"
        exec_dir.mkdir(parents=True, exist_ok=True)
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile("w", suffix=".py", dir=exec_dir, delete=False, encoding="utf-8") as tmp:
                tmp.write(code)
                tmp_path = Path(tmp.name)

            kwargs = {}
            if os.name != "nt":
                kwargs["preexec_fn"] = _limit_subprocess_resources

            proc = await asyncio.create_subprocess_exec(
                "python3", "-I", "-S", str(tmp_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(WORKSPACE),
                env={"PATH": os.environ.get("PATH", ""), "PYTHONIOENCODING": "utf-8"},
                **kwargs,
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=8.0)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.communicate()
                task.antwort = "[CODE] Timeout (8s)"
                task.status = TaskStatus.FAILED
                return

            output = (stdout.decode(errors="replace") or stderr.decode(errors="replace") or "(kein Output)").strip()
            task.antwort = f"```python\n{code[:700]}\n```\n\n**Output:**\n```\n{output[:1200]}\n```"
            task.status = TaskStatus.DONE if proc.returncode == 0 else TaskStatus.FAILED
            if proc.returncode != 0:
                task.fehler = output[:200]
            AuditLog.system_cmd("Executor", "python3 -I -S [tempfile]", proc.returncode)
        except FileNotFoundError:
            task.antwort = "[CODE] python3 nicht gefunden"
            task.status = TaskStatus.FAILED
        finally:
            if tmp_path:
                try:
                    tmp_path.unlink(missing_ok=True)
                except Exception:
                    pass

    # ── File-Task ────────────────────────────────────────────────────────────
    async def _execute_file(self, task: Task):
        ctx = isaac_ctx("Executor", f"Datei-Op: task {task.id}")
        prompt_lower = task.prompt.lower()

        if "schreibe" in prompt_lower or "write" in prompt_lower:
            self.gate.require("file_write", ctx)

        pfad_match = re.search(r"[\"']([^\"']+)[\"']", task.prompt)
        if not pfad_match:
            task.antwort = "[FILE] Pfad nicht erkannt"
            task.status = TaskStatus.FAILED
            return

        try:
            candidate = (WORKSPACE / pfad_match.group(1).strip()).resolve()
            workspace_root = WORKSPACE.resolve()
            if not candidate.is_relative_to(workspace_root):
                task.antwort = "[FILE] Zugriff außerhalb des Workspace blockiert"
                task.status = TaskStatus.FAILED
                return
        except Exception:
            task.antwort = "[FILE] Ungültiger Pfad"
            task.status = TaskStatus.FAILED
            return

        if "schreibe" in prompt_lower or "write" in prompt_lower:
            content_match = re.search(r'(?:inhalt|content)\s*:\s*(.+)$', task.prompt, re.IGNORECASE | re.S)
            if not content_match:
                task.antwort = "[FILE] Kein Schreibinhalt gefunden. Nutze: inhalt: ..."
                task.status = TaskStatus.FAILED
                return
            candidate.parent.mkdir(parents=True, exist_ok=True)
            candidate.write_text(content_match.group(1).strip(), encoding="utf-8")
            task.antwort = f"[FILE] Gespeichert: {candidate.relative_to(workspace_root)}"
            task.status = TaskStatus.DONE
            return

        if candidate.exists() and candidate.is_file():
            task.antwort = candidate.read_text(encoding="utf-8", errors="replace")[:4000]
            task.status = TaskStatus.DONE
            return

        task.antwort = "[FILE] Datei nicht gefunden"
        task.status = TaskStatus.FAILED

    # ── Sub-Tasks ─────────────────────────────────────────────────────────────
    async def _execute_sub_tasks(self, parent: Task,
                                  sub_prompts: list[str],
                                  provider: Optional[str]) -> list[str]:
        tasks = []
        for prompt in sub_prompts:
            sub = self.create_task(
                typ          = parent.typ,
                prompt       = prompt,
                beschreibung = f"[Sub] {prompt[:60]}",
                prioritaet   = parent.prioritaet + 1,
                provider     = provider,
                parent_id    = parent.id,
                sudo_aktiv   = parent.sudo_aktiv,
            )
            parent.sub_task_ids.append(sub.id)
            tasks.append(sub)
        await asyncio.gather(*[self._execute(t) for t in tasks])
        return [t.antwort for t in tasks if t.antwort]

    def _aggregate(self, results: list[str]) -> str:
        if not results:
            return "[Keine Ergebnisse]"
        if len(results) == 1:
            return results[0]
        return "\n\n---\n\n".join(
            f"**Teil {i+1}:**\n{r}" for i, r in enumerate(results)
        )

    # ── System-Prompt ─────────────────────────────────────────────────────────
    def _build_system(self, task: Task) -> str:
        if task.system_prompt:
            return task.system_prompt
        basis = {
            TaskType.CHAT:      "Du bist Isaac. Antworte vollständig, präzise und strukturiert.",
            TaskType.SEARCH:    "Du bist ein Recherche-Synthesizer. Fasse Suchergebnisse vollständig zusammen.",
            TaskType.ANALYSIS:  "Du bist ein Analyse-Experte. Untersuche systematisch.",
            TaskType.TRANSLATE: "Du bist ein Experte für Sprachen und Schriften. Antworte präzise.",
            TaskType.CODE:      "Du bist ein Programmierer. Schreibe sauberen, lauffähigen Code.",
            TaskType.PLAN:      "Du bist ein strategischer Planer. Erstelle detaillierte Pläne.",
        }
        return basis.get(task.typ, "Du bist Isaac, ein autonomes KI-System.")

    # ── Persistenz ────────────────────────────────────────────────────────────
    def _persist_task(self, task: Task):
        """Speichert abgeschlossene Tasks in SQLite."""
        if task.status not in (TaskStatus.DONE, TaskStatus.FAILED):
            return
        try:
            from memory import get_memory
            get_memory().save_task_result(
                task_id     = task.id,
                description = task.beschreibung[:200],
                result      = task.antwort,
                score       = task.score.total if task.score else 0.0,
                iterations  = task.iteration + 1,
                provider    = task.provider_used,
            )
        except Exception as e:
            log.warning(f"Task-Persistenz: {e}")

    def _load_persisted_tasks(self):
        """Lädt die letzten abgeschlossenen Tasks als Dashboard-Historie."""
        try:
            from memory import _conn
            with _conn() as con:
                rows = con.execute(
                    "SELECT task_id, description, result, score, iterations, provider, ts FROM task_results ORDER BY id DESC LIMIT 50"
                ).fetchall()
            for row in reversed(rows):
                task = Task(
                    id=row["task_id"],
                    typ=TaskType.CHAT,
                    prompt=row["description"],
                    beschreibung=row["description"],
                )
                task.status = TaskStatus.DONE
                task.antwort = row["result"] or ""
                task.provider_used = row["provider"] or ""
                task.iteration = max(0, int((row["iterations"] or 1) - 1))
                task.abgeschlossen = row["ts"] or ""
                self._tasks.setdefault(task.id, task)
        except Exception as e:
            log.debug(f"Task-Historie konnte nicht geladen werden: {e}")

    # ── Callbacks ─────────────────────────────────────────────────────────────
    def register_callback(self, fn: Callable):
        self._callbacks.append(fn)

    def unregister_callback(self, fn: Callable):
        self._callbacks = [c for c in self._callbacks if c != fn]

    def _notify(self, task: Task):
        data = task.to_dict()
        try:
            loop = self._loop or asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        for cb in self._callbacks:
            try:
                if loop and loop.is_running():
                    loop.call_soon_threadsafe(asyncio.create_task, self._safe_cb(cb, data))
                else:
                    result = cb(data)
                    if asyncio.iscoroutine(result):
                        asyncio.run(result)
            except Exception as e:
                log.debug(f"Callback-Fehler: {e}")

    async def _safe_cb(self, cb: Callable, data: dict):
        try:
            result = cb(data)
            if asyncio.iscoroutine(result):
                await result
        except (RuntimeError, ValueError) as e:
            log.debug(f"Callback async Fehler: {e}")

    # ── Abfragen ─────────────────────────────────────────────────────────────
    def get_task(self, task_id: str) -> Optional[Task]:
        return self._tasks.get(task_id)

    def all_tasks(self, limit: int = 200) -> list[dict]:
        return [
            t.to_dict()
            for t in sorted(self._tasks.values(),
                            key=lambda t: t.erstellt, reverse=True)[:limit]
        ]

    def running_tasks(self) -> list[dict]:
        return [
            t.to_dict() for t in self._tasks.values()
            if t.status in (TaskStatus.RUNNING, TaskStatus.EVALUATING,
                            TaskStatus.FOLLOWUP)
        ]

    def queue_size(self) -> int:
        return self._queue.qsize()

    def stats(self) -> dict:
        alle = list(self._tasks.values())
        by_status: dict[str, int] = {}
        for t in alle:
            k = t.status.value
            by_status[k] = by_status.get(k, 0) + 1
        scored = [t.score.total for t in alle if t.score]
        return {
            "total":     len(alle),
            "running":   len(self._running),
            "queue":     self.queue_size(),
            "by_status": by_status,
            "avg_score": round(sum(scored)/len(scored), 2) if scored else 0.0,
        }


_executor: Optional[Executor] = None

def get_executor() -> Executor:
    global _executor
    if _executor is None:
        _executor = Executor()
    return _executor
