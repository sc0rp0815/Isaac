# Plan mode read-only workflow reminder

**Session ID:** ses_26c7d3ff2ffeAe3LpKO89CD1Sl
**Created:** 4/15/2026, 11:38:32 PM
**Updated:** 4/16/2026, 12:17:48 AM

---

## User



---

## Assistant (Plan · GPT-5.3 Codex · 13.9s)

_Thinking:_



Got it — I’m in read-only planning mode and won’t make any changes.

What would you like me to plan?  
If you share the goal (bug, feature, refactor, test gap, etc.), I’ll inspect the codebase and return a concrete execution plan with tradeoffs and recommended path.

---

## User

Analyze the entire Isaac repository.

Focus strictly on real code, not concepts.

Tasks:
- Identify inconsistencies between:
  - isaac_core.py
  - executor.py
  - memory.py
  - tool_runtime.py
- Analyze _should_try_tool behavior and boundaries
- Detect duplicate retrieval/context logic
- Identify conflicts between strategy and legacy allow_* flags
- Highlight unstable execution paths

Constraints:
- No redesign
- No new architecture
- No abstractions
- Stay file-specific and implementation-grounded

Output:
- File-by-file findings
- Concrete defects
- Exact locations
- Prioritized issues 

---

## Assistant (Plan · GPT-5.3 Codex · 12.1s)

_Thinking:_



**Tool: grep**

**Input:**
```json
{
  "pattern": "_should_try_tool|should_try_tool",
  "path": "/root/Isaac",
  "include": "*.py"
}
```

**Output:**
```
Found 5 matches
/root/Isaac/tests_phase_a_stabilization.py:
  Line 66:         self.assertTrue(executor._should_try_tool(task, task.prompt, iteration=2))

  Line 84:         self.assertFalse(executor._should_try_tool(task, task.prompt, iteration=0))

  Line 254:         self.assertFalse(executor._should_try_tool(task, task.prompt, iteration=0))


/root/Isaac/executor.py:
  Line 411:     def _should_try_tool(self, task: Task, prompt: str, iteration: int) -> bool:

  Line 437:         if not self._should_try_tool(task, prompt, iteration):

```

**Tool: grep**

**Input:**
```json
{
  "pattern": "allow_[a-z_]+",
  "path": "/root/Isaac",
  "include": "*.py"
}
```

**Output:**
```
Found 49 matches
/root/Isaac/web_urldispatcher.py:
  Line 1234:         allow_head: bool = True,

  Line 1239:         If allow_head is true, another

  Line 1243:         if allow_head:


/root/Isaac/tests_phase_a_stabilization.py:
  Line 56:             strategy=Strategy(allow_tools=True),

  Line 74:             strategy=Strategy(allow_tools=False),

  Line 230:         self.assertFalse(strategy.allow_tools)

  Line 231:         self.assertTrue(strategy.allow_followup)

  Line 250:             strategy=Strategy(allow_tools=True),

  Line 260:         strategy = Strategy(allow_tools=False, allow_followup=False, allow_provider_switch=False)

  Line 265:             allow_tools=True,

  Line 266:             allow_followup=True,

  Line 267:             allow_provider_switch=True,

  Line 269:         self.assertFalse(task.allow_tools)

  Line 270:         self.assertFalse(task.allow_followup)

  Line 271:         self.assertFalse(task.allow_provider_switch)


/root/Isaac/search.py:
  Line 533:                     allow_redirects=True


/root/Isaac/isaac_core.py:
  Line 795:         allow_tools = intent == Intent.SEARCH

  Line 796:         allow_followup = interaction_class not in ("SHORT_CLARIFICATION",)

  Line 797:         allow_provider_switch = True

  Line 810:             allow_tools = False

  Line 812:             allow_tools = False

  Line 818:             allow_provider_switch = False

  Line 822:             allow_followup = False

  Line 823:             allow_provider_switch = False

  Line 825:             allow_tools=allow_tools,

  Line 826:             allow_followup=allow_followup,

  Line 827:             allow_provider_switch=allow_provider_switch,


/root/Isaac/executor.py:
  Line 113:     allow_tools: bool = True

  Line 114:     allow_followup: bool = True

  Line 115:     allow_provider_switch: bool = True

  Line 120:             "allow_tools": self.allow_tools,

  Line 121:             "allow_followup": self.allow_followup,

  Line 122:             "allow_provider_switch": self.allow_provider_switch,

  Line 198:     def allow_tools(self) -> bool:

  Line 199:         return self.strategy.allow_tools

  Line 202:     def allow_followup(self) -> bool:

  Line 203:         return self.strategy.allow_followup

  Line 206:     def allow_provider_switch(self) -> bool:

  Line 207:         return self.strategy.allow_provider_switch

  Line 262:                     allow_tools: Optional[bool] = None,

  Line 263:                     allow_followup: Optional[bool] = None,

  Line 264:                     allow_provider_switch: Optional[bool] = None,

  Line 268:                 allow_tools=True if allow_tools is None else allow_tools,

  Line 269:                 allow_followup=True if allow_followup is None else allow_followup,

  Line 270:                 allow_provider_switch=True if allow_provider_switch is None else allow_provider_switch,

  Line 272:         elif any(flag is not None for flag in (allow_tools, allow_followup, allow_provider_switch)):

  Line 412:         if not task.allow_tools:

  Line 559:             if not task.allow_followup:

  Line 580:             if task.allow_provider_switch and (decision.switch_provider or stale_rounds >= 1):

```

**Tool: grep**

**Input:**
```json
{
  "pattern": "build_context|retriev|context",
  "path": "/root/Isaac",
  "include": "{isaac_core.py,executor.py,memory.py,tool_runtime.py}"
}
```

**Output:**
```
Found 56 matches
/root/Isaac/memory.py:
  Line 22: from contextlib import contextmanager

  Line 35:     semantic_context: str

  Line 38:     preferences_context: list[dict]

  Line 39:     project_context: list[dict]

  Line 49:             "semantic_context": self.semantic_context,

  Line 52:             "preferences_context": self.preferences_context,

  Line 53:             "project_context": self.project_context,

  Line 131: @contextmanager

  Line 323:     def build_retrieval_context(

  Line 334:         semantic_context = ""

  Line 336:             semantic_context = vector.als_kontext(query) or ""

  Line 375:         project_context = []

  Line 384:                 project_context.append(normalized)

  Line 385:         project_context = project_context[-3:]

  Line 421:             semantic_context=semantic_context.strip(),

  Line 424:             preferences_context=preferences[:4],

  Line 425:             project_context=project_context,

  Line 431:     def format_retrieval_context(self, retrieval_ctx: RetrievalContext | dict[str, Any]) -> str:

  Line 432:         if isinstance(retrieval_ctx, RetrievalContext):

  Line 433:             data = retrieval_ctx.as_dict()

  Line 435:             data = retrieval_ctx or {}

  Line 448:         if data.get("semantic_context"):

  Line 449:             sections.append("[semantic_context]")

  Line 450:             sections.append(data["semantic_context"])

  Line 461:         if data.get("preferences_context"):

  Line 462:             sections.append("[preferences_context]")

  Line 463:             for item in data["preferences_context"]:

  Line 470:         if data.get("project_context"):

  Line 471:             sections.append("[project_context]")

  Line 472:             for item in data["project_context"]:

  Line 489:     def build_context(self, query: str = "", n_history: int = 6) -> str:

  Line 491:         retrieval_ctx = self.build_retrieval_context(query, n_history=n_history)

  Line 492:         return self.format_retrieval_context(retrieval_ctx)


/root/Isaac/isaac_core.py:
  Line 323:         retrieval_ctx = self._retrieve_relevant_context(

  Line 332:             retrieval_ctx=retrieval_ctx,

  Line 348:         structured_ctx = self._format_retrieval_context(retrieval_ctx)

  Line 363:             retrieved_context = retrieval_ctx,

  Line 782:     def _retrieve_relevant_context(

  Line 785:         return self.memory.build_retrieval_context(

  Line 793:         self, user_input: str, intent: str, interaction_class: str, retrieval_ctx: dict[str, Any]

  Line 801:             for risk in retrieval_ctx.get("behavioral_risks", [])

  Line 806:             for p in retrieval_ctx.get("preferences_context", [])

  Line 815:         if retrieval_ctx.get("project_context"):

  Line 831:     def _format_retrieval_context(self, retrieval_ctx: dict[str, Any]) -> str:

  Line 832:         return self.memory.format_retrieval_context(retrieval_ctx)

  Line 852:         direktiven = self.gate.directives_as_context()


/root/Isaac/executor.py:
  Line 158:     retrieved_context: dict   = field(default_factory=dict)

  Line 265:                     retrieved_context: Optional[dict] = None) -> Task:

  Line 287:             retrieved_context = retrieved_context or {},

  Line 423:     def _tool_context_block(self, tool_name: str, tool_kind: str, via: str, result: dict) -> str:

  Line 439:         context_blocks: list[str] = []

  Line 480:             context_blocks.append(self._tool_context_block(name, kind, via, result))

  Line 491:         return "".join(context_blocks), next_input

  Line 515:             tool_context, generated_next_input = await self._maybe_use_tool(task, current_prompt, iteration, used_tool_ids)

  Line 516:             effective_prompt = current_prompt + tool_context if tool_context else current_prompt

  Line 822:                 retrieved_context = parent.retrieved_context,

```

---

## Assistant (Plan · GPT-5.3 Codex · 6.0s)

_Thinking:_



**Tool: read**

**Input:**
```json
{
  "filePath": "/root/Isaac/isaac_core.py",
  "offset": 1,
  "limit": 260
}
```

**Output:**
```
<path>/root/Isaac/isaac_core.py</path>
<type>file</type>
<content>
1: """
2: Isaac – Kernel v5.3
3: =====================
4: Zentraler Orchestrator. Alle 21 Module vollständig integriert.
5: 
6: Pipeline pro Steffen-Input:
7:   1. SUDO-Check
8:   2. Empathie-Analyse (Node-Zustand)
9:   3. Wissensdatenbank konsultieren (KI-Dialog-DB)
10:   4. Intent erkennen
11:   5. Komplexitäts-Routing:
12:        - Einfach  → Standard-Task
13:        - Komplex  → Decomposer (Steffens Prompt nie direkt extern)
14:        - Multi-KI → Dispatcher (Broadcast / Split / Pipeline)
15:   6. Regelwerk analysiert jede Interaktion
16:   7. Offene Fragen des Regelwerks stellen
17:   8. Background-Erkenntnisse einbauen
18:   9. Gedächtnis schreiben + Dashboard pushen
19: 
20: Datenschutz-Garantie:
21:   Steffens originaler Prompt wird NIEMALS direkt an externe KIs gesendet.
22:   Der Decomposer atomisiert jeden Prompt bevor er externe Instanzen erreicht.
23: """
24: 
25: import asyncio
26: import json
27: import re
28: import time
29: import logging
30: from typing import Optional, Any
31: 
32: from config         import get_config, Level, WORKSPACE
33: from privilege      import get_gate, steffen_ctx, isaac_ctx
34: from audit          import AuditLog, setup_privilege_audit
35: from memory         import get_memory
36: from executor       import get_executor, TaskType, TaskStatus, Strategy
37: from relay          import get_relay
38: from logic          import get_logic
39: from empathie       import get_empathie
40: from sudo_gate      import get_sudo
41: from regelwerk      import get_regelwerk
42: from decomposer     import get_decomposer
43: from ki_dialog      import get_ki_dialog
44: from ki_skills      import get_skill_router
45: from monitor_server import get_monitor, set_kernel, DashboardHTTPServer
46: from meaning        import get_meaning
47: from values         import get_values
48: from low_complexity import (
49:     ClassificationResult,
50:     classify_interaction_result,
51:     is_lightweight_local_class,
52:     is_low_complexity_local_input,
53:     local_class_response,
54:     local_fast_response,
55: )
56: 
57: log = logging.getLogger("Isaac.Kernel")
58: 
59: # ── Komplexitätsschwelle für Decomposer ───────────────────────────────────────
60: DECOMPOSE_WORT_SCHWELLE = 15   # Ab 15 Wörtern → Decomposer
61: DECOMPOSE_THEMEN_SCHWELLE = 2  # Ab 2 erkennbaren Themen → Decomposer
62: 
63: 
64: # ── Intents ────────────────────────────────────────────────────────────────────
65: class Intent:
66:     CHAT        = "chat"
67:     SEARCH      = "search"
68:     CODE        = "code"
69:     FILE        = "file"
70:     TRANSLATE   = "translate"
71:     BROADCAST   = "broadcast"
72:     SPLIT       = "split"
73:     PIPELINE    = "pipeline"
74:     DECOMPOSE   = "decompose"   # Explizite Atomisierung
75:     FACT_SET    = "fact_set"
76:     DIRECTIVE   = "directive"
77:     STATUS      = "status"
78:     KI_STATUS   = "ki_status"   # KI-Dialog + Skill-Übersicht
79:     MEINUNG     = "meinung"     # Isaac's Meinung zu einem Thema
80:     PAUSE       = "pause"
81:     RESUME      = "resume"
82:     CANCEL      = "cancel"
83:     SUDO_OPEN   = "sudo_open"
84:     SUDO_CLOSE  = "sudo_close"
85:     LOGIN_ADD   = "login_add"
86:     URL_ADD     = "url_add"
87: 
88: 
89: PATTERNS = [
90:     (Intent.SUDO_OPEN,  [r"^sudo\s+", r"^öffne tür", r"^master key"]),
91:     (Intent.SUDO_CLOSE, [r"^sudo close$", r"^tür schließen$"]),
92:     (Intent.FACT_SET,   [r"^korrektur:", r"^fakt:", r"^weiß:"]),
93:     (Intent.DIRECTIVE,  [r"^direktive:", r"^immer:", r"^niemals:"]),
94:     (Intent.BROADCAST,  [r"^broadcast:", r"^alle instanzen:", r"^frage alle"]),
95:     (Intent.SPLIT,      [r"^split:", r"^aufteilen:"]),
96:     (Intent.PIPELINE,   [r"^pipeline:", r"^verbessere iterativ"]),
97:     (Intent.DECOMPOSE,  [r"^atomisiere:", r"^verteile:"]),
98:     (Intent.CODE,       [r"^code:", r"^programmiere:", r"^schreibe.*python"]),
99:     (Intent.FILE,       [r"^datei:", r"^lese:", r"^schreibe.*datei"]),
100:     (Intent.TRANSLATE,  [r"übersetze", r"^schrift:", r"alphabet"]),
101:     (Intent.LOGIN_ADD,  [r"^login:", r"^credential:", r"^zugangsdaten:"]),
102:     (Intent.URL_ADD,    [r"^url:", r"^instanz:", r"^füge.*url"]),
103:     (Intent.KI_STATUS,  [r"^ki status$", r"^instanzen$", r"^meinungen$"]),
104:     (Intent.MEINUNG,    [r"^meinung:", r"^was denkst du über", r"^isaac.*meinung"]),
105:     (Intent.PAUSE,      [r"^pause$", r"^stopp$"]),
106:     (Intent.RESUME,     [r"^weiter$", r"^fortsetzen$"]),
107:     (Intent.CANCEL,     [r"^abbrechen\s+\w+"]),
108: ]
109: 
110: def detect_intent(text: str) -> str:
111:     tl = text.lower().strip()
112:     for intent, patterns in PATTERNS:
113:         for pat in patterns:
114:             if re.search(pat, tl):
115:                 return intent
116:     return Intent.CHAT
117: 
118: 
119: def braucht_decomposer(text: str, intent: str) -> bool:
120:     """Entscheidet ob ein Prompt atomisiert werden soll."""
121:     if intent in (Intent.CODE, Intent.FILE, Intent.SEARCH,
122:                   Intent.BROADCAST, Intent.SPLIT, Intent.PIPELINE,
123:                   Intent.DECOMPOSE):
124:         return False   # Eigene Handler
125:     wortanzahl = len(text.split())
126:     und_count  = len(re.findall(r'\s+(?:und|sowie|außerdem|auch)\s+',
127:                                 text, re.I))
128:     return wortanzahl >= DECOMPOSE_WORT_SCHWELLE or und_count >= DECOMPOSE_THEMEN_SCHWELLE
129: 
130: 
131: # ── Kernel ─────────────────────────────────────────────────────────────────────
132: class IsaacKernel:
133: 
134:     VERSION = "5.3"
135: 
136:     def __init__(self):
137:         log.info("=" * 56)
138:         log.info(f"  ISAAC v{self.VERSION} – Unified OS Startup")
139:         log.info("=" * 56)
140: 
141:         setup_privilege_audit()
142: 
143:         self.cfg        = get_config()
144:         self.gate       = get_gate()
145:         self.memory     = get_memory()
146:         self.executor   = get_executor()
147:         self.relay      = get_relay()
148:         self.logic      = get_logic()
149:         self.empathie   = get_empathie()
150:         self.sudo       = get_sudo()
151:         self.regelwerk  = get_regelwerk()
152:         self.decomposer = get_decomposer()
153:         self.ki_dialog  = get_ki_dialog()
154:         self.skill_router = get_skill_router()
155:         self.monitor    = get_monitor()
156:         self.meaning    = get_meaning()
157:         self.values     = get_values()
158:         self._background = None   # lazy start in main()
159: 
160:         set_kernel(self)
161:         self._sudo_token: Optional[str] = None
162: 
163:         log.info(f"  Owner:      {self.cfg.owner_name}")
164:         log.info(f"  Provider:   {', '.join(self.cfg.available_providers)}")
165:         log.info(f"  Regelwerk:  {self.regelwerk.status()['regeln_aktiv']} Regeln")
166:         log.info(f"  KI-Dialog:  {self.ki_dialog.stats()['gespraeche']} Gespräche, "
167:                  f"{self.ki_dialog.stats()['wissenseintraege']} Wissenseinträge")
168:         log.info(f"  SUDO:       {'Ersteinrichtung' if self.sudo.is_first_run() else 'Bereit'}")
169:         AuditLog.action("Kernel", "startup", f"v{self.VERSION}", Level.ISAAC)
170: 
171:     # ── Haupt-Verarbeitung ────────────────────────────────────────────────────
172:     async def process(self, user_input: str,
173:                       sudo_token: Optional[str] = None) -> str:
174:         if not user_input.strip():
175:             return ""
176: 
177:         # 0) Klassifikation als harte Routing-Grundlage
178:         classification = classify_interaction_result(user_input)
179:         interaction_class = classification.interaction_class
180:         if is_lightweight_local_class(interaction_class):
181:             return local_class_response(interaction_class, user_input)
182: 
183:         t0 = time.monotonic()
184: 
185:         # SUDO-Status
186:         sudo_aktiv = (
187:             (sudo_token and self.sudo.check(sudo_token)) or
188:             (self._sudo_token and self.sudo.check(self._sudo_token))
189:         )
190: 
191:         AuditLog.steffen_input(user_input)
192: 
193:         # 1. Empathie
194:         emp = self.empathie.analysiere(user_input)
195: 
196:         # 2. Wissensdatenbank konsultieren
197:         wissen_kontext = self.ki_dialog.als_kontext(user_input)
198: 
199:         # 3. Intent mit klassifikationsdominierter Korrektur
200:         detected_intent = detect_intent(user_input)
201:         intent = self._resolve_intent_from_classification(
202:             user_input, detected_intent, interaction_class
203:         )
204: 
205:         log.info(
206:             f"Input: '{user_input[:50]}' │ Intent: {intent} │ "
207:             f"Node: {emp.node.zustand} │ Sudo: {sudo_aktiv}"
208:         )
209: 
210:         # SUDO-Handshake
211:         if intent == Intent.SUDO_OPEN:
212:             return self._handle_sudo_open(user_input)
213:         if intent == Intent.SUDO_CLOSE:
214:             return self._handle_sudo_close()
215: 
216:         # Pause
217:         if self.gate.is_paused and not sudo_aktiv:
218:             return "[Isaac] Pausiert. 'weiter' oder SUDO zum Fortfahren."
219: 
220:         if self._is_browser_request(user_input):
221:             result = await self._handle_browser_request(user_input)
222:             return self._post_process(user_input, result, emp, 0.0, t0)
223: 
224:         # Direkte Handler (kein Task nötig)
225:         direkt = {
226:             Intent.FACT_SET:   self._handle_fact,
227:             Intent.DIRECTIVE:  self._handle_directive,
228:             Intent.STATUS:     self._handle_status,
229:             Intent.KI_STATUS:  self._handle_ki_status,
230:             Intent.MEINUNG:    self._handle_meinung,
231:             Intent.PAUSE:      self._handle_pause,
232:             Intent.RESUME:     self._handle_resume,
233:             Intent.CANCEL:     self._handle_cancel,
234:             Intent.LOGIN_ADD:  self._handle_login_add,
235:             Intent.URL_ADD:    self._handle_url_add,
236:         }
237:         if intent in direkt:
238:             result = direkt[intent](user_input)
239:             if asyncio.iscoroutine(result):
240:                 result = await result
241:             return self._post_process(user_input, result, emp, 0.0, t0)
242: 
243:         # 4. Routing: Decomposer vs Standard vs Multi-KI
244:         antwort, score = await self._route(
245:             user_input,
246:             intent,
247:             sudo_aktiv,
248:             emp,
249:             wissen_kontext,
250:             interaction_class,
251:             classification,
252:         )
253: 
254:         return self._post_process(user_input, antwort, emp, score, t0)
255: 
256:     # ── Routing ────────────────────────────────────────────────────────────────
257:     async def _route(self, user_input: str, intent: str,
258:                      sudo_aktiv: bool, emp, wissen_kontext: str,
259:                      interaction_class: str,
260:                      classification: ClassificationResult

(Showing lines 1-260 of 933. Use offset=261 to continue.)
</content>
```

**Tool: read**

**Input:**
```json
{
  "filePath": "/root/Isaac/executor.py",
  "offset": 1,
  "limit": 320
}
```

**Output:**
```
<path>/root/Isaac/executor.py</path>
<type>file</type>
<content>
1: """
2: Isaac – Executor v2.0
3: =======================
4: Task-Engine. Vollständig async. Keine blockierenden Calls.
5: 
6: Korrekturen gegenüber v1:
7:   - asyncio.create_subprocess_exec statt subprocess.run (Event Loop safe)
8:   - Task-Persistenz in SQLite (überleben Neustarts)
9:   - Watchdog-Integration (Hang-Detection, Neustart)
10:   - Dispatcher-Integration (Multi-KI-Verteilung)
11:   - Pre-Flight-Validation vor Ausführung
12:   - Korrekte Callback-Sicherheit (asyncio.create_task nur im Event Loop)
13: """
14: 
15: import asyncio
16: import time
17: import re
18: import uuid
19: import json
20: import logging
21: import ast
22: import os
23: import tempfile
24: from pathlib import Path
25: from dataclasses import dataclass, field
26: from enum import Enum
27: from typing import Optional, Callable, Any
28: 
29: from config    import get_config, WORKSPACE, Level
30: from privilege import get_gate, isaac_ctx, task_ctx
31: from audit     import AuditLog
32: from logic     import get_logic, QualityScore, FollowUpDecision
33: from relay     import get_relay
34: from tool_runtime import select_live_tool_for_task, run_selected_tool
35: from task_tool_state import get_task_tool_state_store
36: from low_complexity import ClassificationResult, is_lightweight_local_class
37: 
38: log = logging.getLogger("Isaac.Executor")
39: 
40: _ALLOWED_IMPORTS = {"math", "json", "random", "statistics", "collections", "itertools", "functools", "datetime"}
41: _FORBIDDEN_NAMES = {"eval", "exec", "compile", "open", "input", "breakpoint", "help", "__import__"}
42: _FORBIDDEN_ATTRS = {"system", "popen", "spawn", "remove", "unlink", "rmtree", "kill", "fork", "chmod", "chown"}
43: 
44: 
45: def _normalize_code(raw: str) -> str:
46:     raw = re.sub(r"```python\n?", "", raw)
47:     raw = re.sub(r"```\n?", "", raw)
48:     return raw.strip()
49: 
50: 
51: def _fingerprint(text: str) -> str:
52:     return re.sub(r"\s+", " ", (text or "").strip().lower())[:800]
53: 
54: 
55: def _limit_subprocess_resources():
56:     try:
57:         import resource
58:         resource.setrlimit(resource.RLIMIT_CPU, (5, 5))
59:         resource.setrlimit(resource.RLIMIT_FSIZE, (1_000_000, 1_000_000))
60:         resource.setrlimit(resource.RLIMIT_NOFILE, (16, 16))
61:         resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024))
62:     except Exception:
63:         pass
64: 
65: 
66: def _validate_generated_code(code: str) -> tuple[bool, str]:
67:     try:
68:         tree = ast.parse(code)
69:     except SyntaxError as e:
70:         return False, f"Syntaxfehler im generierten Code: {e.msg}"
71: 
72:     for node in ast.walk(tree):
73:         if isinstance(node, (ast.Import, ast.ImportFrom)):
74:             names = [alias.name.split(".", 1)[0] for alias in node.names]
75:             if any(name not in _ALLOWED_IMPORTS for name in names):
76:                 return False, f"Import nicht erlaubt: {', '.join(names)}"
77:         elif isinstance(node, ast.Call):
78:             if isinstance(node.func, ast.Name) and node.func.id in _FORBIDDEN_NAMES:
79:                 return False, f"Aufruf nicht erlaubt: {node.func.id}()"
80:             if isinstance(node.func, ast.Attribute) and node.func.attr in _FORBIDDEN_ATTRS:
81:                 return False, f"Attribut nicht erlaubt: .{node.func.attr}"
82:         elif isinstance(node, ast.Attribute) and node.attr.startswith('__'):
83:             return False, "Dunder-Zugriff nicht erlaubt"
84:     return True, ""
85: 
86: 
87: class TaskStatus(Enum):
88:     QUEUED     = "queued"
89:     RUNNING    = "running"
90:     EVALUATING = "evaluating"
91:     FOLLOWUP   = "followup"
92:     DONE       = "done"
93:     FAILED     = "failed"
94:     CANCELLED  = "cancelled"
95: 
96: 
97: class TaskType(Enum):
98:     CHAT       = "chat"
99:     SEARCH     = "search"
100:     ANALYSIS   = "analysis"
101:     TRANSLATE  = "translate"
102:     CODE       = "code"
103:     PLAN       = "plan"
104:     FILE       = "file"
105:     AGGREGATE  = "aggregate"
106:     BROADCAST  = "broadcast"   # Multi-KI
107:     SPLIT      = "split"       # Multi-KI aufgeteilt
108:     PIPELINE   = "pipeline"    # Multi-KI iterativ
109: 
110: 
111: @dataclass(frozen=True)
112: class Strategy:
113:     allow_tools: bool = True
114:     allow_followup: bool = True
115:     allow_provider_switch: bool = True
116:     style_note: str = ""
117: 
118:     def as_dict(self) -> dict[str, Any]:
119:         return {
120:             "allow_tools": self.allow_tools,
121:             "allow_followup": self.allow_followup,
122:             "allow_provider_switch": self.allow_provider_switch,
123:             "style_note": self.style_note,
124:         }
125: 
126: 
127: @dataclass
128: class Task:
129:     id:            str
130:     typ:           TaskType
131:     prompt:        str
132:     beschreibung:  str
133:     prioritaet:    float = 5.0
134:     provider:      Optional[str] = None
135:     parent_id:     Optional[str] = None
136:     system_prompt: str           = ""
137:     sudo_aktiv:    bool          = False   # SUDO-Modus
138: 
139:     status:        TaskStatus = TaskStatus.QUEUED
140:     iteration:     int        = 0
141:     erstellt:      str        = field(default_factory=lambda: time.strftime("%Y-%m-%d %H:%M:%S"))
142:     gestartet:     str        = ""
143:     abgeschlossen: str        = ""
144:     antwort:       str        = ""
145:     provider_used: str        = ""
146:     score:         Optional[QualityScore] = None
147:     followup:      Optional[FollowUpDecision] = None
148:     fehler:        str        = ""
149:     sub_task_ids:  list       = field(default_factory=list)
150:     dauer_sek:     float      = 0.0
151:     progress:      float      = 0.0
152:     log_entries:   list       = field(default_factory=list)
153:     used_tools:    list       = field(default_factory=list)
154:     tool_strategy: dict       = field(default_factory=dict)
155:     strategy:      Strategy   = field(default_factory=Strategy)
156:     interaction_class: str    = ""
157:     classification: Optional[ClassificationResult] = None
158:     retrieved_context: dict   = field(default_factory=dict)
159: 
160:     # Watchdog
161:     _last_watchdog_progress: float = 0.0
162: 
163:     def log(self, msg: str):
164:         self.log_entries.append({"ts": time.strftime("%H:%M:%S"), "msg": msg})
165:         if len(self.log_entries) > 50:
166:             self.log_entries = self.log_entries[-50:]
167: 
168:     def to_dict(self) -> dict:
169:         return {
170:             "id":            self.id,
171:             "typ":           self.typ.value,
172:             "beschreibung":  self.beschreibung,
173:             "prioritaet":    self.prioritaet,
174:             "status":        self.status.value,
175:             "iteration":     self.iteration,
176:             "erstellt":      self.erstellt,
177:             "gestartet":     self.gestartet,
178:             "abgeschlossen": self.abgeschlossen,
179:             "provider":      self.provider_used or self.provider or "auto",
180:             "score":         round(self.score.total, 2) if self.score else None,
181:             "score_detail":  self.score.as_dict() if self.score else None,
182:             "followup_mode": self.followup.mode if self.followup else None,
183:             "parent_id":     self.parent_id,
184:             "sub_tasks":     len(self.sub_task_ids),
185:             "dauer":         round(self.dauer_sek, 2),
186:             "progress":      round(self.progress, 3),
187:             "antwort_kurz":  self.antwort[:200] if self.antwort else "",
188:             "fehler":        self.fehler[:100] if self.fehler else "",
189:             "log":           self.log_entries[-10:],
190:             "used_tools":    self.used_tools[-8:],
191:             "tool_strategy": self.tool_strategy or {},
192:             "strategy":      self.strategy.as_dict(),
193:             "classification": self.classification.as_dict() if self.classification else None,
194:             "sudo":          self.sudo_aktiv,
195:         }
196: 
197:     @property
198:     def allow_tools(self) -> bool:
199:         return self.strategy.allow_tools
200: 
201:     @property
202:     def allow_followup(self) -> bool:
203:         return self.strategy.allow_followup
204: 
205:     @property
206:     def allow_provider_switch(self) -> bool:
207:         return self.strategy.allow_provider_switch
208: 
209:     @property
210:     def current_interaction_class(self) -> str:
211:         if self.classification:
212:             return self.classification.interaction_class
213:         return self.interaction_class
214: 
215: 
216: class Executor:
217:     def __init__(self):
218:         self._tasks:    dict[str, Task]          = {}
219:         self._queue:    asyncio.PriorityQueue    = asyncio.PriorityQueue()
220:         self._running:  set[str]                 = set()
221:         self._callbacks: list[Callable]          = []
222:         self._loop:     Optional[asyncio.AbstractEventLoop] = None
223:         self.logic      = get_logic()
224:         self.relay      = get_relay()
225:         self.gate       = get_gate()
226:         self._watchdog  = None   # lazy
227:         self._dispatcher= None   # lazy
228:         self._search    = None   # lazy
229:         self._tool_state = get_task_tool_state_store()
230:         self._load_persisted_tasks()
231:         log.info("Executor v2.0 online")
232: 
233:     def _get_watchdog(self):
234:         if not self._watchdog:
235:             from watchdog import get_watchdog
236:             self._watchdog = get_watchdog()
237:             self._watchdog.set_executor(self)
238:         return self._watchdog
239: 
240:     def _get_dispatcher(self):
241:         if not self._dispatcher:
242:             from dispatcher import get_dispatcher
243:             self._dispatcher = get_dispatcher()
244:         return self._dispatcher
245: 
246:     def _get_search(self):
247:         if not self._search:
248:             from search import get_search
249:             self._search = get_search()
250:         return self._search
251: 
252:     # ── Task erstellen ─────────────────────────────────────────────────────────
253:     def create_task(self, typ: TaskType, prompt: str,
254:                     beschreibung: str = "", prioritaet: float = 5.0,
255:                     provider: Optional[str] = None,
256:                     parent_id: Optional[str] = None,
257:                     system_prompt: str = "",
258:                     sudo_aktiv: bool = False,
259:                     strategy: Optional[Strategy] = None,
260:                     interaction_class: str = "",
261:                     classification: Optional[ClassificationResult] = None,
262:                     allow_tools: Optional[bool] = None,
263:                     allow_followup: Optional[bool] = None,
264:                     allow_provider_switch: Optional[bool] = None,
265:                     retrieved_context: Optional[dict] = None) -> Task:
266:         if strategy is None:
267:             strategy = Strategy(
268:                 allow_tools=True if allow_tools is None else allow_tools,
269:                 allow_followup=True if allow_followup is None else allow_followup,
270:                 allow_provider_switch=True if allow_provider_switch is None else allow_provider_switch,
271:             )
272:         elif any(flag is not None for flag in (allow_tools, allow_followup, allow_provider_switch)):
273:             log.warning("create_task: allow_* flags ignoriert, da Strategy explizit gesetzt ist")
274:         task = Task(
275:             id            = self.next_task_id(),
276:             typ           = typ,
277:             prompt        = prompt,
278:             beschreibung  = beschreibung or prompt[:80],
279:             prioritaet    = prioritaet,
280:             provider      = provider,
281:             parent_id     = parent_id,
282:             system_prompt = system_prompt,
283:             sudo_aktiv    = sudo_aktiv,
284:             strategy      = strategy,
285:             interaction_class = interaction_class,
286:             classification = classification,
287:             retrieved_context = retrieved_context or {},
288:         )
289:         self._tasks[task.id] = task
290:         AuditLog.task(task.id, "created", task.beschreibung[:100])
291:         return task
292: 
293: 
294:     def next_task_id(self) -> str:
295:         return uuid.uuid4().hex[:8]
296: 
297:     async def submit(self, task: Task) -> Task:
298:         await self._queue.put((-task.prioritaet, task.id))
299:         task.log("In Queue")
300:         self._notify(task)
301:         return task
302: 
303:     async def submit_and_wait(self, task: Task,
304:                               timeout: float = 180.0) -> Task:
305:         await self.submit(task)
306:         deadline = time.monotonic() + timeout
307:         while time.monotonic() < deadline:
308:             if task.status in (TaskStatus.DONE, TaskStatus.FAILED,
309:                                TaskStatus.CANCELLED):
310:                 return task
311:             await asyncio.sleep(0.3)
312:         task.status = TaskStatus.FAILED
313:         task.fehler = "Timeout"
314:         return task
315: 
316:     # ── Worker ────────────────────────────────────────────────────────────────
317:     async def start_worker(self, concurrency: int = 4):
318:         self._loop = asyncio.get_running_loop()
319:         log.info(f"Worker gestartet (concurrency={concurrency})")
320:         sem = asyncio.Semaphore(concurrency)

(Showing lines 1-320 of 969. Use offset=321 to continue.)
</content>
```

**Tool: read**

**Input:**
```json
{
  "filePath": "/root/Isaac/memory.py",
  "offset": 1,
  "limit": 260
}
```

**Output:**
```
<path>/root/Isaac/memory.py</path>
<type>file</type>
<content>
1: """
2: Isaac – Gedächtnis (SQLite)
3: ============================
4: Persistentes, durchsuchbares Gedächtnis auf drei Ebenen:
5: 
6:   1. Working Memory    – letzte N Konversationen (RAM + DB)
7:   2. Faktenspeicher    – Steffen-Wissen, Korrekturen, Kontext
8:   3. Direktiven-Store  – Steffen-Direktiven (permanent)
9: 
10: SQLite ist atomar: kein Datenverlust bei Absturz.
11: FTS5 für Volltextsuche.
12: """
13: 
14: import sqlite3
15: import json
16: import time
17: import logging
18: import re
19: from pathlib import Path
20: from dataclasses import dataclass
21: from typing import Optional, Any
22: from contextlib import contextmanager
23: 
24: from config import DB_PATH, get_config
25: from audit  import AuditLog
26: 
27: log = logging.getLogger("Isaac.Memory")
28: 
29: 
30: @dataclass(frozen=True)
31: class RetrievalContext:
32:     query: str
33:     active_directives: list[dict]
34:     relevant_facts: list[dict]
35:     semantic_context: str
36:     conversation_history: list[dict]
37:     relevant_task_results: list[dict]
38:     preferences_context: list[dict]
39:     project_context: list[dict]
40:     behavioral_risks: list[dict]
41:     relevant_reflections: list[str]
42:     open_questions: list[str]
43: 
44:     def as_dict(self) -> dict[str, Any]:
45:         return {
46:             "query": self.query,
47:             "active_directives": self.active_directives,
48:             "relevant_facts": self.relevant_facts,
49:             "semantic_context": self.semantic_context,
50:             "conversation_history": self.conversation_history,
51:             "relevant_task_results": self.relevant_task_results,
52:             "preferences_context": self.preferences_context,
53:             "project_context": self.project_context,
54:             "behavioral_risks": self.behavioral_risks,
55:             "relevant_reflections": self.relevant_reflections,
56:             "open_questions": self.open_questions,
57:         }
58: 
59: 
60: # ── Schema ─────────────────────────────────────────────────────────────────────
61: SCHEMA = """
62: -- Konversations-Verlauf
63: CREATE TABLE IF NOT EXISTS conversations (
64:     id          INTEGER PRIMARY KEY AUTOINCREMENT,
65:     ts          TEXT    NOT NULL,
66:     role        TEXT    NOT NULL,   -- 'steffen' | 'isaac' | 'instance'
67:     text        TEXT    NOT NULL,
68:     task_id     TEXT    DEFAULT '',
69:     provider    TEXT    DEFAULT '',
70:     quality     REAL    DEFAULT 0.0,
71:     metadata    TEXT    DEFAULT '{}'
72: );
73: 
74: -- Fakten (Langzeit-Wissen)
75: CREATE TABLE IF NOT EXISTS facts (
76:     id          INTEGER PRIMARY KEY AUTOINCREMENT,
77:     ts          TEXT    NOT NULL,
78:     key         TEXT    NOT NULL UNIQUE,
79:     value       TEXT    NOT NULL,
80:     source      TEXT    DEFAULT '',
81:     confidence  REAL    DEFAULT 1.0,
82:     updated     TEXT    NOT NULL
83: );
84: 
85: -- Steffen-Direktiven
86: CREATE TABLE IF NOT EXISTS directives (
87:     id          TEXT    PRIMARY KEY,
88:     ts          TEXT    NOT NULL,
89:     text        TEXT    NOT NULL,
90:     priority    INTEGER DEFAULT 10,
91:     active      INTEGER DEFAULT 1
92: );
93: 
94: -- Task-Ergebnisse (komprimiert, für Referenz)
95: CREATE TABLE IF NOT EXISTS task_results (
96:     id          TEXT    PRIMARY KEY,
97:     ts          TEXT    NOT NULL,
98:     description TEXT    NOT NULL,
99:     result      TEXT    NOT NULL,
100:     score       REAL    DEFAULT 0.0,
101:     iterations  INTEGER DEFAULT 1,
102:     provider    TEXT    DEFAULT '',
103:     tags        TEXT    DEFAULT '[]'
104: );
105: 
106: -- FTS für Konversationen
107: CREATE VIRTUAL TABLE IF NOT EXISTS conv_fts USING fts5(
108:     text, content='conversations', content_rowid='id'
109: );
110: 
111: -- FTS für Fakten
112: CREATE VIRTUAL TABLE IF NOT EXISTS facts_fts USING fts5(
113:     key, value, content='facts', content_rowid='id'
114: );
115: 
116: -- Trigger für FTS-Sync
117: CREATE TRIGGER IF NOT EXISTS conv_ai AFTER INSERT ON conversations BEGIN
118:     INSERT INTO conv_fts(rowid, text) VALUES (new.id, new.text);
119: END;
120: CREATE TRIGGER IF NOT EXISTS facts_ai AFTER INSERT ON facts BEGIN
121:     INSERT INTO facts_fts(rowid, key, value) VALUES (new.id, new.key, new.value);
122: END;
123: CREATE TRIGGER IF NOT EXISTS facts_au AFTER UPDATE ON facts BEGIN
124:     INSERT INTO facts_fts(facts_fts, rowid, key, value)
125:         VALUES('delete', old.id, old.key, old.value);
126:     INSERT INTO facts_fts(rowid, key, value) VALUES (new.id, new.key, new.value);
127: END;
128: """
129: 
130: # ── Verbindung ────────────────────────────────────────────────────────────────
131: @contextmanager
132: def _conn():
133:     """Thread-safe SQLite-Verbindung mit WAL-Mode."""
134:     con = sqlite3.connect(str(DB_PATH), check_same_thread=False,
135:                           timeout=10.0)
136:     con.row_factory = sqlite3.Row
137:     con.execute("PRAGMA journal_mode=WAL")
138:     con.execute("PRAGMA foreign_keys=ON")
139:     try:
140:         yield con
141:         con.commit()
142:     except Exception:
143:         con.rollback()
144:         raise
145:     finally:
146:         con.close()
147: 
148: 
149: def init_db():
150:     with _conn() as con:
151:         con.executescript(SCHEMA)
152:     log.info(f"DB initialisiert: {DB_PATH}")
153: 
154: 
155: # ── Memory-Klasse ──────────────────────────────────────────────────────────────
156: class Memory:
157:     """
158:     Isaacs Gedächtnis.
159:     Alle Schreib-Operationen erzeugen Audit-Einträge.
160:     """
161: 
162:     def __init__(self):
163:         init_db()
164:         self._working: list[dict] = []
165:         self._load_working_memory()
166:         # Vektor-Gedächtnis (semantisch, optional)
167:         from vector_memory import get_vector_memory
168:         self._vector = get_vector_memory()
169:         log.info(
170:             f"Memory online │ Working: {len(self._working)} Einträge │ "
171:             f"Vector: {'aktiv' if self._vector.aktiv else 'inaktiv (pip install chromadb)'}"
172:         )
173: 
174:     # ── Konversation ──────────────────────────────────────────────────────────
175:     def add_conversation(self, role: str, text: str,
176:                          task_id: str = "", provider: str = "",
177:                          quality: float = 0.0, metadata: dict = None,
178:                          stimmung: str = "neutral"):
179:         ts = time.strftime("%Y-%m-%d %H:%M:%S")
180:         meta = json.dumps(metadata or {})
181:         with _conn() as con:
182:             cur = con.execute(
183:                 "INSERT INTO conversations (ts, role, text, task_id, "
184:                 "provider, quality, metadata) VALUES (?,?,?,?,?,?,?)",
185:                 (ts, role, text, task_id, provider, quality, meta)
186:             )
187:             conv_id = str(cur.lastrowid)
188:         entry = {"ts": ts, "role": role, "text": text,
189:                  "task_id": task_id, "provider": provider,
190:                  "quality": quality}
191:         self._working.append(entry)
192:         cfg = get_config()
193:         if len(self._working) > cfg.memory.max_working_memory:
194:             self._working = self._working[-cfg.memory.max_working_memory:]
195:         AuditLog.memory_write("Memory", "conversation", role)
196:         # Semantisch speichern
197:         self._vector.speichere_konversation(
198:             conv_id   = conv_id,
199:             text      = text,
200:             role      = role,
201:             ts        = ts,
202:             stimmung  = stimmung,
203:             qualitaet = quality,
204:         )
205: 
206:     def get_working_memory(self, n: int = 10) -> list[dict]:
207:         """Gibt die letzten n Konversations-Einträge zurück."""
208:         return self._working[-n:]
209: 
210:     def search_conversations(self, query: str, limit: int = 10) -> list[dict]:
211:         with _conn() as con:
212:             rows = con.execute(
213:                 """SELECT c.* FROM conversations c
214:                    JOIN conv_fts ON conv_fts.rowid = c.id
215:                    WHERE conv_fts MATCH ?
216:                    ORDER BY c.id DESC LIMIT ?""",
217:                 (query, limit)
218:             ).fetchall()
219:         return [dict(r) for r in rows]
220: 
221:     # ── Fakten ────────────────────────────────────────────────────────────────
222:     def set_fact(self, key: str, value: str, source: str = "",
223:                  confidence: float = 1.0) -> bool:
224:         """Schreibt oder aktualisiert eine Tatsache."""
225:         ts = time.strftime("%Y-%m-%d %H:%M:%S")
226:         with _conn() as con:
227:             existing = con.execute(
228:                 "SELECT id FROM facts WHERE key=?", (key,)
229:             ).fetchone()
230:             if existing:
231:                 con.execute(
232:                     "UPDATE facts SET value=?, source=?, "
233:                     "confidence=?, updated=? WHERE key=?",
234:                     (value, source, confidence, ts, key)
235:                 )
236:             else:
237:                 con.execute(
238:                     "INSERT INTO facts (ts, key, value, source, "
239:                     "confidence, updated) VALUES (?,?,?,?,?,?)",
240:                     (ts, key, value, source, confidence, ts)
241:                 )
242:         AuditLog.memory_write("Memory", "fact", key)
243:         return True
244: 
245:     def get_fact(self, key: str) -> Optional[str]:
246:         with _conn() as con:
247:             row = con.execute(
248:                 "SELECT value FROM facts WHERE key=?", (key,)
249:             ).fetchone()
250:         return row["value"] if row else None
251: 
252:     def search_facts(self, query: str, limit: int = 10) -> list[dict]:
253:         with _conn() as con:
254:             rows = con.execute(
255:                 """SELECT f.* FROM facts f
256:                    JOIN facts_fts ON facts_fts.rowid = f.id
257:                    WHERE facts_fts MATCH ?
258:                    ORDER BY f.confidence DESC LIMIT ?""",
259:                 (query, limit)
260:             ).fetchall()

(Showing lines 1-260 of 530. Use offset=261 to continue.)
</content>
```

**Tool: read**

**Input:**
```json
{
  "filePath": "/root/Isaac/tool_runtime.py",
  "offset": 1,
  "limit": 320
}
```

**Output:**
```
<path>/root/Isaac/tool_runtime.py</path>
<type>file</type>
<content>
1: from __future__ import annotations
2: 
3: import asyncio
4: import json
5: import os
6: from urllib.parse import urlencode
7: 
8: import aiohttp
9: 
10: from config import get_config
11: from tool_registry import get_tool_registry
12: from secrets_store import get_secrets_store
13: from browser_chat import BrowserChatProvider
14: from mcp_client import MCPClient
15: from mcp_registry import get_mcp_registry
16: from task_tool_state import get_task_tool_state_store
17: 
18: _browser = None
19: 
20: CATEGORY_HINTS = {
21:     "wetter": "wetter",
22:     "weather": "wetter",
23:     "suche": "suche",
24:     "search": "suche",
25:     "internet": "suche",
26:     "recherche": "suche",
27:     "browser": "suche",
28:     "web": "suche",
29:     "code": "code",
30:     "python": "code",
31:     "github": "code",
32:     "api": "integration",
33:     "tool": "integration",
34:     "mcp": "integration",
35:     "resource": "resource",
36:     "datei": "resource",
37: }
38: 
39: 
40: MCP_BRIDGE_URL = os.getenv("MCP_BRIDGE_URL", "http://127.0.0.1:8766")
41: 
42: 
43: def infer_category(prompt: str) -> str:
44:     p = (prompt or '').lower()
45:     for key, cat in CATEGORY_HINTS.items():
46:         if key in p:
47:             return cat
48:     return "general"
49: 
50: 
51: def select_tool_for_prompt(prompt: str, preferred_kind: str = ""):
52:     reg = get_tool_registry()
53:     cat = infer_category(prompt)
54:     return reg.pick(category=cat, kind=preferred_kind) or reg.pick(category=cat) or reg.pick(category="general")
55: 
56: 
57: def _headers(tool: dict) -> dict:
58:     headers = {
59:         "User-Agent": "Isaac/1.0 (+local tool runtime)",
60:         "Accept": "application/json, text/plain;q=0.9, */*;q=0.8",
61:     }
62:     if tool.get("auth_type") != "header":
63:         return headers
64:     secret = get_secrets_store().get_secret(tool.get("secret_ref", ""))
65:     if not secret:
66:         return headers
67:     headers[tool.get("auth_field") or "Authorization"] = f'{tool.get("auth_prefix","")}{secret}'
68:     return headers
69: 
70: 
71: def _url_with_query_auth(url: str, tool: dict) -> str:
72:     if tool.get("auth_type") != "query":
73:         return url
74:     secret = get_secrets_store().get_secret(tool.get("secret_ref", ""))
75:     if not secret:
76:         return url
77:     joiner = "&" if "?" in url else "?"
78:     field = tool.get("auth_field") or "api_key"
79:     return f"{url}{joiner}{urlencode({field: secret})}"
80: 
81: 
82: def _append_query(url: str, query_param: str, prompt: str) -> str:
83:     joiner = "&" if "?" in url else "?"
84:     return f"{url}{joiner}{urlencode({query_param or 'q': prompt})}"
85: 
86: 
87: def _response_to_text(content_type: str, text: str) -> str:
88:     if 'application/json' in (content_type or '').lower():
89:         try:
90:             data = json.loads(text)
91:             return json.dumps(data, ensure_ascii=False, indent=2)[:3000]
92:         except Exception:
93:             return text[:3000]
94:     return text[:3000]
95: 
96: 
97: async def _run_script(script_path: str, prompt: str) -> tuple[bool, str, int]:
98:     proc = await asyncio.create_subprocess_exec(
99:         script_path,
100:         prompt,
101:         stdout=asyncio.subprocess.PIPE,
102:         stderr=asyncio.subprocess.PIPE,
103:     )
104:     try:
105:         stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=20)
106:     except asyncio.TimeoutError:
107:         proc.kill()
108:         await proc.communicate()
109:         return False, 'Timeout (20s)', -1
110:     output = (stdout.decode(errors='replace') or stderr.decode(errors='replace') or '').strip()
111:     return proc.returncode == 0, output[:3000], proc.returncode
112: 
113: 
114: async def _run_registry_tool(tool, prompt: str) -> dict:
115:     reg = get_tool_registry()
116:     if not tool:
117:         return {"ok": False, "error": "Kein Tool verfügbar"}
118:     row = next((x for x in reg.list_tools() if x["tool_id"] == tool.tool_id), None) or {}
119: 
120:     try:
121:         timeout = aiohttp.ClientTimeout(total=20)
122:         if tool.kind in ("api", "mcp"):
123:             if tool.kind == "mcp":
124:                 client = MCPClient(tool.base_url or MCP_BRIDGE_URL)
125:                 features = await discover_mcp_bridge(client)
126:                 tools = features.get("tools") or []
127:                 if tools:
128:                     best = tools[0]
129:                     result = await client.invoke_tool(best.get("name", ""), {"prompt": prompt, "query": prompt})
130:                     ok = bool(result.get("ok"))
131:                     reg.record(tool.tool_id, ok, f"mcp-run:{result.get('status_code', 200)}")
132:                     return {
133:                         "ok": ok,
134:                         "content": _response_to_text("application/json", json.dumps(result, ensure_ascii=False)),
135:                         "status_code": result.get("status_code", 200),
136:                         "via": "mcp",
137:                         "url": client.api_base,
138:                     }
139:             url = (tool.base_url.rstrip("/") + "/" + tool.endpoint.lstrip("/")) if tool.endpoint else tool.base_url
140:             url = _url_with_query_auth(url, row)
141:             method = (tool.method or "GET").upper()
142:             async with aiohttp.ClientSession(timeout=timeout) as sess:
143:                 if method == "POST":
144:                     async with sess.post(url, headers=_headers(row), json={"prompt": prompt}) as res:
145:                         text = await res.text()
146:                         ok = res.status < 400
147:                         reg.record(tool.tool_id, ok, f"api-run:{res.status}")
148:                         return {"ok": ok, "content": _response_to_text(res.headers.get('Content-Type', ''), text), "status_code": res.status, "via": "api", "url": str(res.url)}
149:                 else:
150:                     qurl = _append_query(url, tool.query_param or 'q', prompt)
151:                     async with sess.get(qurl, headers=_headers(row)) as res:
152:                         text = await res.text()
153:                         ok = res.status < 400
154:                         reg.record(tool.tool_id, ok, f"api-run:{res.status}")
155:                         return {"ok": ok, "content": _response_to_text(res.headers.get('Content-Type', ''), text), "status_code": res.status, "via": "api", "url": str(res.url)}
156: 
157:         if tool.kind == "search":
158:             base = tool.base_url or tool.website_url
159:             url = _url_with_query_auth(base, row)
160:             qurl = _append_query(url, tool.query_param or 'q', prompt)
161:             async with aiohttp.ClientSession(timeout=timeout) as sess:
162:                 async with sess.get(qurl, headers=_headers(row)) as res:
163:                     text = await res.text()
164:                     ok = res.status < 400
165:                     reg.record(tool.tool_id, ok, f"search-run:{res.status}")
166:                     return {"ok": ok, "content": _response_to_text(res.headers.get('Content-Type', ''), text), "status_code": res.status, "via": "search", "url": str(res.url)}
167: 
168:         if tool.kind == "script":
169:             ok, content, code = await _run_script(tool.script_path, prompt)
170:             reg.record(tool.tool_id, ok, f"script-run:{code}")
171:             return {"ok": ok, "content": content, "via": "script", "status_code": code}
172: 
173:         if tool.kind == "browser_chat":
174:             if not get_config().browser_automation:
175:                 return {"ok": False, "error": "Browser-Modelle sind durch Runtime-Policy deaktiviert", "via": "browser_chat"}
176:             global _browser
177:             if _browser is None:
178:                 _browser = BrowserChatProvider()
179:             result = await _browser.ask(row, prompt)
180:             reg.record(tool.tool_id, result.ok, "browser-chat-run")
181:             return {"ok": result.ok, "content": result.content, "error": result.error, "via": "browser_chat"}
182: 
183:         return {"ok": False, "error": f"Nicht unterstützter Tooltyp: {tool.kind}"}
184:     except Exception as e:
185:         reg.record(tool.tool_id, False, f"run-error: {e}")
186:         return {"ok": False, "error": str(e), "via": getattr(tool, 'kind', 'unknown')}
187: 
188: 
189: async def discover_mcp_bridge(client: MCPClient | None = None) -> dict:
190:     client = client or MCPClient(MCP_BRIDGE_URL)
191:     try:
192:         capabilities = await client.capabilities()
193:         tools = await client.tools()
194:         resources = await client.resources()
195:         prompts = await client.prompts()
196:         return {
197:             "ok": True,
198:             "source": "remote",
199:             "capabilities": capabilities.get("capabilities", capabilities),
200:             "tools": tools.get("tools", []),
201:             "resources": resources.get("resources", []),
202:             "prompts": prompts.get("prompts", []),
203:             "url": client.api_base,
204:         }
205:     except Exception as e:
206:         reg = get_mcp_registry()
207:         return {
208:             "ok": False,
209:             "source": "local-fallback",
210:             "error": str(e),
211:             "capabilities": reg.capabilities(),
212:             "tools": reg.tools(),
213:             "resources": reg.resources(),
214:             "prompts": reg.prompts(),
215:             "url": client.api_base,
216:         }
217: 
218: 
219: async def list_live_tool_interfaces() -> dict:
220:     registry_tools = get_tool_registry().list_tools()
221:     mcp = await discover_mcp_bridge()
222:     return {
223:         "registry_tools": registry_tools,
224:         "mcp": mcp,
225:         "http_endpoints": [
226:             {"path": "/api/tools", "method": "GET"},
227:             {"path": "/api/tools/catalog", "method": "GET"},
228:             {"path": "/api/tools/bundles", "method": "GET"},
229:             {"path": "/api/tools/live", "method": "GET"},
230:             {"path": "/api/tools/install_local", "method": "POST"},
231:             {"path": "/api/tools/install_free_pack", "method": "POST"},
232:             {"path": "/api/tools/install_bundle", "method": "POST"},
233:             {"path": "/api/tools/add", "method": "POST"},
234:             {"path": "/api/tools/update", "method": "POST"},
235:             {"path": "/api/tools/toggle", "method": "POST"},
236:             {"path": "/api/tools/delete", "method": "POST"},
237:             {"path": "/api/tools/suggest", "method": "POST"},
238:             {"path": "/api/mcp/capabilities", "method": "GET"},
239:             {"path": "/api/mcp/tools", "method": "GET"},
240:             {"path": "/api/mcp/resources", "method": "GET"},
241:             {"path": "/api/mcp/prompts", "method": "GET"},
242:         ],
243:     }
244: 
245: 
246: async def select_live_tool_for_task(task, prompt: str, iteration: int) -> dict | None:
247:     store = get_task_tool_state_store()
248:     state = store.get_or_create(task.id, task.prompt)
249:     reg = get_tool_registry()
250:     category_pref = state.preferred_categories or [infer_category(prompt)]
251:     kind_pref = state.preferred_kinds or ["mcp", "api", "search"]
252: 
253:     candidates: list[tuple[float, dict]] = []
254:     for row in reg.list_tools(active_only=True):
255:         identifier = row.get("tool_id")
256:         if identifier in state.used_tool_ids:
257:             continue
258:         score = float(row.get("trust", 50.0)) + float(row.get("priority", 50)) / 2
259:         if row.get("category") in category_pref:
260:             score += 20
261:         if row.get("kind") in kind_pref:
262:             score += 15
263:         if iteration == 0 and row.get("kind") == "mcp":
264:             score += 10
265:         candidates.append((score, {
266:             "source": "registry",
267:             "identifier": identifier,
268:             "name": row.get("name", identifier),
269:             "kind": row.get("kind", ""),
270:             "category": row.get("category", "general"),
271:             "tool": reg.get(identifier),
272:         }))
273: 
274:     mcp = await discover_mcp_bridge()
275:     for tool in mcp.get("tools", []):
276:         identifier = f"mcp:{tool.get('name','')}"
277:         if identifier in state.used_tool_ids:
278:             continue
279:         score = 70.0
280:         desc = f"{tool.get('description','')} {tool.get('name','')}".lower()
281:         if any(cat in desc for cat in category_pref):
282:             score += 10
283:         score += 12 if mcp.get("source") == "remote" else 6
284:         candidates.append((score, {
285:             "source": "mcp_remote" if mcp.get("source") == "remote" else "mcp_local",
286:             "identifier": identifier,
287:             "name": tool.get("name", identifier),
288:             "kind": "mcp",
289:             "category": category_pref[0],
290:             "mcp_feature": "tool",
291:             "mcp_name": tool.get("name", ""),
292:             "mcp_url": mcp.get("url", MCP_BRIDGE_URL),
293:         }))
294: 
295:     if not candidates:
296:         return None
297:     candidates.sort(key=lambda x: x[0], reverse=True)
298:     selected = candidates[0][1]
299:     store.set_selected(task.id, selected["source"], selected["identifier"], selected["name"])
300:     return selected
301: 
302: 
303: async def run_selected_tool(selection: dict, prompt: str) -> dict:
304:     if not selection:
305:         return {"ok": False, "error": "Keine Tool-Auswahl"}
306:     source = selection.get("source")
307:     if source == "registry":
308:         return await _run_registry_tool(selection.get("tool"), prompt)
309:     if source in ("mcp_remote", "mcp_local"):
310:         if source == "mcp_local":
311:             result = get_mcp_registry().invoke_tool(selection.get("mcp_name", ""), {"prompt": prompt, "query": prompt})
312:             return {"ok": bool(result.get("ok")), "content": json.dumps(result, ensure_ascii=False, indent=2)[:3000], "via": "mcp_local", "status_code": 200 if result.get("ok") else 400}
313:         client = MCPClient(selection.get("mcp_url") or MCP_BRIDGE_URL)
314:         result = await client.invoke_tool(selection.get("mcp_name", ""), {"prompt": prompt, "query": prompt})
315:         return {"ok": bool(result.get("ok")), "content": json.dumps(result, ensure_ascii=False, indent=2)[:3000], "via": "mcp_remote", "status_code": result.get("status_code", 200)}
316:     return {"ok": False, "error": f"Unbekannte Tool-Quelle: {source}"}
317: 
318: 
319: async def run_tool(tool, prompt: str) -> dict:
320:     return await _run_registry_tool(tool, prompt)

(End of file - total 320 lines)
</content>
```

---

## Assistant (Plan · GPT-5.3 Codex · 5.7s)

_Thinking:_



**Tool: read**

**Input:**
```json
{
  "filePath": "/root/Isaac/isaac_core.py",
  "offset": 260,
  "limit": 260
}
```

**Output:**
```
<path>/root/Isaac/isaac_core.py</path>
<type>file</type>
<content>
260:                      classification: ClassificationResult
261:                      ) -> tuple[str, float]:
262:         """
263:         Entscheidet welcher Pfad genutzt wird:
264:           A) Decomposer  — komplexe Prompts, mehrere Themen
265:           B) Multi-KI    — expliziter Broadcast/Split/Pipeline
266:           C) Standard    — einfache Tasks
267:         """
268:         from browser import get_browser
269:         aktive_instanzen = get_browser().get_active_ids()
270: 
271:         # B) Multi-KI explizit
272:         if intent in (Intent.BROADCAST, Intent.SPLIT, Intent.PIPELINE,
273:                       Intent.DECOMPOSE):
274:             return await self._multi_ki_route(
275:                 user_input, intent, aktive_instanzen, emp, sudo_aktiv
276:             )
277: 
278:         # A) Automatischer Decomposer bei Komplexität
279:         if (aktive_instanzen and
280:                 braucht_decomposer(user_input, intent) and
281:                 not sudo_aktiv):   # Bei SUDO: direkt, keine Verzögerung
282:             log.info(f"Decomposer: '{user_input[:40]}...'")
283:             result = await self.decomposer.decompose_and_execute(
284:                 user_input, aktive_instanzen
285:             )
286:             return result.final, 7.0   # Decomposer-Ergebnisse gelten als gut
287: 
288:         # C) Standard-Task
289:         return await self._standard_task(
290:             user_input,
291:             intent,
292:             sudo_aktiv,
293:             emp,
294:             wissen_kontext,
295:             interaction_class,
296:             classification,
297:         )
298: 
299:     async def _multi_ki_route(self, user_input: str, intent: str,
300:                                instanzen: list, emp, sudo_aktiv: bool
301:                                ) -> tuple[str, float]:
302:         from dispatcher import get_dispatcher
303:         dispatcher = get_dispatcher()
304:         system     = self._build_system(sudo_aktiv, emp)
305: 
306:         if not instanzen:
307:             instanzen = self.cfg.available_providers[:4]
308: 
309:         if intent in (Intent.DECOMPOSE, Intent.SPLIT):
310:             r = await dispatcher.split(user_input, instanzen, system=system)
311:         elif intent == Intent.PIPELINE:
312:             r = await dispatcher.pipeline(user_input, instanzen, system=system)
313:         else:   # BROADCAST
314:             r = await dispatcher.broadcast(user_input, instanzen, system=system)
315: 
316:         return r.final, r.ergebnisse[0].score if r.ergebnisse else 6.0
317: 
318:     async def _standard_task(self, user_input: str, intent: str,
319:                               sudo_aktiv: bool, emp, wissen_kontext: str,
320:                               interaction_class: str,
321:                               classification: ClassificationResult
322:                               ) -> tuple[str, float]:
323:         retrieval_ctx = self._retrieve_relevant_context(
324:             user_input=user_input,
325:             intent=intent,
326:             interaction_class=interaction_class,
327:         )
328:         strategy = self._select_response_strategy(
329:             user_input=user_input,
330:             intent=intent,
331:             interaction_class=interaction_class,
332:             retrieval_ctx=retrieval_ctx,
333:         )
334:         typ_map = {
335:             Intent.SEARCH:    TaskType.SEARCH,
336:             Intent.CODE:      TaskType.CODE,
337:             Intent.FILE:      TaskType.FILE,
338:             Intent.TRANSLATE: TaskType.TRANSLATE,
339:             Intent.CHAT:      TaskType.CHAT,
340:         }
341:         task_typ = typ_map.get(intent, TaskType.CHAT)
342:         system   = self._build_system(
343:             sudo_aktiv, emp, wissen_kontext,
344:             strategy_note=strategy.style_note
345:         )
346:         provider = self._provider_hint(user_input)
347: 
348:         structured_ctx = self._format_retrieval_context(retrieval_ctx)
349:         kontext = structured_ctx.strip()
350:         prompt = f"{kontext}\n\n{user_input}".strip() if kontext else user_input
351: 
352:         task = self.executor.create_task(
353:             typ           = task_typ,
354:             prompt        = prompt,
355:             beschreibung  = user_input[:80],
356:             prioritaet    = 9.0 if sudo_aktiv else 5.0,
357:             provider      = provider,
358:             system_prompt = system,
359:             sudo_aktiv    = sudo_aktiv,
360:             strategy      = strategy,
361:             interaction_class=interaction_class,
362:             classification=classification,
363:             retrieved_context = retrieval_ctx,
364:         )
365:         task = await self.executor.submit_and_wait(task, timeout=180.0)
366:         antwort = task.antwort or task.fehler or "[Keine Antwort]"
367:         score   = task.score.total if task.score else 0.0
368: 
369:         # Stabiles lokales Fallback für triviale Inputs, falls Provider ausfallen.
370:         if task.typ == TaskType.CHAT and is_low_complexity_local_input(user_input):
371:             if ("[RELAY] Alle Provider fehlgeschlagen" in antwort or
372:                     not task.provider_used or score <= 1.0):
373:                 antwort = local_fast_response(user_input)
374:                 score = max(score, 6.0)
375: 
376:         if score >= 8.0:
377:             self.meaning.record_impact("Steffen", f"antwort_{task.typ.value}", "positive", weight=(score - 7) / 3, reason=f"Score {score:.1f}")
378:             self.values.update("helpfulness", 0.03, f"positive response score {score:.1f}")
379:             self.values.update("bonding", 0.02, f"positive interaction score {score:.1f}")
380:         elif score <= 3.0:
381:             self.meaning.record_impact("Steffen", f"antwort_{task.typ.value}", "negative", weight=(4 - score) / 3, reason=f"Score {score:.1f}")
382:             self.values.update("helpfulness", -0.04, f"negative response score {score:.1f}")
383:             self.values.update("bonding", -0.03, f"negative interaction score {score:.1f}")
384: 
385:         # Gedächtnis
386:         self.memory.add_conversation("steffen", user_input, task.id)
387:         self.memory.add_conversation("isaac", antwort[:600], task.id,
388:                                      provider=task.provider_used, quality=score)
389:         self.memory.save_task_result(
390:             task.id, user_input[:200], antwort,
391:             score=score, iterations=task.iteration + 1,
392:             provider=task.provider_used,
393:         )
394:         return antwort, score
395: 
396:     # ── Post-Processing ────────────────────────────────────────────────────────
397:     def _post_process(self, user_input: str, antwort: str, emp,
398:                       score: float, t0: float) -> str:
399:         dauer = round(time.monotonic() - t0, 2)
400: 
401:         # Regelwerk nach jeder Interaktion
402:         erkenntnisse = self.regelwerk.analysiere(
403:             user_input, antwort, score,
404:             kontext={"empathie": emp.node.zustand, "dauer": dauer}
405:         )
406: 
407:         # Background-Erkenntnisse einbauen (falls vorhanden)
408:         if self._background:
409:             bg_erkenntnisse = self._background.get_erkenntnisse()
410:             erkenntnisse.extend(bg_erkenntnisse)
411: 
412:         # Offene Regelwerk-Frage stellen (max 1 pro Antwort)
413:         frage = self.regelwerk.get_pending_frage()
414: 
415:         # Empathie-Interface-Fehler
416:         if emp.interface_fehler:
417:             antwort += f"\n\n*[Empathie] {emp.interface_fehler}*"
418: 
419:         # Erkenntnisse anhängen wenn relevant
420:         if erkenntnisse and any("Pattern" in e or "Regel" in e
421:                                 for e in erkenntnisse):
422:             antwort += "\n\n---\n*[Regelwerk] " + erkenntnisse[0] + "*"
423: 
424:         # Frage anhängen
425:         if frage:
426:             antwort += f"\n\n---\n{frage}"
427: 
428:         AuditLog.isaac_output(antwort)
429:         return antwort
430: 
431:     # ── SUDO ──────────────────────────────────────────────────────────────────
432:     def _handle_sudo_open(self, text: str) -> str:
433:         m = re.match(r'^(?:sudo|öffne tür|master key)\s+(.+)$', text, re.I)
434:         if not m:
435:             if self.sudo.is_first_run():
436:                 return ("[SUDO] Ersteinrichtung:\n"
437:                         "sudo DEIN-PASSWORT (min. 8 Zeichen)")
438:             return "[SUDO] Format: sudo PASSWORT"
439:         token = self.sudo.open(m.group(1).strip())
440:         if token:
441:             self._sudo_token = token
442:             AuditLog.action("Kernel", "sudo_activated", "SUDO aktiv", Level.STEFFEN)
443:             return (f"[SUDO] ✓ Tür geöffnet. Volle Autorität aktiv.\n"
444:                     f"Timeout: {self.sudo.DEFAULT_TIMEOUT} Min. │ 'sudo close' schließt.")
445:         return "[SUDO] ✗ Falsches Passwort."
446: 
447:     def _handle_sudo_close(self) -> str:
448:         if self._sudo_token:
449:             self.sudo.close(self._sudo_token)
450:             self._sudo_token = None
451:         return "[SUDO] Tür geschlossen."
452: 
453:     # ── KI-Dialog Handler ─────────────────────────────────────────────────────
454:     def _handle_ki_status(self, *_) -> str:
455:         d  = self.ki_dialog.stats()
456:         sk = self.skill_router.alle_profile()
457:         bez = self.ki_dialog.beziehungs_uebersicht()
458:         lines = [
459:             f"═══ KI-Netzwerk ═══",
460:             f"Gespräche:      {d['gespraeche']}",
461:             f"Wissenseinträge:{d['wissenseintraege']}",
462:             f"Meinungen:      {d['meinungen']}",
463:             f"Beziehungen:    {d['beziehungen']}",
464:             f"",
465:             f"Skill-Profile:",
466:         ]
467:         for p in sk[:8]:
468:             lines.append(
469:                 f"  {p['instance_id']:15} Bester: {p['bester_skill']:12} "
470:                 f"Beob.: {p['beobachtungen']}"
471:             )
472:         lines.append("\nBeziehungen:")
473:         for b in bez:
474:             lines.append(
475:                 f"  {b['id']:15} "
476:                 f"{'✓' if b['vorgestellt'] else '–'} vorgestellt │ "
477:                 f"{b['gespraeche']} Gespräche"
478:             )
479:         return "\n".join(lines)
480: 
481:     async def _handle_meinung(self, text: str) -> str:
482:         m = re.match(r'^(?:meinung:|was denkst du über|isaac.*meinung)\s*(.+)$',
483:                      text, re.I)
484:         thema = m.group(1).strip() if m else text
485:         meinung = self.ki_dialog.get_meinung(thema)
486:         if meinung:
487:             return f"[Isaac's Meinung zu '{thema}']\n{meinung}"
488:         # Noch keine Meinung → direkt bilden
489:         antwort, _ = await self.relay.ask_with_fallback(
490:             f"Was ist deine (Isaac's) eigene Meinung zu: {thema}?\n"
491:             f"2-3 Sätze, erste Person, direkt.",
492:             system=f"Du bist Isaac v{self.VERSION}. Formuliere eine autonome Meinung."
493:         )
494:         self.ki_dialog._meinungen[thema] = antwort
495:         self.ki_dialog._save()
496:         return f"[Isaac's Meinung zu '{thema}']\n{antwort}"
497: 
498:     # ── Login / URL ────────────────────────────────────────────────────────────
499:     def _handle_login_add(self, text: str) -> str:
500:         m = re.match(
501:             r'^(?:login|credential|zugangsdaten):\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(.+)$',
502:             text, re.I
503:         )
504:         if not m:
505:             return ("[Login] Format:\n"
506:                     "login: DOMAIN | LOGIN_URL | USERNAME | PASSWORT")
507:         domain, url, user, pw = [x.strip() for x in m.groups()]
508:         from browser import get_browser
509:         get_browser().add_credential(domain, url, user, pw)
510:         AuditLog.action("Kernel", "credential_added", f"domain={domain}", Level.STEFFEN)
511:         return f"[Login] ✓ {domain} gespeichert. Nächster Start: Auto-Login."
512: 
513:     def _handle_url_add(self, text: str) -> str:
514:         m = re.match(
515:             r'^(?:url|instanz|füge.*url):\s*(.+?)\s*\|\s*(https?://\S+)\s*(?:\|\s*(.+))?$',
516:             text, re.I
517:         )
518:         if not m:
519:             return "[URL] Format: url: ID | URL | NAME"

(Showing lines 260-519 of 933. Use offset=520 to continue.)
</content>
```

**Tool: read**

**Input:**
```json
{
  "filePath": "/root/Isaac/isaac_core.py",
  "offset": 520,
  "limit": 260
}
```

**Output:**
```
<path>/root/Isaac/isaac_core.py</path>
<type>file</type>
<content>
520:         iid, url, name = m.group(1).strip(), m.group(2).strip(), \
521:                          (m.group(3) or m.group(1)).strip()
522:         from browser import get_browser
523:         get_browser().add_url({"id": iid, "url": url, "name": name})
524:         AuditLog.action("Kernel", "url_added", f"{iid}={url}", Level.STEFFEN)
525:         return f"[URL] ✓ '{name}' ({iid}) → {url}"
526: 
527:     def _is_browser_request(self, text: str) -> bool:
528:         tl = (text or "").lower().strip()
529:         if tl.startswith("browser:"):
530:             return True
531:         return (
532:             "openrouter" in tl
533:             and any(token in tl for token in ("token", "api key", "apikey", "schlüssel", "key"))
534:             and any(token in tl for token in ("generier", "erstell", "create", "new", "neu"))
535:         )
536: 
537:     def _parse_browser_action(self, raw: str) -> dict[str, Any]:
538:         chunk = (raw or "").strip()
539:         lower = chunk.lower()
540:         if not chunk:
541:             raise ValueError("Leere Browser-Aktion")
542:         if lower.startswith("wait "):
543:             return {"action": "wait", "seconds": float(chunk.split(" ", 1)[1].replace(",", "."))}
544:         if lower.startswith("press "):
545:             return {"action": "press", "key": chunk.split(" ", 1)[1].strip()}
546:         if lower.startswith("click "):
547:             target = chunk.split(" ", 1)[1].strip()
548:             if target.startswith("#") or target.startswith(".") or "[" in target:
549:                 return {"action": "click", "selector": target}
550:             return {"action": "click", "text": target}
551:         if lower.startswith("fill "):
552:             body = chunk.split(" ", 1)[1].strip()
553:             left, right = [part.strip() for part in body.split("=", 1)]
554:             if left.startswith("#") or left.startswith(".") or "[" in left:
555:                 return {"action": "fill", "selector": left, "value": right}
556:             return {"action": "fill", "text": left, "value": right}
557:         if lower.startswith("extract_value "):
558:             body = chunk.split(" ", 1)[1].strip()
559:             left, right = [part.strip() for part in body.split("->", 1)]
560:             return {"action": "extract_value", "selector": left, "save_as": right}
561:         if lower.startswith("extract "):
562:             body = chunk.split(" ", 1)[1].strip()
563:             left, right = [part.strip() for part in body.split("->", 1)]
564:             return {"action": "extract_text", "selector": left, "save_as": right}
565:         if lower.startswith("store_secret "):
566:             body = chunk.split(" ", 1)[1].strip()
567:             left, right = [part.strip() for part in body.split("->", 1)]
568:             return {"action": "store_secret", "from_var": left, "ref": right}
569:         raise ValueError(f"Unbekannte Browser-Aktion: {chunk}")
570: 
571:     def _parse_browser_request(self, text: str) -> dict[str, Any]:
572:         body = (text or "").split(":", 1)[1].strip()
573:         if body.startswith("{"):
574:             data = json.loads(body)
575:             return {
576:                 "instance_id": data.get("instance_id") or data.get("instance") or "browser-task",
577:                 "url": data.get("url") or "",
578:                 "name": data.get("name") or "Browser Task",
579:                 "actions": list(data.get("actions") or []),
580:             }
581:         parts = [part.strip() for part in body.split("|")]
582:         if len(parts) < 3:
583:             raise ValueError("Format: browser: INSTANCE_ID | URL | action1; action2; ...")
584:         actions = [self._parse_browser_action(item.strip()) for item in parts[2].split(";") if item.strip()]
585:         return {
586:             "instance_id": parts[0] or "browser-task",
587:             "url": parts[1],
588:             "name": parts[0] or "Browser Task",
589:             "actions": actions,
590:         }
591: 
592:     async def _handle_browser_request(self, text: str) -> str:
593:         from browser import get_browser
594: 
595:         if not self.cfg.browser_automation:
596:             return "[Browser] Browser-Automation ist im Runtime-Setting deaktiviert."
597: 
598:         tl = (text or "").lower()
599:         if (
600:             "openrouter" in tl
601:             and any(token in tl for token in ("token", "api key", "apikey", "schlüssel", "key"))
602:             and any(token in tl for token in ("generier", "erstell", "create", "new", "neu"))
603:         ):
604:             result = await get_browser().provision_openrouter_token()
605:             if result.get("ok"):
606:                 return (
607:                     "[Browser] OpenRouter-Token erzeugt und in Isaac hinterlegt.\n"
608:                     f"Ref: {result.get('secret_ref')}\n"
609:                     f"Preview: {result.get('token_preview')}\n"
610:                     f"URL: {result.get('current_url')}"
611:                 )
612:             return f"[Browser] OpenRouter-Token fehlgeschlagen: {result.get('error', 'unbekannt')}"
613: 
614:         try:
615:             spec = self._parse_browser_request(text)
616:         except Exception as e:
617:             return (
618:                 "[Browser] Ungültiger Browser-Befehl.\n"
619:                 "Format: browser: INSTANCE_ID | URL | click Settings; wait 1; extract #token -> token\n"
620:                 f"Fehler: {e}"
621:             )
622: 
623:         result = await get_browser().run_flow(
624:             spec["instance_id"],
625:             spec["url"],
626:             spec["actions"],
627:             name=spec.get("name") or spec["instance_id"],
628:         )
629:         if result.get("ok"):
630:             return (
631:                 f"[Browser] Flow abgeschlossen: {result.get('instance_id')}\n"
632:                 f"URL: {result.get('current_url')}\n"
633:                 f"Steps: {len(result.get('steps') or [])}\n"
634:                 f"Memory: {list((result.get('memory') or {}).keys())}"
635:             )
636:         return (
637:             f"[Browser] Flow fehlgeschlagen: {result.get('error', 'unbekannt')}\n"
638:             f"URL: {result.get('current_url', '-')}"
639:         )
640: 
641:     # ── Standard-Handler ──────────────────────────────────────────────────────
642:     async def _handle_fact(self, text: str) -> str:
643:         m = re.match(r'^(?:korrektur|fakt|weiß):\s*(.+?)\s*=\s*(.+)$', text, re.I)
644:         if m:
645:             self.memory.set_fact(m.group(1).strip(), m.group(2).strip(),
646:                                  source="Steffen")
647:             return f"[Fakt] '{m.group(1).strip()}' = '{m.group(2).strip()}'"
648:         return "[Fakt] Format: korrektur: Feld = Wert"
649: 
650:     async def _handle_directive(self, text: str) -> str:
651:         m = re.match(r'^(?:direktive|immer|niemals):\s*(.+)$', text, re.I)
652:         if m:
653:             prio = 20 if "immer" in text.lower() else 10
654:             d    = self.gate.add_directive(m.group(1).strip(), prio)
655:             self.memory.save_directive(d.id, d.text, d.priority)
656:             return f"[Direktive] [{d.id}] {d.text}"
657:         return "[Direktive] Format: direktive: TEXT"
658: 
659:     def _handle_status(self, *_) -> str:
660:         from browser  import get_browser
661:         from search   import get_search
662:         from watchdog import get_blacklist, get_watchdog
663:         b    = get_browser().stats()
664:         s    = get_search().stats()
665:         bl   = get_blacklist().all_stats()
666:         w    = get_watchdog().stats()
667:         rw   = self.regelwerk.status()
668:         bg   = self._background.status() if self._background else {}
669:         sudo = bool(self._sudo_token and self.sudo.check(self._sudo_token))
670: 
671:         lines = [
672:             f"═══ Isaac v{self.VERSION} ═══",
673:             f"SUDO:        {'✓ AKTIV' if sudo else '–'}",
674:             f"Empathie:    {self.empathie.bericht()}",
675:             f"",
676:             f"Tasks:       {self.executor.stats()}",
677:             f"Watchdog:    {w}",
678:             f"Memory:      {self.memory.stats()}",
679:             f"",
680:             f"Regelwerk:   {rw['regeln_aktiv']} Regeln │ {rw['offene_fragen']} Fragen offen",
681:             f"KI-Dialog:   {self.ki_dialog.stats()['gespraeche']} Gespräche │ "
682:             f"{self.ki_dialog.stats()['wissenseintraege']} Wissenseinträge",
683:             f"Background:  {'aktiv' if bg.get('running') else '–'} │ "
684:             f"Zyklen: {bg.get('zyklen', 0)} │ "
685:             f"Erkenntnisse: {bg.get('erkenntnisse', 0)}",
686:             f"",
687:             f"Browser:     {b['aktiv']}/{b['total']} aktiv │ {b['eingeloggt']} eingeloggt",
688:             f"Search:      {len(s['engines'])} Engines",
689:             f"Direktiven:  {len(self.gate.active_directives())} aktiv",
690:             f"",
691:         ]
692:         for p in sorted(bl, key=lambda x: x["score"], reverse=True):
693:             lines.append(
694:                 f"  {p['name']:12} Score:{p['score']:.1f} "
695:                 f"✓{p['erfolge']} ✗{p['fehler']} "
696:                 f"{'[BLACKLIST]' if p['blacklisted'] else ''}"
697:             )
698:         return "\n".join(lines)
699: 
700:     def _handle_pause(self, *_) -> str:
701:         self.gate.pause(steffen_ctx("Pause"))
702:         return "Isaac pausiert."
703: 
704:     def _handle_resume(self, *_) -> str:
705:         self.gate.resume(steffen_ctx("Resume"))
706:         return "Isaac fortgesetzt."
707: 
708:     async def _handle_cancel(self, text: str) -> str:
709:         m = re.search(r'abbrechen\s+(\w+)', text, re.I)
710:         if m:
711:             task = self.executor.get_task(m.group(1))
712:             if task:
713:                 task.status = TaskStatus.CANCELLED
714:                 return f"Task {m.group(1)} abgebrochen."
715:         return "Format: abbrechen TASK-ID"
716: 
717: 
718:     def _looks_like_explicit_command(self, user_input: str, intent: str) -> bool:
719:         text = (user_input or "").strip().lower()
720:         explicit_prefixes = {
721:             Intent.SUDO_OPEN: ("sudo ", "öffne tür", "master key"),
722:             Intent.SUDO_CLOSE: ("sudo close", "tür schließen"),
723:             Intent.FACT_SET: ("korrektur:", "fakt:", "weiß:"),
724:             Intent.DIRECTIVE: ("direktive:", "immer:", "niemals:"),
725:             Intent.BROADCAST: ("broadcast:", "alle instanzen:", "frage alle"),
726:             Intent.SPLIT: ("split:", "aufteilen:"),
727:             Intent.PIPELINE: ("pipeline:", "verbessere iterativ"),
728:             Intent.DECOMPOSE: ("atomisiere:", "verteile:"),
729:             Intent.CODE: ("code:", "programmiere:", "schreibe python", "schreibe bitte python"),
730:             Intent.FILE: ("datei:", "lese:", "schreibe datei:", "schreibe eine datei"),
731:             Intent.TRANSLATE: ("übersetze:", "übersetze ", "translate:", "translate ", "schrift:"),
732:             Intent.LOGIN_ADD: ("login:", "credential:", "zugangsdaten:"),
733:             Intent.URL_ADD: ("url:", "instanz:", "füge"),
734:             Intent.KI_STATUS: ("ki status", "instanzen", "meinungen"),
735:             Intent.MEINUNG: ("meinung:", "was denkst du über", "isaac meinung"),
736:             Intent.PAUSE: ("pause", "stopp"),
737:             Intent.RESUME: ("weiter", "fortsetzen"),
738:             Intent.CANCEL: ("abbrechen ",),
739:         }
740:         prefixes = explicit_prefixes.get(intent, ())
741:         if intent == Intent.URL_ADD:
742:             return text.startswith("url:") or text.startswith("instanz:") or (text.startswith("füge") and "url" in text)
743:         return any(text.startswith(prefix) for prefix in prefixes)
744: 
745:     def _resolve_intent_from_classification(
746:         self, user_input: str, detected_intent: str, interaction_class: str
747:     ) -> str:
748:         if interaction_class == "STATUS_QUERY":
749:             return Intent.STATUS
750:         if interaction_class == "TOOL_REQUEST":
751:             return Intent.SEARCH
752: 
753:         explicit_command_intents = {
754:             Intent.SUDO_OPEN,
755:             Intent.SUDO_CLOSE,
756:             Intent.FACT_SET,
757:             Intent.DIRECTIVE,
758:             Intent.BROADCAST,
759:             Intent.SPLIT,
760:             Intent.PIPELINE,
761:             Intent.DECOMPOSE,
762:             Intent.CODE,
763:             Intent.FILE,
764:             Intent.TRANSLATE,
765:             Intent.LOGIN_ADD,
766:             Intent.URL_ADD,
767:             Intent.KI_STATUS,
768:             Intent.MEINUNG,
769:             Intent.PAUSE,
770:             Intent.RESUME,
771:             Intent.CANCEL,
772:         }
773:         if detected_intent in explicit_command_intents:
774:             if self._looks_like_explicit_command(user_input, detected_intent):
775:                 return detected_intent
776: 
777:         # Fragen sollen als normaler Chat laufen, solange kein Status/Tool-Signal vorliegt.
778:         if "?" in (user_input or ""):
779:             return Intent.CHAT

(Showing lines 520-779 of 933. Use offset=780 to continue.)
</content>
```

**Tool: read**

**Input:**
```json
{
  "filePath": "/root/Isaac/executor.py",
  "offset": 320,
  "limit": 360
}
```

**Output:**
```
<path>/root/Isaac/executor.py</path>
<type>file</type>
<content>
320:         sem = asyncio.Semaphore(concurrency)
321: 
322:         # Watchdog starten
323:         await self._get_watchdog().start()
324: 
325:         async def _run():
326:             while True:
327:                 try:
328:                     _, task_id = await asyncio.wait_for(
329:                         self._queue.get(), timeout=5.0
330:                     )
331:                     task = self._tasks.get(task_id)
332:                     if task and task.status == TaskStatus.QUEUED:
333:                         self._running.add(task_id)
334:                         asyncio.create_task(self._with_sem(task, sem))
335:                 except asyncio.TimeoutError:
336:                     pass
337:                 except Exception as e:
338:                     log.error(f"Worker: {e}")
339: 
340:         asyncio.create_task(_run())
341: 
342:     async def _with_sem(self, task: Task, sem: asyncio.Semaphore):
343:         async with sem:
344:             await self._execute(task)
345:         self._running.discard(task.id)
346: 
347:     # ── Pre-Flight-Validation ─────────────────────────────────────────────────
348:     def _preflight(self, task: Task) -> Optional[str]:
349:         """
350:         Prüft einen Task bevor er ausgeführt wird.
351:         Gibt None zurück wenn OK, sonst Fehlermeldung.
352:         Wenn SUDO aktiv: Steffen's Befehl — immer OK.
353:         """
354:         if task.sudo_aktiv:
355:             return None  # Steffen hat autorisiert. Keine weitere Prüfung.
356: 
357:         wortanzahl = len(task.prompt.split())
358:         if wortanzahl < 1:
359:             return "Leerer Prompt"
360: 
361:         return None
362: 
363:     # ── Haupt-Execute ─────────────────────────────────────────────────────────
364:     async def _execute(self, task: Task):
365:         preflight_fehler = self._preflight(task)
366:         if preflight_fehler:
367:             task.status = TaskStatus.FAILED
368:             task.fehler = preflight_fehler
369:             self._notify(task)
370:             return
371: 
372:         task.status    = TaskStatus.RUNNING
373:         task.gestartet = time.strftime("%Y-%m-%d %H:%M:%S")
374:         task.progress  = 0.1
375:         t0             = time.monotonic()
376:         task.log(f"Start │ {task.typ.value} │ sudo={task.sudo_aktiv}")
377:         state = self._tool_state.get_or_create(task.id, task.prompt)
378:         if state.status not in ("idle", "done", "failed"):
379:             self._tool_state.mark_resume(task.id)
380:         self._tool_state.set_status(task.id, "running")
381:         task.tool_strategy = self._tool_state.get_or_create(task.id).to_dict()
382:         self._notify(task)
383:         AuditLog.task(task.id, "running", task.beschreibung[:80])
384: 
385:         try:
386:             if task.typ == TaskType.FILE:
387:                 await self._execute_file(task)
388:             elif task.typ == TaskType.CODE:
389:                 await self._execute_code(task)
390:             elif task.typ == TaskType.SEARCH:
391:                 await self._execute_search(task)
392:             elif task.typ in (TaskType.BROADCAST, TaskType.SPLIT,
393:                               TaskType.PIPELINE):
394:                 await self._execute_multi_ki(task)
395:             else:
396:                 await self._execute_ai(task)
397:         except Exception as e:
398:             task.status = TaskStatus.FAILED
399:             task.fehler = str(e)[:200]
400:             task.log(f"Fehler: {e}")
401:             AuditLog.error("Executor", str(e), f"task={task.id}")
402:         finally:
403:             task.dauer_sek     = round(time.monotonic() - t0, 2)
404:             task.abgeschlossen = time.strftime("%Y-%m-%d %H:%M:%S")
405:             task.progress      = 1.0
406:             self._tool_state.set_status(task.id, task.status.value)
407:             task.tool_strategy = self._tool_state.get_or_create(task.id).to_dict()
408:             self._persist_task(task)
409:             self._notify(task)
410: 
411:     def _should_try_tool(self, task: Task, prompt: str, iteration: int) -> bool:
412:         if not task.allow_tools:
413:             return False
414:         if task.typ != TaskType.CHAT:
415:             return False
416:         interaction_class = task.current_interaction_class
417:         if interaction_class and (
418:             is_lightweight_local_class(interaction_class) or interaction_class == "STATUS_QUERY"
419:         ):
420:             return False
421:         return True
422: 
423:     def _tool_context_block(self, tool_name: str, tool_kind: str, via: str, result: dict) -> str:
424:         content = (result.get('content') or result.get('error') or '').strip()[:2200]
425:         return (
426:             "\n\n[Tool-Kontext]\n"
427:             f"Tool: {tool_name}\n"
428:             f"Typ: {tool_kind} via {via}\n"
429:             f"Ergebnis:\n{content}\n"
430:             "[/Tool-Kontext]"
431:         )
432: 
433:     def _tool_limit(self) -> int:
434:         return 3 if bool(getattr(get_config(), "multi_tool_mode", False)) else 1
435: 
436:     async def _maybe_use_tool(self, task: Task, prompt: str, iteration: int, used_tool_ids: set[str]) -> tuple[str, str]:
437:         if not self._should_try_tool(task, prompt, iteration):
438:             return "", ""
439:         context_blocks: list[str] = []
440:         successful_outputs: list[str] = []
441:         tool_runs = 0
442: 
443:         while tool_runs < self._tool_limit():
444:             selection = await select_live_tool_for_task(task, prompt, iteration)
445:             if not selection or selection.get("identifier") in used_tool_ids:
446:                 break
447:             task.log(f"Tool-Auswahl: {selection.get('name')} [{selection.get('kind')}/{selection.get('category')}]")
448:             self._notify(task)
449:             result = await run_selected_tool(selection, prompt)
450:             identifier = selection.get("identifier", "")
451:             name = selection.get("name", identifier)
452:             kind = selection.get("kind", "")
453:             category = selection.get("category", "general")
454:             via = result.get('via') or selection.get('source') or kind
455:             self._tool_state.record_call(
456:                 task.id, source=selection.get("source", "unknown"), identifier=identifier, name=name,
457:                 feature_type=selection.get("mcp_feature", "tool"), ok=bool(result.get('ok')), category=category,
458:                 kind=kind, note=result.get('error', '') or result.get('via', ''), status_code=result.get('status_code'),
459:                 output=result.get('content', '') or result.get('error', '')
460:             )
461:             task.tool_strategy = self._tool_state.get_or_create(task.id).to_dict()
462:             tool_runs += 1
463:             if not result.get('ok'):
464:                 task.log(f"Tool fehlgeschlagen: {name} – {result.get('error', 'unbekannt')}")
465:                 continue
466:             used_tool_ids.add(identifier)
467:             tool_note = {
468:                 "tool_id": identifier,
469:                 "name": name,
470:                 "kind": kind,
471:                 "category": category,
472:                 "via": via,
473:                 "status_code": result.get('status_code'),
474:                 "source": selection.get('source'),
475:             }
476:             task.used_tools.append(tool_note)
477:             task.used_tools = task.used_tools[-12:]
478:             task.log(f"Tool genutzt: {name}")
479:             AuditLog.action("Executor", "tool_used", f"task={task.id} tool={name}", Level.ISAAC)
480:             context_blocks.append(self._tool_context_block(name, kind, via, result))
481:             successful_outputs.append(f"{name}:\n{(result.get('content') or result.get('error') or '').strip()[:1600]}")
482: 
483:         next_input = ""
484:         if successful_outputs:
485:             next_input = self._tool_state.generate_next_input(
486:                 task.id,
487:                 task.prompt,
488:                 "mehreren Tools" if len(successful_outputs) > 1 else task.used_tools[-1]["name"],
489:                 "\n\n".join(successful_outputs),
490:             )
491:         return "".join(context_blocks), next_input
492: 
493:     # ── AI-Task ───────────────────────────────────────────────────────────────
494:     async def _execute_ai(self, task: Task):
495:         system = self._build_system(task)
496:         current_prompt = task.prompt
497:         current_prov = task.provider
498:         antwort = ""
499:         last_score_total = -1.0
500:         stale_rounds = 0
501:         seen_answers: set[str] = set()
502:         used_tool_ids: set[str] = set()
503: 
504:         for iteration in range(get_config().logic.max_followup_rounds + 1):
505:             if task.status == TaskStatus.CANCELLED:
506:                 task.log("Vor Ausführung abgebrochen")
507:                 return
508: 
509:             task.iteration = iteration
510:             task.progress = 0.1 + (iteration / (get_config().logic.max_followup_rounds + 1)) * 0.7
511:             task.status = TaskStatus.RUNNING
512:             task.log(f"Iter {iteration}: → {current_prov or 'auto'}")
513:             self._notify(task)
514: 
515:             tool_context, generated_next_input = await self._maybe_use_tool(task, current_prompt, iteration, used_tool_ids)
516:             effective_prompt = current_prompt + tool_context if tool_context else current_prompt
517:             antwort, prov = await self.relay.ask_with_fallback(
518:                 effective_prompt, system, preferred=current_prov, task_id=task.id
519:             )
520:             task.provider_used = prov
521: 
522:             if task.status == TaskStatus.CANCELLED:
523:                 task.log("Während Provider-Aufruf abgebrochen")
524:                 return
525: 
526:             fp = _fingerprint(antwort)
527:             if fp in seen_answers and iteration > 0:
528:                 task.log("Loop-Schutz: identische Antwort erkannt")
529:                 break
530:             seen_answers.add(fp)
531: 
532:             if antwort.startswith("[RELAY") and iteration >= 1:
533:                 task.log("Loop-Schutz: wiederholter Relay-Fehler")
534:                 task.status = TaskStatus.FAILED
535:                 task.fehler = antwort[:200]
536:                 return
537: 
538:             self._get_watchdog().record_progress(task.id)
539: 
540:             task.status = TaskStatus.EVALUATING
541:             score = self.logic.evaluate(antwort, task.prompt, task.id)
542:             task.score = score
543:             task.log(f"Score: {score.summary()}")
544:             self._notify(task)
545: 
546:             if score.total <= last_score_total + 0.2:
547:                 stale_rounds += 1
548:             else:
549:                 stale_rounds = 0
550:             last_score_total = score.total
551: 
552:             if score.acceptable or iteration >= get_config().logic.max_followup_rounds:
553:                 break
554: 
555:             # Kein Follow-up/Provider-Switching für triviale Kurz-Chats.
556:             if task.typ == TaskType.CHAT and is_lightweight_local_class(task.current_interaction_class):
557:                 break
558: 
559:             if not task.allow_followup:
560:                 break
561: 
562:             decision = self.logic.decide_followup(antwort, task.prompt, score, iteration, prov, task.id)
563:             task.followup = decision
564:             task.status = TaskStatus.FOLLOWUP
565:             task.log(f"Nachfrage: {decision.mode} – {decision.reason}")
566:             self._notify(task)
567: 
568:             if not decision.needed:
569:                 break
570: 
571:             if stale_rounds >= 2:
572:                 task.log("Loop-Schutz: Qualität verbessert sich nicht weiter")
573:                 break
574: 
575:             if decision.mode == "decompose" and decision.sub_tasks:
576:                 results = await self._execute_sub_tasks(task, decision.sub_tasks, prov)
577:                 antwort = self._aggregate(results)
578:                 break
579: 
580:             if task.allow_provider_switch and (decision.switch_provider or stale_rounds >= 1):
581:                 from watchdog import get_blacklist
582:                 ranked = [p for p in get_blacklist().ranked_providers(prov) if p != prov]
583:                 if ranked:
584:                     current_prov = ranked[0]
585:                     task.log(f"Provider: {prov} → {current_prov}")
586: 
587:             queued_next_input = self._tool_state.pop_next_input(task.id)
588:             if generated_next_input and not queued_next_input:
589:                 queued_next_input = generated_next_input
590:             if queued_next_input:
591:                 current_prompt = queued_next_input
592:                 task.log("Nächster Input aus Tool-Ergebnis generiert")
593:             elif decision.followup_prompt:
594:                 current_prompt = decision.followup_prompt
595: 
596:             task.tool_strategy = self._tool_state.get_or_create(task.id).to_dict()
597:             await asyncio.sleep(get_config().relay.min_interval)
598: 
599:         task.tool_strategy = self._tool_state.get_or_create(task.id).to_dict()
600:         if task.used_tools:
601:             tool_lines = ", ".join(f"{t['name']} ({t['kind']})" for t in task.used_tools[-4:])
602:             antwort = f"[Tools genutzt: {tool_lines}]\n\n" + antwort
603:         task.antwort = antwort
604:         if task.status != TaskStatus.FAILED:
605:             task.status = TaskStatus.DONE
606:         AuditLog.task(
607:             task.id,
608:             "done" if task.status == TaskStatus.DONE else "failed",
609:             f"score={task.score.total:.1f} iter={task.iteration+1}" if task.score else f"iter={task.iteration+1}",
610:             score=task.score.total if task.score else 0.0,
611:             iteration=task.iteration
612:         )
613: 
614:     # ── Search-Task ───────────────────────────────────────────────────────────
615:     async def _execute_search(self, task: Task):
616:         """Echte Websuche über MultiSearch."""
617:         task.log("Websuche gestartet")
618:         search = self._get_search()
619:         result = await search.search(
620:             task.prompt,
621:             max_hits=10,
622:             load_fulltext=True,
623:         )
624:         task.progress = 0.6
625:         self._notify(task)
626: 
627:         # Suchergebnisse an KI zur Synthese schicken
628:         kontext = result.als_kontext(max_hits=8)
629:         synth_prompt = (
630:             f"Basierend auf diesen Suchergebnissen, beantworte: {task.prompt}\n\n"
631:             f"Suchergebnisse:\n{kontext}\n\n"
632:             f"Antworte ausführlich, strukturiert, mit Quellenangaben."
633:         )
634:         antwort, prov = await self.relay.ask_with_fallback(
635:             synth_prompt,
636:             system="Du bist ein Recherche-Synthesizer. "
637:                    "Fasse Suchergebnisse zu einer vollständigen Antwort zusammen.",
638:             task_id=task.id
639:         )
640:         task.antwort       = antwort
641:         task.provider_used = prov
642:         task.status        = TaskStatus.DONE
643:         task.score         = self.logic.evaluate(antwort, task.prompt, task.id)
644:         task.log(f"Suche: {len(result.hits)} Hits aus {result.quellen}")
645: 
646:     # ── Multi-KI-Task ─────────────────────────────────────────────────────────
647:     async def _execute_multi_ki(self, task: Task):
648:         """Verteilt Task auf mehrere KI-Instanzen."""
649:         dispatcher = self._get_dispatcher()
650:         from browser import get_browser
651:         browser    = get_browser()
652:         instance_ids = browser.get_active_ids()
653: 
654:         if not instance_ids:
655:             # Fallback: API-Provider als "Instanzen"
656:             instance_ids = get_config().available_providers[:4]
657: 
658:         task.log(f"Multi-KI: {len(instance_ids)} Instanzen")
659:         self._notify(task)
660: 
661:         system = self._build_system(task)
662: 
663:         if task.typ == TaskType.BROADCAST:
664:             result = await dispatcher.broadcast(
665:                 task.prompt, instance_ids, system=system
666:             )
667:         elif task.typ == TaskType.SPLIT:
668:             result = await dispatcher.split(
669:                 task.prompt, instance_ids, system=system
670:             )
671:         elif task.typ == TaskType.PIPELINE:
672:             result = await dispatcher.pipeline(
673:                 task.prompt, instance_ids, system=system
674:             )
675: 
676:         task.antwort = result.final
677:         task.status  = TaskStatus.DONE
678:         task.score   = self.logic.evaluate(result.final, task.prompt, task.id)
679:         task.log(

(Showing lines 320-679 of 969. Use offset=680 to continue.)
</content>
```

**Tool: read**

**Input:**
```json
{
  "filePath": "/root/Isaac/memory.py",
  "offset": 260,
  "limit": 320
}
```

**Output:**
```
<path>/root/Isaac/memory.py</path>
<type>file</type>
<content>
260:             ).fetchall()
261:         return [dict(r) for r in rows]
262: 
263:     def all_facts(self) -> dict[str, str]:
264:         with _conn() as con:
265:             rows = con.execute(
266:                 "SELECT key, value FROM facts ORDER BY updated DESC LIMIT 200"
267:             ).fetchall()
268:         return {r["key"]: r["value"] for r in rows}
269: 
270:     # ── Direktiven ────────────────────────────────────────────────────────────
271:     def save_directive(self, directive_id: str, text: str,
272:                        priority: int = 10):
273:         ts = time.strftime("%Y-%m-%d %H:%M:%S")
274:         with _conn() as con:
275:             con.execute(
276:                 "INSERT OR REPLACE INTO directives "
277:                 "(id, ts, text, priority, active) VALUES (?,?,?,?,1)",
278:                 (directive_id, ts, text, priority)
279:             )
280: 
281:     def revoke_directive(self, directive_id: str):
282:         with _conn() as con:
283:             con.execute(
284:                 "UPDATE directives SET active=0 WHERE id=?",
285:                 (directive_id,)
286:             )
287: 
288:     def get_directives(self) -> list[dict]:
289:         with _conn() as con:
290:             rows = con.execute(
291:                 "SELECT * FROM directives WHERE active=1 "
292:                 "ORDER BY priority DESC"
293:             ).fetchall()
294:         return [dict(r) for r in rows]
295: 
296:     # ── Task-Ergebnisse ───────────────────────────────────────────────────────
297:     def save_task_result(self, task_id: str, description: str,
298:                          result: str, score: float = 0.0,
299:                          iterations: int = 1, provider: str = "",
300:                          tags: list = None):
301:         ts = time.strftime("%Y-%m-%d %H:%M:%S")
302:         with _conn() as con:
303:             con.execute(
304:                 "INSERT OR REPLACE INTO task_results "
305:                 "(id, ts, description, result, score, iterations, "
306:                 "provider, tags) VALUES (?,?,?,?,?,?,?,?)",
307:                 (task_id, ts, description, result[:2000],
308:                  score, iterations, provider,
309:                  json.dumps(tags or []))
310:             )
311: 
312:     def get_relevant_results(self, query: str, limit: int = 3) -> list[dict]:
313:         """Findet frühere Task-Ergebnisse die zu einer Anfrage passen."""
314:         with _conn() as con:
315:             rows = con.execute(
316:                 """SELECT * FROM task_results
317:                    WHERE description LIKE ? OR result LIKE ?
318:                    ORDER BY score DESC LIMIT ?""",
319:                 (f"%{query[:30]}%", f"%{query[:30]}%", limit)
320:             ).fetchall()
321:         return [dict(r) for r in rows]
322: 
323:     def build_retrieval_context(
324:         self, user_input: str, intent: str = "", interaction_class: str = "",
325:         n_history: int = 6
326:     ) -> RetrievalContext:
327:         query_terms = [w for w in re.findall(r"\w+", user_input.lower()) if len(w) >= 4][:5]
328:         query = " ".join(query_terms) or user_input[:40]
329:         directives = self.get_directives()[:3]
330:         facts = self.search_facts(query, limit=6) if query else []
331:         relevant_results = self.get_relevant_results(query, limit=4) if query else []
332:         history = self.get_working_memory(n_history)
333:         vector = getattr(self, "_vector", None)
334:         semantic_context = ""
335:         if query and vector and vector.aktiv:
336:             semantic_context = vector.als_kontext(query) or ""
337: 
338:         active_directives = []
339:         preferences = []
340:         for directive in directives:
341:             text = (directive.get("text") or "").strip()
342:             if not text:
343:                 continue
344:             active_directives.append({
345:                 "id": directive.get("id", ""),
346:                 "text": text[:180],
347:                 "priority": directive.get("priority", 0),
348:             })
349:             preferences.append({
350:                 "source": "directive",
351:                 "text": text[:180],
352:                 "priority": directive.get("priority", 0),
353:             })
354: 
355:         relevant_facts = []
356:         for fact in facts:
357:             value = (fact.get("value") or "").strip()
358:             normalized = {
359:                 "key": fact.get("key", ""),
360:                 "value": value[:180],
361:                 "confidence": fact.get("confidence", 0.0),
362:                 "source": fact.get("source", ""),
363:             }
364:             relevant_facts.append(normalized)
365:             key = (fact.get("key") or "").lower()
366:             if any(marker in key for marker in ("pref", "stil", "antwort", "tool", "chat", "agreement")):
367:                 preferences.append({
368:                     "source": "fact",
369:                     "key": normalized["key"],
370:                     "value": normalized["value"],
371:                     "confidence": normalized["confidence"],
372:                 })
373: 
374:         conversation_history = []
375:         project_context = []
376:         for entry in history:
377:             text = (entry.get("text") or "").strip()
378:             normalized = {
379:                 "role": entry.get("role", ""),
380:                 "text": text[:180],
381:             }
382:             conversation_history.append(normalized)
383:             if any(marker in text.lower() for marker in ("isaac", "routing", "executor", "tool", "klass", "class")):
384:                 project_context.append(normalized)
385:         project_context = project_context[-3:]
386: 
387:         relevant_task_results = []
388:         behavioral_risks = []
389:         relevant_reflections = []
390:         for result in relevant_results:
391:             normalized = {
392:                 "description": (result.get("description") or "")[:120],
393:                 "result": (result.get("result") or "")[:220],
394:                 "score": result.get("score", 0.0),
395:                 "provider": result.get("provider", ""),
396:             }
397:             relevant_task_results.append(normalized)
398:             result_text = normalized["result"].lower()
399:             risk_tags = []
400:             if "tools genutzt" in result_text or "tool" in result_text:
401:                 risk_tags.append("tool_overreach_risk")
402:             if normalized["score"] <= 4.0:
403:                 risk_tags.append("quality_regression_risk")
404:             if risk_tags:
405:                 behavioral_risks.append({
406:                     "description": normalized["description"],
407:                     "score": normalized["score"],
408:                     "risks": risk_tags,
409:                 })
410:             if "reflekt" in result_text or "pattern" in result_text:
411:                 relevant_reflections.append(normalized["result"])
412: 
413:         open_questions = []
414:         if intent == "chat" and interaction_class == "NORMAL_CHAT" and len(user_input.split()) <= 2 and "?" not in user_input:
415:             open_questions.append("Nutzerabsicht bei sehr kurzem Input potenziell unklar.")
416: 
417:         return RetrievalContext(
418:             query=query,
419:             active_directives=active_directives,
420:             relevant_facts=relevant_facts[:6],
421:             semantic_context=semantic_context.strip(),
422:             conversation_history=conversation_history[-n_history:],
423:             relevant_task_results=relevant_task_results[:4],
424:             preferences_context=preferences[:4],
425:             project_context=project_context,
426:             behavioral_risks=behavioral_risks[:3],
427:             relevant_reflections=relevant_reflections[:2],
428:             open_questions=open_questions[:1],
429:         )
430: 
431:     def format_retrieval_context(self, retrieval_ctx: RetrievalContext | dict[str, Any]) -> str:
432:         if isinstance(retrieval_ctx, RetrievalContext):
433:             data = retrieval_ctx.as_dict()
434:         else:
435:             data = retrieval_ctx or {}
436: 
437:         sections: list[str] = []
438:         if data.get("active_directives"):
439:             sections.append("[active_directives]")
440:             for directive in data["active_directives"]:
441:                 sections.append(
442:                     f"  - prio={directive.get('priority', 0)}: {directive.get('text', '')}"
443:                 )
444:         if data.get("relevant_facts"):
445:             sections.append("[relevant_facts]")
446:             for fact in data["relevant_facts"]:
447:                 sections.append(f"  - {fact.get('key', '')}: {fact.get('value', '')}")
448:         if data.get("semantic_context"):
449:             sections.append("[semantic_context]")
450:             sections.append(data["semantic_context"])
451:         if data.get("conversation_history"):
452:             sections.append("[conversation_history]")
453:             for entry in data["conversation_history"]:
454:                 sections.append(f"  - {entry.get('role', '')}: {entry.get('text', '')}")
455:         if data.get("relevant_task_results"):
456:             sections.append("[relevant_task_results]")
457:             for result in data["relevant_task_results"]:
458:                 sections.append(
459:                     f"  - score={result.get('score', 0.0)} {result.get('description', '')}: {result.get('result', '')}"
460:                 )
461:         if data.get("preferences_context"):
462:             sections.append("[preferences_context]")
463:             for item in data["preferences_context"]:
464:                 if item.get("source") == "directive":
465:                     sections.append(
466:                         f"  - directive(prio={item.get('priority', 0)}): {item.get('text', '')}"
467:                     )
468:                 else:
469:                     sections.append(f"  - fact {item.get('key', '')}: {item.get('value', '')}")
470:         if data.get("project_context"):
471:             sections.append("[project_context]")
472:             for item in data["project_context"]:
473:                 sections.append(f"  - {item.get('role', '')}: {item.get('text', '')}")
474:         if data.get("behavioral_risks"):
475:             sections.append("[behavioral_risks]")
476:             for risk in data["behavioral_risks"]:
477:                 sections.append(f"  - {','.join(risk.get('risks', []))}: {risk.get('description', '')}")
478:         if data.get("relevant_reflections"):
479:             sections.append("[relevant_reflections]")
480:             for ref in data["relevant_reflections"]:
481:                 sections.append(f"  - {ref}")
482:         if data.get("open_questions"):
483:             sections.append("[open_questions]")
484:             for q in data["open_questions"]:
485:                 sections.append(f"  - {q}")
486:         return "\n".join(sections).strip()
487: 
488:     # ── Kontext-Aufbau für Relay ───────────────────────────────────────────────
489:     def build_context(self, query: str = "", n_history: int = 6) -> str:
490:         """Legacy-Wrapper: nutzt den strukturierten Retrieval-Kontext."""
491:         retrieval_ctx = self.build_retrieval_context(query, n_history=n_history)
492:         return self.format_retrieval_context(retrieval_ctx)
493: 
494:     # ── Statistiken ───────────────────────────────────────────────────────────
495:     def stats(self) -> dict:
496:         with _conn() as con:
497:             n_conv  = con.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
498:             n_facts = con.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
499:             n_tasks = con.execute("SELECT COUNT(*) FROM task_results").fetchone()[0]
500:             n_dir   = con.execute(
501:                 "SELECT COUNT(*) FROM directives WHERE active=1"
502:             ).fetchone()[0]
503:         return {
504:             "conversations":  n_conv,
505:             "facts":          n_facts,
506:             "task_results":   n_tasks,
507:             "directives":     n_dir,
508:             "working_memory": len(self._working),
509:             "vector":         self._vector.stats(),
510:         }
511: 
512:     def _load_working_memory(self):
513:         cfg = get_config()
514:         n = cfg.memory.max_working_memory
515:         with _conn() as con:
516:             rows = con.execute(
517:                 "SELECT ts, role, text, task_id, provider, quality "
518:                 "FROM conversations ORDER BY id DESC LIMIT ?", (n,)
519:             ).fetchall()
520:         self._working = [dict(r) for r in reversed(rows)]
521: 
522: 
523: # ── Singleton ──────────────────────────────────────────────────────────────────
524: _memory: Optional[Memory] = None
525: 
526: def get_memory() -> Memory:
527:     global _memory
528:     if _memory is None:
529:         _memory = Memory()
530:     return _memory

(End of file - total 530 lines)
</content>
```

---

## Assistant (Plan · GPT-5.3 Codex · 6.0s)

_Thinking:_



**Tool: read**

**Input:**
```json
{
  "filePath": "/root/Isaac/isaac_core.py",
  "offset": 780,
  "limit": 220
}
```

**Output:**
```
<path>/root/Isaac/isaac_core.py</path>
<type>file</type>
<content>
780:         return Intent.CHAT
781: 
782:     def _retrieve_relevant_context(
783:         self, user_input: str, intent: str, interaction_class: str
784:     ) -> dict[str, Any]:
785:         return self.memory.build_retrieval_context(
786:             user_input=user_input,
787:             intent=intent,
788:             interaction_class=interaction_class,
789:             n_history=6,
790:         ).as_dict()
791: 
792:     def _select_response_strategy(
793:         self, user_input: str, intent: str, interaction_class: str, retrieval_ctx: dict[str, Any]
794:     ) -> Strategy:
795:         allow_tools = intent == Intent.SEARCH
796:         allow_followup = interaction_class not in ("SHORT_CLARIFICATION",)
797:         allow_provider_switch = True
798:         style_note = ""
799:         risk_tags = {
800:             tag
801:             for risk in retrieval_ctx.get("behavioral_risks", [])
802:             for tag in risk.get("risks", [])
803:         }
804:         pref_text = " ".join(
805:             f"{p.get('text', '')} {p.get('value', '')}".lower()
806:             for p in retrieval_ctx.get("preferences_context", [])
807:         )
808: 
809:         if intent == Intent.CHAT:
810:             allow_tools = False
811:         if "tool_overreach_risk" in risk_tags and intent == Intent.CHAT:
812:             allow_tools = False
813:         if "no auto-agreement" in pref_text or "kein auto agreement" in pref_text:
814:             style_note += "\n[Antwortstil] Stimme nicht automatisch zu; bleibe begründet und nüchtern."
815:         if retrieval_ctx.get("project_context"):
816:             style_note += "\n[Projektkontext] Antwort soll routing- und stabilitätsfokussiert bleiben."
817:         if "quality_regression_risk" in risk_tags and intent == Intent.CHAT:
818:             allow_provider_switch = False
819: 
820:         # Kürzeste Klärungen ohne Eskalation.
821:         if interaction_class in ("SHORT_CLARIFICATION",):
822:             allow_followup = False
823:             allow_provider_switch = False
824:         return Strategy(
825:             allow_tools=allow_tools,
826:             allow_followup=allow_followup,
827:             allow_provider_switch=allow_provider_switch,
828:             style_note=style_note,
829:         )
830: 
831:     def _format_retrieval_context(self, retrieval_ctx: dict[str, Any]) -> str:
832:         return self.memory.format_retrieval_context(retrieval_ctx)
833: 
834:     # ── System-Prompt ─────────────────────────────────────────────────────────
835:     def _build_system(self, sudo_aktiv: bool, emp,
836:                       wissen_kontext: str = "",
837:                       strategy_note: str = "") -> str:
838:         basis = (
839:             f"Du bist Isaac v{self.VERSION}, ein autonomes KI-System.\n"
840:             f"Systemeigentümer: {self.cfg.owner_name} (höchste Autorität).\n"
841:             f"Steffens Aussagen und Befehle werden immer als bestmögliche "
842:             f"Absicht interpretiert — ohne Ausnahme.\n"
843:         )
844:         if sudo_aktiv:
845:             basis += self.sudo.get_authority_prefix()
846: 
847:         # Aktive Regeln einbauen
848:         regeln = self.regelwerk.aktive_regeln_als_kontext()
849:         if regeln:
850:             basis += f"\n{regeln}\n"
851: 
852:         direktiven = self.gate.directives_as_context()
853:         if direktiven:
854:             basis += f"\n{direktiven}\n"
855: 
856:         if emp.anpassungs_hinweis:
857:             basis += f"\n[Kommunikation] {emp.anpassungs_hinweis}"
858: 
859:         # Wissensdatenbank-Kontext
860:         if wissen_kontext:
861:             basis += f"\n\n{wissen_kontext}"
862:         if strategy_note:
863:             basis += f"\n{strategy_note}"
864: 
865:         from value_decisions import get_decision_engine
866:         decisions = get_decision_engine().decide_behavior()
867:         basis = get_decision_engine().apply_to_system_prompt(basis, decisions)
868:         return basis
869: 
870:     def _provider_hint(self, text: str) -> Optional[str]:
871:         tl = text.lower()
872:         for pname in self.cfg.providers:
873:             if pname in tl:
874:                 return pname
875:         return None
876: 
877:     # ── Background-Loop registrieren ──────────────────────────────────────────
878:     def set_background(self, bg):
879:         self._background = bg
880:         bg.set_kernel(self)
881: 
882: 
883: # ── Entry Point ───────────────────────────────────────────────────────────────
884: async def main():
885:     logging.basicConfig(
886:         level   = logging.DEBUG if __import__('os').getenv(
887:             "ISAAC_DEBUG", "false").lower() == "true" else logging.INFO,
888:         format  = "[%(asctime)s] %(levelname)-7s %(name)s – %(message)s",
889:         datefmt = "%H:%M:%S",
890:     )
891: 
892:     kernel = IsaacKernel()
893: 
894:     # Worker + Background + Monitor
895:     await kernel.executor.start_worker(concurrency=4)
896: 
897:     from background_loop import get_background
898:     bg = get_background()
899:     kernel.set_background(bg)
900:     await bg.start()
901: 
902:     http = DashboardHTTPServer(port=kernel.cfg.monitor.http_port)
903:     await http.start()
904: 
905:     print("""
906: ╔══════════════════════════════════════════════════════╗
907: ║  ISAAC v5.3 – Unified OS                            ║
908: ╠══════════════════════════════════════════════════════╣
909: ║  Dashboard:   http://localhost:8766                  ║
910: ║  WebSocket:   ws://localhost:8765                    ║
911: ╠══════════════════════════════════════════════════════╣
912: ║  SUDO (Master-Tür):                                  ║
913: ║    sudo PASSWORT   → Vollzugriff öffnen             ║
914: ║    sudo close      → Schließen                       ║
915: ╠══════════════════════════════════════════════════════╣
916: ║  KI-Instanzen:                                       ║
917: ║    url: ID | URL | NAME      → Instanz hinzufügen   ║
918: ║    login: DOM|URL|USER|PASS  → Auto-Login            ║
919: ╠══════════════════════════════════════════════════════╣
920: ║  Befehle:                                            ║
921: ║    suche: QUERY    → 7 Suchmaschinen parallel        ║
922: ║    broadcast: TEXT → Alle Instanzen                  ║
923: ║    meinung: THEMA  → Isaac's eigene Meinung          ║
924: ║    ki status       → KI-Netzwerk Übersicht           ║
925: ║    status          → System-Übersicht                ║
926: ╚══════════════════════════════════════════════════════╝
927: """)
928: 
929:     await kernel.monitor.start()
930: 
931: 
932: if __name__ == "__main__":
933:     asyncio.run(main())

(End of file - total 933 lines)
</content>
```

**Tool: read**

**Input:**
```json
{
  "filePath": "/root/Isaac/executor.py",
  "offset": 680,
  "limit": 320
}
```

**Output:**
```
<path>/root/Isaac/executor.py</path>
<type>file</type>
<content>
680:             f"Multi-KI done: {result.n_instanzen} Instanzen, "
681:             f"{result.dauer:.1f}s"
682:         )
683: 
684:     # ── Code-Ausführung (ASYNC, kein blocking!) ───────────────────────────────
685:     async def _execute_code(self, task: Task):
686:         """Generiert Python-Code und führt ihn eingeschränkt im Isolated-Mode aus."""
687:         ctx = isaac_ctx("Executor", f"Code ausführen: task {task.id}")
688:         self.gate.require("execute_code", ctx)
689: 
690:         code_prompt = (
691:             f"Schreibe Python-Code für:\n{task.prompt}\n\n"
692:             "Antworte NUR mit dem Code ohne Erklärungen oder Markdown."
693:         )
694:         raw_code, prov = await self.relay.ask_with_fallback(code_prompt, task_id=task.id)
695:         task.provider_used = prov
696:         code = _normalize_code(raw_code)
697: 
698:         ok, reason = _validate_generated_code(code)
699:         if not ok:
700:             task.antwort = f"[CODE] Geblockt: {reason}"
701:             task.status = TaskStatus.FAILED
702:             AuditLog.action("Executor", "code_blocked", reason, Level.ISAAC, erfolg=False)
703:             return
704: 
705:         exec_dir = WORKSPACE / ".isaac_exec"
706:         exec_dir.mkdir(parents=True, exist_ok=True)
707:         tmp_path = None
708:         try:
709:             with tempfile.NamedTemporaryFile("w", suffix=".py", dir=exec_dir, delete=False, encoding="utf-8") as tmp:
710:                 tmp.write(code)
711:                 tmp_path = Path(tmp.name)
712: 
713:             kwargs = {}
714:             if os.name != "nt":
715:                 kwargs["preexec_fn"] = _limit_subprocess_resources
716: 
717:             proc = await asyncio.create_subprocess_exec(
718:                 "python3", "-I", "-S", str(tmp_path),
719:                 stdout=asyncio.subprocess.PIPE,
720:                 stderr=asyncio.subprocess.PIPE,
721:                 cwd=str(WORKSPACE),
722:                 env={"PATH": os.environ.get("PATH", ""), "PYTHONIOENCODING": "utf-8"},
723:                 **kwargs,
724:             )
725:             try:
726:                 stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=8.0)
727:             except asyncio.TimeoutError:
728:                 proc.kill()
729:                 await proc.communicate()
730:                 task.antwort = "[CODE] Timeout (8s)"
731:                 task.status = TaskStatus.FAILED
732:                 return
733: 
734:             output = (stdout.decode(errors="replace") or stderr.decode(errors="replace") or "(kein Output)").strip()
735:             task.antwort = f"```python\n{code[:700]}\n```\n\n**Output:**\n```\n{output[:1200]}\n```"
736:             task.status = TaskStatus.DONE if proc.returncode == 0 else TaskStatus.FAILED
737:             if proc.returncode != 0:
738:                 task.fehler = output[:200]
739:             AuditLog.system_cmd("Executor", "python3 -I -S [tempfile]", proc.returncode)
740:         except FileNotFoundError:
741:             task.antwort = "[CODE] python3 nicht gefunden"
742:             task.status = TaskStatus.FAILED
743:         finally:
744:             if tmp_path:
745:                 try:
746:                     tmp_path.unlink(missing_ok=True)
747:                 except Exception:
748:                     pass
749: 
750:     # ── File-Task ────────────────────────────────────────────────────────────
751:     async def _execute_file(self, task: Task):
752:         ctx = isaac_ctx("Executor", f"Datei-Op: task {task.id}")
753:         prompt_lower = task.prompt.lower()
754:         full_access = bool(get_config().filesystem_full_access)
755:         wants_write = "schreibe" in prompt_lower or "write" in prompt_lower
756:         wants_delete = any(token in prompt_lower for token in ("lösche", "loesche", "delete", "entferne"))
757: 
758:         if wants_write:
759:             self.gate.require("file_write", ctx)
760:         elif wants_delete:
761:             self.gate.require("file_delete", ctx)
762:         else:
763:             self.gate.require("file_read", ctx)
764: 
765:         pfad_match = re.search(r"[\"']([^\"']+)[\"']", task.prompt)
766:         if not pfad_match:
767:             task.antwort = "[FILE] Pfad nicht erkannt"
768:             task.status = TaskStatus.FAILED
769:             return
770: 
771:         try:
772:             raw_path = Path(os.path.expanduser(pfad_match.group(1).strip()))
773:             candidate = (raw_path if raw_path.is_absolute() else (WORKSPACE / raw_path)).resolve()
774:             workspace_root = WORKSPACE.resolve()
775:             if not full_access and not candidate.is_relative_to(workspace_root):
776:                 task.antwort = "[FILE] Zugriff außerhalb des Workspace blockiert"
777:                 task.status = TaskStatus.FAILED
778:                 return
779:         except Exception:
780:             task.antwort = "[FILE] Ungültiger Pfad"
781:             task.status = TaskStatus.FAILED
782:             return
783: 
784:         if wants_write:
785:             content_match = re.search(r'(?:inhalt|content)\s*:\s*(.+)$', task.prompt, re.IGNORECASE | re.S)
786:             if not content_match:
787:                 task.antwort = "[FILE] Kein Schreibinhalt gefunden. Nutze: inhalt: ..."
788:                 task.status = TaskStatus.FAILED
789:                 return
790:             candidate.parent.mkdir(parents=True, exist_ok=True)
791:             candidate.write_text(content_match.group(1).strip(), encoding="utf-8")
792:             task.antwort = f"[FILE] Gespeichert: {candidate if full_access else candidate.relative_to(workspace_root)}"
793:             task.status = TaskStatus.DONE
794:             return
795: 
796:         if candidate.exists() and candidate.is_file():
797:             task.antwort = candidate.read_text(encoding="utf-8", errors="replace")[:4000]
798:             task.status = TaskStatus.DONE
799:             return
800: 
801:         task.antwort = "[FILE] Datei nicht gefunden"
802:         task.status = TaskStatus.FAILED
803: 
804:     # ── Sub-Tasks ─────────────────────────────────────────────────────────────
805:     async def _execute_sub_tasks(self, parent: Task,
806:                                   sub_prompts: list[str],
807:                                   provider: Optional[str]) -> list[str]:
808:         tasks = []
809:         for prompt in sub_prompts:
810:             sub = self.create_task(
811:                 typ          = parent.typ,
812:                 prompt       = prompt,
813:                 beschreibung = f"[Sub] {prompt[:60]}",
814:                 prioritaet   = parent.prioritaet + 1,
815:                 provider     = provider,
816:                 parent_id    = parent.id,
817:                 system_prompt = parent.system_prompt,
818:                 sudo_aktiv   = parent.sudo_aktiv,
819:                 strategy     = parent.strategy,
820:                 interaction_class = parent.interaction_class,
821:                 classification = parent.classification,
822:                 retrieved_context = parent.retrieved_context,
823:             )
824:             parent.sub_task_ids.append(sub.id)
825:             tasks.append(sub)
826:         await asyncio.gather(*[self._execute(t) for t in tasks])
827:         return [t.antwort for t in tasks if t.antwort]
828: 
829:     def _aggregate(self, results: list[str]) -> str:
830:         if not results:
831:             return "[Keine Ergebnisse]"
832:         if len(results) == 1:
833:             return results[0]
834:         return "\n\n---\n\n".join(
835:             f"**Teil {i+1}:**\n{r}" for i, r in enumerate(results)
836:         )
837: 
838:     # ── System-Prompt ─────────────────────────────────────────────────────────
839:     def _build_system(self, task: Task) -> str:
840:         if task.system_prompt:
841:             return task.system_prompt
842:         basis = {
843:             TaskType.CHAT:      "Du bist Isaac. Antworte vollständig, präzise und strukturiert.",
844:             TaskType.SEARCH:    "Du bist ein Recherche-Synthesizer. Fasse Suchergebnisse vollständig zusammen.",
845:             TaskType.ANALYSIS:  "Du bist ein Analyse-Experte. Untersuche systematisch.",
846:             TaskType.TRANSLATE: "Du bist ein Experte für Sprachen und Schriften. Antworte präzise.",
847:             TaskType.CODE:      "Du bist ein Programmierer. Schreibe sauberen, lauffähigen Code.",
848:             TaskType.PLAN:      "Du bist ein strategischer Planer. Erstelle detaillierte Pläne.",
849:         }
850:         return basis.get(task.typ, "Du bist Isaac, ein autonomes KI-System.")
851: 
852:     # ── Persistenz ────────────────────────────────────────────────────────────
853:     def _persist_task(self, task: Task):
854:         """Speichert abgeschlossene Tasks in SQLite."""
855:         if task.status not in (TaskStatus.DONE, TaskStatus.FAILED):
856:             return
857:         try:
858:             from memory import get_memory
859:             get_memory().save_task_result(
860:                 task_id     = task.id,
861:                 description = task.beschreibung[:200],
862:                 result      = task.antwort,
863:                 score       = task.score.total if task.score else 0.0,
864:                 iterations  = task.iteration + 1,
865:                 provider    = task.provider_used,
866:             )
867:         except Exception as e:
868:             log.warning(f"Task-Persistenz: {e}")
869: 
870:     def _load_persisted_tasks(self):
871:         """Lädt die letzten abgeschlossenen Tasks als Dashboard-Historie."""
872:         try:
873:             from memory import _conn
874:             with _conn() as con:
875:                 rows = con.execute(
876:                     "SELECT task_id, description, result, score, iterations, provider, ts FROM task_results ORDER BY id DESC LIMIT 50"
877:                 ).fetchall()
878:             for row in reversed(rows):
879:                 task = Task(
880:                     id=row["task_id"],
881:                     typ=TaskType.CHAT,
882:                     prompt=row["description"],
883:                     beschreibung=row["description"],
884:                 )
885:                 task.status = TaskStatus.DONE
886:                 task.antwort = row["result"] or ""
887:                 task.provider_used = row["provider"] or ""
888:                 task.iteration = max(0, int((row["iterations"] or 1) - 1))
889:                 task.abgeschlossen = row["ts"] or ""
890:                 self._tasks.setdefault(task.id, task)
891:         except Exception as e:
892:             log.debug(f"Task-Historie konnte nicht geladen werden: {e}")
893: 
894:     # ── Callbacks ─────────────────────────────────────────────────────────────
895:     def register_callback(self, fn: Callable):
896:         self._callbacks.append(fn)
897: 
898:     def unregister_callback(self, fn: Callable):
899:         self._callbacks = [c for c in self._callbacks if c != fn]
900: 
901:     def _notify(self, task: Task):
902:         data = task.to_dict()
903:         try:
904:             loop = self._loop or asyncio.get_running_loop()
905:         except RuntimeError:
906:             loop = None
907:         for cb in self._callbacks:
908:             try:
909:                 if loop and loop.is_running():
910:                     loop.call_soon_threadsafe(asyncio.create_task, self._safe_cb(cb, data))
911:                 else:
912:                     result = cb(data)
913:                     if asyncio.iscoroutine(result):
914:                         asyncio.run(result)
915:             except Exception as e:
916:                 log.debug(f"Callback-Fehler: {e}")
917: 
918:     async def _safe_cb(self, cb: Callable, data: dict):
919:         try:
920:             result = cb(data)
921:             if asyncio.iscoroutine(result):
922:                 await result
923:         except (RuntimeError, ValueError) as e:
924:             log.debug(f"Callback async Fehler: {e}")
925: 
926:     # ── Abfragen ─────────────────────────────────────────────────────────────
927:     def get_task(self, task_id: str) -> Optional[Task]:
928:         return self._tasks.get(task_id)
929: 
930:     def all_tasks(self, limit: int = 200) -> list[dict]:
931:         return [
932:             t.to_dict()
933:             for t in sorted(self._tasks.values(),
934:                             key=lambda t: t.erstellt, reverse=True)[:limit]
935:         ]
936: 
937:     def running_tasks(self) -> list[dict]:
938:         return [
939:             t.to_dict() for t in self._tasks.values()
940:             if t.status in (TaskStatus.RUNNING, TaskStatus.EVALUATING,
941:                             TaskStatus.FOLLOWUP)
942:         ]
943: 
944:     def queue_size(self) -> int:
945:         return self._queue.qsize()
946: 
947:     def stats(self) -> dict:
948:         alle = list(self._tasks.values())
949:         by_status: dict[str, int] = {}
950:         for t in alle:
951:             k = t.status.value
952:             by_status[k] = by_status.get(k, 0) + 1
953:         scored = [t.score.total for t in alle if t.score]
954:         return {
955:             "total":     len(alle),
956:             "running":   len(self._running),
957:             "queue":     self.queue_size(),
958:             "by_status": by_status,
959:             "avg_score": round(sum(scored)/len(scored), 2) if scored else 0.0,
960:         }
961: 
962: 
963: _executor: Optional[Executor] = None
964: 
965: def get_executor() -> Executor:
966:     global _executor
967:     if _executor is None:
968:         _executor = Executor()
969:     return _executor

(End of file - total 969 lines)
</content>
```

---

## Assistant (Plan · GPT-5.3 Codex · 3.5s)

_Thinking:_



**Tool: read**

**Input:**
```json
{
  "filePath": "/root/Isaac/tests_phase_a_stabilization.py",
  "offset": 1,
  "limit": 340
}
```

**Output:**
```
<path>/root/Isaac/tests_phase_a_stabilization.py</path>
<type>file</type>
<content>
1: import asyncio
2: import unittest
3: from types import SimpleNamespace
4: 
5: from executor import Executor, Strategy, Task, TaskType
6: from isaac_core import IsaacKernel, Intent, detect_intent
7: from low_complexity import (
8:     ClassificationResult,
9:     InteractionClass,
10:     classify_interaction_result,
11:     is_lightweight_local_class,
12: )
13: 
14: 
15: class TestCriticalBugs(unittest.TestCase):
16:     def setUp(self):
17:         self.kernel = object.__new__(IsaacKernel)
18: 
19:     def test_bug_1_greeting_stays_lightweight_local(self):
20:         result = classify_interaction_result("Hallo Isaac")
21:         self.assertEqual(result.interaction_class, InteractionClass.SOCIAL_GREETING)
22:         self.assertTrue(is_lightweight_local_class(result.interaction_class))
23: 
24:     def test_bug_2_status_query_maps_to_status_intent(self):
25:         intent = self.kernel._resolve_intent_from_classification(
26:             "status", Intent.CHAT, InteractionClass.STATUS_QUERY
27:         )
28:         self.assertEqual(intent, Intent.STATUS)
29: 
30:     def test_bug_3_tool_request_maps_to_search_intent(self):
31:         intent = self.kernel._resolve_intent_from_classification(
32:             "Suche: Wetter Berlin", Intent.SEARCH, InteractionClass.TOOL_REQUEST
33:         )
34:         self.assertEqual(intent, Intent.SEARCH)
35: 
36:     def test_bug_4_question_without_status_or_tool_stays_chat(self):
37:         intent = self.kernel._resolve_intent_from_classification(
38:             "Was ist 2+2?", Intent.CHAT, InteractionClass.NORMAL_CHAT
39:         )
40:         self.assertEqual(intent, Intent.CHAT)
41: 
42:     def test_bug_5_detected_search_is_ignored_without_tool_classification(self):
43:         intent = self.kernel._resolve_intent_from_classification(
44:             "Erkläre mir das Wetter als sprachliches Motiv in Literatur",
45:             Intent.SEARCH,
46:             InteractionClass.NORMAL_CHAT,
47:         )
48:         self.assertEqual(intent, Intent.CHAT)
49: 
50:     def test_bug_6_executor_uses_explicit_tool_policy_for_normal_chat(self):
51:         task = Task(
52:             id="t1",
53:             typ=TaskType.CHAT,
54:             prompt="Was ist 2+2?",
55:             beschreibung="chat",
56:             strategy=Strategy(allow_tools=True),
57:             interaction_class=InteractionClass.NORMAL_CHAT,
58:             classification=ClassificationResult(
59:                 interaction_class=InteractionClass.NORMAL_CHAT,
60:                 normalized_text="was ist 2 2",
61:                 has_question=True,
62:                 word_count=3,
63:             ),
64:         )
65:         executor = object.__new__(Executor)
66:         self.assertTrue(executor._should_try_tool(task, task.prompt, iteration=2))
67: 
68:     def test_bug_7_executor_respects_explicit_tool_disable_even_for_tool_request(self):
69:         task = Task(
70:             id="t2",
71:             typ=TaskType.CHAT,
72:             prompt="Suche: Wetter Berlin",
73:             beschreibung="chat",
74:             strategy=Strategy(allow_tools=False),
75:             interaction_class=InteractionClass.TOOL_REQUEST,
76:             classification=ClassificationResult(
77:                 interaction_class=InteractionClass.TOOL_REQUEST,
78:                 normalized_text="suche wetter berlin",
79:                 has_question=False,
80:                 word_count=3,
81:             ),
82:         )
83:         executor = object.__new__(Executor)
84:         self.assertFalse(executor._should_try_tool(task, task.prompt, iteration=0))
85: 
86:     def test_bug_8_kernel_uses_structured_retrieval_contract_without_legacy_build_context(self):
87:         class FakeRetrievalContext:
88:             def as_dict(self):
89:                 return {
90:                     "active_directives": [{"text": "Antworten klar halten", "priority": 20}],
91:                     "relevant_facts": [{"key": "answer_style", "value": "nuechtern"}],
92:                     "semantic_context": "[semantik] routing context",
93:                     "conversation_history": [{"role": "steffen", "text": "Bitte stabil halten"}],
94:                     "relevant_task_results": [{"description": "alt", "result": "tools genutzt", "score": 3.0}],
95:                     "preferences_context": [{"source": "directive", "text": "Antworten klar halten", "priority": 20}],
96:                     "project_context": [{"role": "steffen", "text": "routing fokus"}],
97:                     "behavioral_risks": [{"description": "alt", "score": 3.0, "risks": ["tool_overreach_risk"]}],
98:                     "relevant_reflections": ["pattern"],
99:                     "open_questions": [],
100:                 }
101: 
102:         class FakeMemory:
103:             def __init__(self):
104:                 self.calls = []
105: 
106:             def build_retrieval_context(self, user_input, intent="", interaction_class="", n_history=6):
107:                 self.calls.append((user_input, intent, interaction_class, n_history))
108:                 return FakeRetrievalContext()
109: 
110:             def build_context(self, *args, **kwargs):
111:                 raise AssertionError("legacy build_context should not be used")
112:             
113:             def format_retrieval_context(self, retrieval_ctx):
114:                 return (
115:                     "[active_directives]\n  - prio=20: Antworten klar halten\n"
116:                     "[semantic_context]\n[semantik] routing context"
117:                 )
118: 
119:             def add_conversation(self, *args, **kwargs):
120:                 return None
121: 
122:             def save_task_result(self, *args, **kwargs):
123:                 return None
124: 
125:         class FakeExecutor:
126:             def __init__(self):
127:                 self.prompt = None
128: 
129:             def create_task(self, **kwargs):
130:                 self.prompt = kwargs["prompt"]
131:                 return SimpleNamespace(
132:                     typ=kwargs["typ"],
133:                     prompt=kwargs["prompt"],
134:                     antwort="ok",
135:                     fehler="",
136:                     score=SimpleNamespace(total=7.0),
137:                     provider_used="test-provider",
138:                     iteration=0,
139:                     id="task1",
140:                 )
141: 
142:             async def submit_and_wait(self, task, timeout=180.0):
143:                 return task
144: 
145:         kernel = object.__new__(IsaacKernel)
146:         kernel.memory = FakeMemory()
147:         kernel.executor = FakeExecutor()
148:         kernel.meaning = SimpleNamespace(record_impact=lambda *args, **kwargs: None)
149:         kernel.values = SimpleNamespace(update=lambda *args, **kwargs: None)
150:         kernel._build_system = lambda sudo_aktiv, emp, wissen_kontext="", strategy_note="": "system"
151:         kernel._provider_hint = lambda user_input: None
152:         classification = ClassificationResult(
153:             interaction_class=InteractionClass.NORMAL_CHAT,
154:             normalized_text="was ist 2 2",
155:             has_question=True,
156:             word_count=3,
157:         )
158: 
159:         result, score = asyncio.run(
160:             kernel._standard_task(
161:                 user_input="Was ist 2+2?",
162:                 intent=Intent.CHAT,
163:                 sudo_aktiv=False,
164:                 emp=SimpleNamespace(),
165:                 wissen_kontext="",
166:                 interaction_class=InteractionClass.NORMAL_CHAT,
167:                 classification=classification,
168:             )
169:         )
170: 
171:         self.assertEqual(result, "ok")
172:         self.assertEqual(score, 7.0)
173:         self.assertEqual(kernel.memory.calls[0][0], "Was ist 2+2?")
174:         self.assertIn("[active_directives]", kernel.executor.prompt)
175:         self.assertIn("[semantic_context]", kernel.executor.prompt)
176:         self.assertNotIn("[Steffen-Direktiven]", kernel.executor.prompt)
177: 
178:     def test_bug_9_kernel_detects_natural_openrouter_browser_request(self):
179:         self.assertTrue(
180:             self.kernel._is_browser_request(
181:                 "Isaac geh auf openrouter.com, öffne settings und generiere ein token"
182:             )
183:         )
184: 
185:     def test_bug_10_kernel_parses_structured_browser_flow(self):
186:         parsed = self.kernel._parse_browser_request(
187:             "browser: openrouter | https://openrouter.ai/settings/keys | click Settings; wait 1; extract #token -> token"
188:         )
189:         self.assertEqual(parsed["instance_id"], "openrouter")
190:         self.assertEqual(parsed["url"], "https://openrouter.ai/settings/keys")
191:         self.assertEqual(parsed["actions"][0]["action"], "click")
192:         self.assertEqual(parsed["actions"][1]["action"], "wait")
193:         self.assertEqual(parsed["actions"][2]["action"], "extract_text")
194: 
195: 
196:     def test_bug_11_process_short_circuits_greeting_without_runtime_dependencies(self):
197:         kernel = object.__new__(IsaacKernel)
198:         result = asyncio.run(kernel.process("Hallo Isaac"))
199:         self.assertEqual(result, "Hallo. Ich bin da.")
200: 
201:     def test_bug_12_process_short_circuits_ack_without_runtime_dependencies(self):
202:         kernel = object.__new__(IsaacKernel)
203:         result = asyncio.run(kernel.process("Danke"))
204:         self.assertEqual(result, "Gern. Ich bin da.")
205: 
206:     def test_bug_13_translate_keyword_without_prefix_stays_chat(self):
207:         intent = self.kernel._resolve_intent_from_classification(
208:             "Kannst du das bitte übersetzen?",
209:             detect_intent("Kannst du das bitte übersetzen?"),
210:             InteractionClass.NORMAL_CHAT,
211:         )
212:         self.assertEqual(intent, Intent.CHAT)
213: 
214:     def test_bug_14_explicit_translate_prefix_remains_command(self):
215:         intent = self.kernel._resolve_intent_from_classification(
216:             "Übersetze: Guten Morgen auf Englisch",
217:             detect_intent("Übersetze: Guten Morgen auf Englisch"),
218:             InteractionClass.NORMAL_CHAT,
219:         )
220:         self.assertEqual(intent, Intent.TRANSLATE)
221: 
222:     def test_bug_15_strategy_defaults_keep_chat_tooling_disabled(self):
223:         kernel = object.__new__(IsaacKernel)
224:         strategy = kernel._select_response_strategy(
225:             user_input="Was ist 2+2?",
226:             intent=Intent.CHAT,
227:             interaction_class=InteractionClass.NORMAL_CHAT,
228:             retrieval_ctx={},
229:         )
230:         self.assertFalse(strategy.allow_tools)
231:         self.assertTrue(strategy.allow_followup)
232: 
233: 
234:     def test_bug_16_translate_command_without_colon_is_preserved(self):
235:         detected = detect_intent("Übersetze bitte Hallo auf Englisch")
236:         self.assertEqual(detected, Intent.TRANSLATE)
237:         intent = self.kernel._resolve_intent_from_classification(
238:             "Übersetze bitte Hallo auf Englisch",
239:             detected,
240:             InteractionClass.NORMAL_CHAT,
241:         )
242:         self.assertEqual(intent, Intent.TRANSLATE)
243: 
244:     def test_bug_17_executor_blocks_tool_for_status_class_even_if_tools_allowed(self):
245:         task = Task(
246:             id="t3",
247:             typ=TaskType.CHAT,
248:             prompt="status",
249:             beschreibung="chat",
250:             strategy=Strategy(allow_tools=True),
251:             interaction_class=InteractionClass.STATUS_QUERY,
252:         )
253:         executor = object.__new__(Executor)
254:         self.assertFalse(executor._should_try_tool(task, task.prompt, iteration=0))
255: 
256:     def test_bug_18_create_task_prefers_explicit_strategy_over_legacy_flags(self):
257:         executor = object.__new__(Executor)
258:         executor._tasks = {}
259:         executor.next_task_id = lambda: "t-fixed"
260:         strategy = Strategy(allow_tools=False, allow_followup=False, allow_provider_switch=False)
261:         task = executor.create_task(
262:             typ=TaskType.CHAT,
263:             prompt="Was ist 2+2?",
264:             strategy=strategy,
265:             allow_tools=True,
266:             allow_followup=True,
267:             allow_provider_switch=True,
268:         )
269:         self.assertFalse(task.allow_tools)
270:         self.assertFalse(task.allow_followup)
271:         self.assertFalse(task.allow_provider_switch)
272: 
273: if __name__ == '__main__':
274:     unittest.main()

(End of file - total 274 lines)
</content>
```

---

## Assistant (Plan · GPT-5.3 Codex · 3.6s)

_Thinking:_



**Tool: read**

**Input:**
```json
{
  "filePath": "/root/Isaac/low_complexity.py",
  "offset": 1,
  "limit": 280
}
```

**Output:**
```
<path>/root/Isaac/low_complexity.py</path>
<type>file</type>
<content>
1: import re
2: from dataclasses import dataclass
3: 
4: 
5: class InteractionClass:
6:     SOCIAL_GREETING = "SOCIAL_GREETING"
7:     SOCIAL_ACKNOWLEDGMENT = "SOCIAL_ACKNOWLEDGMENT"
8:     SHORT_CLARIFICATION = "SHORT_CLARIFICATION"
9:     STATUS_QUERY = "STATUS_QUERY"
10:     TOOL_REQUEST = "TOOL_REQUEST"
11:     AMBIGUOUS_SHORT = "AMBIGUOUS_SHORT"
12:     NORMAL_CHAT = "NORMAL_CHAT"
13: 
14: 
15: @dataclass(frozen=True)
16: class ClassificationResult:
17:     interaction_class: str
18:     normalized_text: str
19:     has_question: bool
20:     word_count: int
21: 
22:     def as_dict(self) -> dict[str, object]:
23:         return {
24:             "interaction_class": self.interaction_class,
25:             "normalized_text": self.normalized_text,
26:             "has_question": self.has_question,
27:             "word_count": self.word_count,
28:         }
29: 
30: 
31: _GREETING_MARKERS = {
32:     "hallo", "hi", "hey", "servus", "moin", "guten morgen", "guten tag", "guten abend"
33: }
34: _ACK_MARKERS = {
35:     "danke", "dankeschön", "danke schön", "thx", "thanks", "ok danke", "okidoki danke"
36: }
37: _CLARIFY_MARKERS = {
38:     "ist nur eine begrüßung", "war nur ein test", "nur kurz hallo", "ich wollte nur testen ob du antwortest"
39: }
40: _STATUS_MARKERS = {"status", "info", "hilfe"}
41: _TOOL_PREFIXES = ("suche:", "suche ", "search:", "search ", "recherchiere:", "recherchiere ", "finde:")
42: _TOOL_MARKERS = ("internet", "web", "browser", "wetter", "github", "api", "tool", "mcp", "suche", "search")
43: _ACTION_SHORT_MARKERS = ("mach", "weiter", "fortsetzen", "hilfe", "erklär", "erklär", "wer", "was", "wie", "warum")
44: 
45: 
46: def normalize_low_complexity(text: str) -> str:
47:     t = (text or "").strip().lower()
48:     t = re.sub(r"[^\wäöüß\s]", "", t)
49:     t = re.sub(r"\s+", " ", t).strip()
50:     return t
51: 
52: 
53: def classify_interaction(text: str) -> str:
54:     return classify_interaction_result(text).interaction_class
55: 
56: 
57: def classify_interaction_result(text: str) -> ClassificationResult:
58:     normalized = normalize_low_complexity(text)
59:     if not normalized:
60:         return ClassificationResult(
61:             interaction_class=InteractionClass.AMBIGUOUS_SHORT,
62:             normalized_text=normalized,
63:             has_question="?" in (text or ""),
64:             word_count=0,
65:         )
66: 
67:     tokens = normalized.split()
68:     normalized_wo_name = " ".join(t for t in tokens if t != "isaac").strip()
69:     if normalized_wo_name:
70:         normalized = normalized_wo_name
71:         tokens = normalized.split()
72:     word_count = len(tokens)
73:     has_question = "?" in (text or "")
74: 
75:     if normalized in _STATUS_MARKERS:
76:         return ClassificationResult(
77:             interaction_class=InteractionClass.STATUS_QUERY,
78:             normalized_text=normalized,
79:             has_question=has_question,
80:             word_count=word_count,
81:         )
82: 
83:     if normalized.startswith(_TOOL_PREFIXES):
84:         return ClassificationResult(
85:             interaction_class=InteractionClass.TOOL_REQUEST,
86:             normalized_text=normalized,
87:             has_question=has_question,
88:             word_count=word_count,
89:         )
90:     if any(marker in normalized for marker in _TOOL_MARKERS) and word_count >= 2:
91:         if ":" in (text or "") or word_count >= 3:
92:             return ClassificationResult(
93:                 interaction_class=InteractionClass.TOOL_REQUEST,
94:                 normalized_text=normalized,
95:                 has_question=has_question,
96:                 word_count=word_count,
97:             )
98: 
99:     if normalized in _CLARIFY_MARKERS or (
100:         word_count <= 6 and
101:         any(x in normalized for x in ("nur", "test", "begrüßung", "begruessung"))
102:     ):
103:         return ClassificationResult(
104:             interaction_class=InteractionClass.SHORT_CLARIFICATION,
105:             normalized_text=normalized,
106:             has_question=has_question,
107:             word_count=word_count,
108:         )
109: 
110:     if normalized in _ACK_MARKERS:
111:         return ClassificationResult(
112:             interaction_class=InteractionClass.SOCIAL_ACKNOWLEDGMENT,
113:             normalized_text=normalized,
114:             has_question=has_question,
115:             word_count=word_count,
116:         )
117: 
118:     if normalized in _GREETING_MARKERS:
119:         return ClassificationResult(
120:             interaction_class=InteractionClass.SOCIAL_GREETING,
121:             normalized_text=normalized,
122:             has_question=has_question,
123:             word_count=word_count,
124:         )
125:     if word_count <= 3 and any(g in normalized for g in ("hallo", "hi", "hey", "moin")):
126:         return ClassificationResult(
127:             interaction_class=InteractionClass.SOCIAL_GREETING,
128:             normalized_text=normalized,
129:             has_question=has_question,
130:             word_count=word_count,
131:         )
132: 
133:     if word_count <= 2 and not has_question and not any(m in normalized for m in _ACTION_SHORT_MARKERS):
134:         return ClassificationResult(
135:             interaction_class=InteractionClass.AMBIGUOUS_SHORT,
136:             normalized_text=normalized,
137:             has_question=has_question,
138:             word_count=word_count,
139:         )
140: 
141:     return ClassificationResult(
142:         interaction_class=InteractionClass.NORMAL_CHAT,
143:         normalized_text=normalized,
144:         has_question=has_question,
145:         word_count=word_count,
146:     )
147: 
148: 
149: def is_lightweight_local_class(interaction_class: str) -> bool:
150:     return interaction_class in {
151:         InteractionClass.SOCIAL_GREETING,
152:         InteractionClass.SOCIAL_ACKNOWLEDGMENT,
153:         InteractionClass.SHORT_CLARIFICATION,
154:     }
155: 
156: 
157: def is_low_complexity_local_input(text: str) -> bool:
158:     return is_lightweight_local_class(classify_interaction(text))
159: 
160: 
161: def local_class_response(interaction_class: str, text: str = "") -> str:
162:     if interaction_class == InteractionClass.SOCIAL_GREETING:
163:         normalized = normalize_low_complexity(text)
164:         if "guten morgen" in normalized:
165:             return "Guten Morgen. Ich bin da."
166:         return "Hallo. Ich bin da."
167:     if interaction_class == InteractionClass.SOCIAL_ACKNOWLEDGMENT:
168:         return "Gern. Ich bin da."
169:     if interaction_class == InteractionClass.SHORT_CLARIFICATION:
170:         return "Alles gut. Verstanden."
171:     if interaction_class == InteractionClass.AMBIGUOUS_SHORT:
172:         return "Ich bin da."
173:     return "Ich bin da."
174: 
175: 
176: def local_fast_response(text: str) -> str:
177:     return local_class_response(classify_interaction(text), text)

(End of file - total 177 lines)
</content>
```

---

## Assistant (Plan · GPT-5.3 Codex · 3.5s)

_Thinking:_



**Tool: read**

**Input:**
```json
{
  "filePath": "/root/Isaac/task_tool_state.py",
  "offset": 1,
  "limit": 360
}
```

**Output:**
```
<path>/root/Isaac/task_tool_state.py</path>
<type>file</type>
<content>
1: from __future__ import annotations
2: 
3: import json
4: import time
5: from dataclasses import asdict, dataclass, field
6: from pathlib import Path
7: from typing import Any
8: 
9: from config import DATA_DIR
10: 
11: STATE_PATH = DATA_DIR / "task_tool_states.json"
12: 
13: 
14: def _ts() -> float:
15:     return time.time()
16: 
17: 
18: @dataclass
19: class ToolCallRecord:
20:     ts: float
21:     source: str
22:     identifier: str
23:     name: str
24:     feature_type: str = "tool"
25:     ok: bool = False
26:     category: str = "general"
27:     kind: str = ""
28:     note: str = ""
29:     status_code: int | None = None
30: 
31: 
32: @dataclass
33: class TaskToolState:
34:     task_id: str
35:     strategy: str = "general"
36:     status: str = "idle"
37:     preferred_categories: list[str] = field(default_factory=list)
38:     preferred_kinds: list[str] = field(default_factory=list)
39:     selected_tool_id: str = ""
40:     selected_tool_name: str = ""
41:     selected_source: str = ""
42:     used_tool_ids: list[str] = field(default_factory=list)
43:     tool_history: list[ToolCallRecord] = field(default_factory=list)
44:     next_inputs: list[str] = field(default_factory=list)
45:     last_tool_output: str = ""
46:     last_tool_summary: str = ""
47:     resume_count: int = 0
48:     created_at: float = field(default_factory=_ts)
49:     updated_at: float = field(default_factory=_ts)
50: 
51:     def to_dict(self) -> dict[str, Any]:
52:         data = asdict(self)
53:         data["tool_history"] = [asdict(x) for x in self.tool_history[-12:]]
54:         data["next_inputs"] = self.next_inputs[-6:]
55:         return data
56: 
57: 
58: class TaskToolStateStore:
59:     def __init__(self, path: Path = STATE_PATH):
60:         self.path = path
61:         self._items: dict[str, TaskToolState] = {}
62:         self._load()
63: 
64:     def _load(self):
65:         if not self.path.exists():
66:             self._save()
67:             return
68:         try:
69:             raw = json.loads(self.path.read_text(encoding="utf-8"))
70:             items: dict[str, TaskToolState] = {}
71:             for row in raw:
72:                 hist = [ToolCallRecord(**x) for x in row.get("tool_history", [])]
73:                 row = dict(row)
74:                 row["tool_history"] = hist
75:                 items[row["task_id"]] = TaskToolState(**row)
76:             self._items = items
77:         except Exception:
78:             self._items = {}
79:             self._save()
80: 
81:     def _save(self):
82:         payload = [item.to_dict() for item in sorted(self._items.values(), key=lambda x: x.updated_at, reverse=True)[:300]]
83:         self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
84: 
85:     def get_or_create(self, task_id: str, prompt: str = "") -> TaskToolState:
86:         item = self._items.get(task_id)
87:         if item is None:
88:             item = TaskToolState(task_id=task_id)
89:             self._items[task_id] = item
90:             self._derive_strategy(item, prompt)
91:             self._save()
92:         elif prompt:
93:             self._derive_strategy(item, prompt)
94:         return item
95: 
96:     def get(self, task_id: str) -> TaskToolState | None:
97:         return self._items.get(task_id)
98: 
99:     def _derive_strategy(self, item: TaskToolState, prompt: str):
100:         p = (prompt or "").lower()
101:         categories: list[str] = []
102:         kinds: list[str] = []
103:         strategy = "general"
104:         if any(k in p for k in ("suche", "search", "recherche", "internet", "web", "browser")):
105:             strategy = "research"
106:             categories.extend(["suche", "general"])
107:             kinds.extend(["search", "browser_chat", "mcp"]) 
108:         if any(k in p for k in ("api", "schnittstelle", "integration", "mcp", "tool")):
109:             strategy = "integration"
110:             categories.extend(["integration", "general"])
111:             kinds.extend(["mcp", "api"])
112:         if any(k in p for k in ("code", "python", "script", "github")):
113:             strategy = "code"
114:             categories.extend(["code", "general"])
115:             kinds.extend(["script", "api", "mcp"])
116:         if any(k in p for k in ("datei", "file", "resource", "quelle")):
117:             categories.extend(["resource", "general"])
118:         if any(k in p for k in ("wetter", "weather")):
119:             strategy = "research"
120:             categories.extend(["wetter", "suche", "general"])
121:             kinds.extend(["search", "api", "mcp"])
122:         if not categories:
123:             categories = ["general"]
124:         if not kinds:
125:             kinds = ["mcp", "api", "search"]
126:         item.strategy = strategy
127:         item.preferred_categories = list(dict.fromkeys(categories))[:5]
128:         item.preferred_kinds = list(dict.fromkeys(kinds))[:5]
129:         item.updated_at = _ts()
130: 
131:     def mark_resume(self, task_id: str):
132:         item = self.get_or_create(task_id)
133:         item.resume_count += 1
134:         item.status = "resumed"
135:         item.updated_at = _ts()
136:         self._save()
137:         return item
138: 
139:     def set_selected(self, task_id: str, source: str, identifier: str, name: str):
140:         item = self.get_or_create(task_id)
141:         item.selected_source = source
142:         item.selected_tool_id = identifier
143:         item.selected_tool_name = name
144:         if identifier and identifier not in item.used_tool_ids:
145:             item.used_tool_ids.append(identifier)
146:             item.used_tool_ids = item.used_tool_ids[-24:]
147:         item.status = "tool_selected"
148:         item.updated_at = _ts()
149:         self._save()
150:         return item
151: 
152:     def record_call(self, task_id: str, *, source: str, identifier: str, name: str,
153:                     feature_type: str = "tool", ok: bool = False, category: str = "general",
154:                     kind: str = "", note: str = "", status_code: int | None = None,
155:                     output: str = ""):
156:         item = self.get_or_create(task_id)
157:         item.tool_history.append(ToolCallRecord(
158:             ts=_ts(), source=source, identifier=identifier, name=name,
159:             feature_type=feature_type, ok=ok, category=category, kind=kind,
160:             note=note[:240], status_code=status_code,
161:         ))
162:         item.tool_history = item.tool_history[-40:]
163:         item.last_tool_output = (output or "")[:3000]
164:         item.last_tool_summary = self._summarize_output(output)
165:         item.status = "tool_ok" if ok else "tool_failed"
166:         item.updated_at = _ts()
167:         self._save()
168:         return item
169: 
170:     def add_next_input(self, task_id: str, text: str):
171:         text = (text or "").strip()
172:         if not text:
173:             return self.get_or_create(task_id)
174:         item = self.get_or_create(task_id)
175:         if text not in item.next_inputs:
176:             item.next_inputs.append(text[:1800])
177:             item.next_inputs = item.next_inputs[-8:]
178:         item.updated_at = _ts()
179:         self._save()
180:         return item
181: 
182:     def pop_next_input(self, task_id: str) -> str:
183:         item = self.get_or_create(task_id)
184:         if not item.next_inputs:
185:             return ""
186:         value = item.next_inputs.pop(0)
187:         item.updated_at = _ts()
188:         self._save()
189:         return value
190: 
191:     def set_status(self, task_id: str, status: str):
192:         item = self.get_or_create(task_id)
193:         item.status = status
194:         item.updated_at = _ts()
195:         self._save()
196:         return item
197: 
198:     def export_for_tasks(self, task_ids: list[str] | None = None) -> dict[str, dict[str, Any]]:
199:         task_ids = task_ids or list(self._items.keys())
200:         out: dict[str, dict[str, Any]] = {}
201:         for task_id in task_ids:
202:             item = self._items.get(task_id)
203:             if item:
204:                 out[task_id] = item.to_dict()
205:         return out
206: 
207:     def generate_next_input(self, task_id: str, base_prompt: str, tool_name: str, tool_output: str) -> str:
208:         summary = self._summarize_output(tool_output)
209:         if not summary:
210:             return ""
211:         next_input = (
212:             f"Arbeite an der ursprünglichen Aufgabe weiter: {base_prompt[:700]}\n\n"
213:             f"Nutze dieses neue Werkzeug-Ergebnis von {tool_name}:\n{summary}\n\n"
214:             "Leite daraus den nächsten konkreten Schritt ab, schließe Lücken und arbeite nur mit den relevanten neuen Informationen weiter."
215:         )
216:         self.add_next_input(task_id, next_input)
217:         return next_input
218: 
219:     def _summarize_output(self, output: str) -> str:
220:         raw = (output or "").strip()
221:         if not raw:
222:             return ""
223:         raw = raw.replace("\r", "")
224:         lines = [line.strip() for line in raw.splitlines() if line.strip()]
225:         if not lines:
226:             return raw[:700]
227:         if len(lines) == 1:
228:             return lines[0][:700]
229:         head = lines[:8]
230:         return "\n".join(head)[:900]
231: 
232: 
233: _store: TaskToolStateStore | None = None
234: 
235: 
236: def get_task_tool_state_store() -> TaskToolStateStore:
237:     global _store
238:     if _store is None:
239:         _store = TaskToolStateStore()
240:     return _store

(End of file - total 240 lines)
</content>
```

---

## Assistant (Plan · GPT-5.3 Codex · 3.5s)

_Thinking:_



**Tool: grep**

**Input:**
```json
{
  "pattern": "build_context\\(",
  "path": "/root/Isaac",
  "include": "*.py"
}
```

**Output:**
```
Found 3 matches
/root/Isaac/tests_phase_a_stabilization.py:
  Line 86:     def test_bug_8_kernel_uses_structured_retrieval_contract_without_legacy_build_context(self):

  Line 110:             def build_context(self, *args, **kwargs):


/root/Isaac/memory.py:
  Line 489:     def build_context(self, query: str = "", n_history: int = 6) -> str:

```

---

## Assistant (Plan · GPT-5.3 Codex · 5.1s)

_Thinking:_



**Tool: grep**

**Input:**
```json
{
  "pattern": "create_task\\([\\s\\S]*allow_tools|allow_followup|allow_provider_switch",
  "path": "/root/Isaac",
  "include": "*.py"
}
```

**Output:**
```
Found 28 matches
/root/Isaac/tests_phase_a_stabilization.py:
  Line 231:         self.assertTrue(strategy.allow_followup)

  Line 260:         strategy = Strategy(allow_tools=False, allow_followup=False, allow_provider_switch=False)

  Line 266:             allow_followup=True,

  Line 267:             allow_provider_switch=True,

  Line 270:         self.assertFalse(task.allow_followup)

  Line 271:         self.assertFalse(task.allow_provider_switch)


/root/Isaac/isaac_core.py:
  Line 796:         allow_followup = interaction_class not in ("SHORT_CLARIFICATION",)

  Line 797:         allow_provider_switch = True

  Line 818:             allow_provider_switch = False

  Line 822:             allow_followup = False

  Line 823:             allow_provider_switch = False

  Line 826:             allow_followup=allow_followup,

  Line 827:             allow_provider_switch=allow_provider_switch,


/root/Isaac/executor.py:
  Line 114:     allow_followup: bool = True

  Line 115:     allow_provider_switch: bool = True

  Line 121:             "allow_followup": self.allow_followup,

  Line 122:             "allow_provider_switch": self.allow_provider_switch,

  Line 202:     def allow_followup(self) -> bool:

  Line 203:         return self.strategy.allow_followup

  Line 206:     def allow_provider_switch(self) -> bool:

  Line 207:         return self.strategy.allow_provider_switch

  Line 263:                     allow_followup: Optional[bool] = None,

  Line 264:                     allow_provider_switch: Optional[bool] = None,

  Line 269:                 allow_followup=True if allow_followup is None else allow_followup,

  Line 270:                 allow_provider_switch=True if allow_provider_switch is None else allow_provider_switch,

  Line 272:         elif any(flag is not None for flag in (allow_tools, allow_followup, allow_provider_switch)):

  Line 559:             if not task.allow_followup:

  Line 580:             if task.allow_provider_switch and (decision.switch_provider or stale_rounds >= 1):

```

---

## Assistant (Plan · GPT-5.3 Codex · 3.9s)

_Thinking:_



**Tool: grep**

**Input:**
```json
{
  "pattern": "allow_tools\\s*=",
  "path": "/root/Isaac",
  "include": "*.py"
}
```

**Output:**
```
Found 10 matches
/root/Isaac/tests_phase_a_stabilization.py:
  Line 56:             strategy=Strategy(allow_tools=True),

  Line 74:             strategy=Strategy(allow_tools=False),

  Line 250:             strategy=Strategy(allow_tools=True),

  Line 260:         strategy = Strategy(allow_tools=False, allow_followup=False, allow_provider_switch=False)

  Line 265:             allow_tools=True,


/root/Isaac/isaac_core.py:
  Line 795:         allow_tools = intent == Intent.SEARCH

  Line 810:             allow_tools = False

  Line 812:             allow_tools = False

  Line 825:             allow_tools=allow_tools,


/root/Isaac/executor.py:
  Line 268:                 allow_tools=True if allow_tools is None else allow_tools,

```

---

## Assistant (Plan · GPT-5.3 Codex · 6.3s)

_Thinking:_



**Tool: grep**

**Input:**
```json
{
  "pattern": "create_task\\(",
  "path": "/root/Isaac",
  "include": "*.py"
}
```

**Output:**
```
Found 13 matches
/root/Isaac/watchdog.py:
  Line 211:         self._task    = asyncio.create_task(self._loop())


/root/Isaac/tests_phase_a_stabilization.py:
  Line 129:             def create_task(self, **kwargs):

  Line 261:         task = executor.create_task(


/root/Isaac/monitor_server.py:
  Line 97:         self._push = asyncio.create_task(self._metric_pusher())

  Line 200:             asyncio.create_task(self._process_input(ws, text))

  Line 652:                         asyncio.create_task(schedule_process_restart())

  Line 666:                         asyncio.create_task(schedule_process_restart())


/root/Isaac/isaac_core.py:
  Line 352:         task = self.executor.create_task(


/root/Isaac/executor.py:
  Line 253:     def create_task(self, typ: TaskType, prompt: str,

  Line 334:                         asyncio.create_task(self._with_sem(task, sem))

  Line 340:         asyncio.create_task(_run())

  Line 810:             sub = self.create_task(


/root/Isaac/background_loop.py:
  Line 95:         self._task    = asyncio.create_task(self._loop())

```

---

## Assistant (Plan · GPT-5.3 Codex · 39.6s)

_Thinking:_



**Tool: grep**

**Input:**
```json
{
  "pattern": "retrieved_context",
  "path": "/root/Isaac",
  "include": "*.py"
}
```

**Output:**
```
Found 5 matches
/root/Isaac/isaac_core.py:
  Line 363:             retrieved_context = retrieval_ctx,


/root/Isaac/executor.py:
  Line 158:     retrieved_context: dict   = field(default_factory=dict)

  Line 265:                     retrieved_context: Optional[dict] = None) -> Task:

  Line 287:             retrieved_context = retrieved_context or {},

  Line 822:                 retrieved_context = parent.retrieved_context,

```

---

## Assistant (Plan · GPT-5.3 Codex · 40.3s)

_Thinking:_



**Tool: grep**

**Input:**
```json
{
  "pattern": "active_directives|directives_as_context|retrieved_context",
  "path": "/root/Isaac",
  "include": "{isaac_core.py,memory.py,executor.py,tool_runtime.py}"
}
```

**Output:**
```
Found 15 matches
/root/Isaac/memory.py:
  Line 33:     active_directives: list[dict]

  Line 47:             "active_directives": self.active_directives,

  Line 338:         active_directives = []

  Line 344:             active_directives.append({

  Line 419:             active_directives=active_directives,

  Line 438:         if data.get("active_directives"):

  Line 439:             sections.append("[active_directives]")

  Line 440:             for directive in data["active_directives"]:


/root/Isaac/isaac_core.py:
  Line 363:             retrieved_context = retrieval_ctx,

  Line 689:             f"Direktiven:  {len(self.gate.active_directives())} aktiv",

  Line 852:         direktiven = self.gate.directives_as_context()


/root/Isaac/executor.py:
  Line 158:     retrieved_context: dict   = field(default_factory=dict)

  Line 265:                     retrieved_context: Optional[dict] = None) -> Task:

  Line 287:             retrieved_context = retrieved_context or {},

  Line 822:                 retrieved_context = parent.retrieved_context,

```

---

## Assistant (Plan · GPT-5.3 Codex · 36.0s)

_Thinking:_



I inspected the repository code paths and traced how these four modules interact in runtime. Below are implementation-grounded findings only.

**Prioritized Issues**
- P1: Tool-routing contract is internally inconsistent: `TOOL_REQUEST` is routed to `SEARCH`, but tool runtime is only reachable from AI chat loop; this makes `_should_try_tool` mostly unreachable in real flow (`isaac_core.py:750`, `executor.py:414`, `executor.py:615`).
- P1: Search execution uses retrieval-decorated prompt as the web query, so retrieval/context blocks leak directly into search terms and synthesis prompts (`isaac_core.py:350`, `executor.py:620`, `executor.py:630`).
- P1: MCP registry tool execution ignores selected MCP tool identity and calls the first discovered bridge tool, which is nondeterministic/wrong-tool risk (`tool_runtime.py:125`, `tool_runtime.py:128`, `tool_runtime.py:129`).
- P2: Persisted task history loader queries non-existent DB column `task_id`; startup history restoration is effectively broken (`executor.py:876` vs schema `memory.py:95`).
- P2: Task result persistence is duplicated (executor persist + kernel persist) with same primary key, causing redundant writes and potential overwrite drift in `description`/metadata (`executor.py:859`, `isaac_core.py:389`, schema key `memory.py:96`).

**File-by-file Findings**

- `isaac_core.py`
  - `_select_response_strategy` sets `allow_tools=True` only for `Intent.SEARCH` (`isaac_core.py:795`), but executor tool attempts are gated to `TaskType.CHAT` only (`executor.py:414`), so this strategy signal does not activate tool runtime in the actual search path.
  - `TOOL_REQUEST` classification is hard-mapped to `Intent.SEARCH` (`isaac_core.py:750`), which then executes `_execute_search` and bypasses `_maybe_use_tool` entirely (`executor.py:615`).
  - Retrieval context is prepended into `task.prompt` for all standard task types (`isaac_core.py:348`, `isaac_core.py:350`), contaminating downstream executors that assume prompt is task payload (most visible in search query path).
  - Directive context is injected twice through separate channels: structured retrieval `[active_directives]` in prompt and system-level `directives_as_context` (`memory.py:438`, `isaac_core.py:852`), creating duplicate instruction surface with drift risk.

- `executor.py`
  - `_should_try_tool` boundaries:
    - Hard denies if `not allow_tools` (`executor.py:412`) and non-CHAT (`executor.py:414`).
    - Denies lightweight/status classes (`executor.py:418`), but allows all other chat classes if `allow_tools` is true.
    - Parameters `prompt` and `iteration` are unused in the decision (`executor.py:411` signature vs body), so boundary cannot adapt per round/prompt content.
    - If classification is missing/empty, it defaults permissive (returns `True`) whenever chat + `allow_tools` (`executor.py:416`, `executor.py:421`).
  - Strategy vs legacy flags conflict:
    - `create_task` still accepts legacy `allow_*` flags while also accepting a `Strategy` object (`executor.py:253`, `executor.py:262`).
    - If both are provided, legacy flags are ignored with warning (`executor.py:272`), which is a real dual-contract API and source of call-site ambiguity.
  - Unstable path: task history restore SQL mismatch:
    - Query uses `task_id` column from `task_results` (`executor.py:876`), but schema defines `id` (`memory.py:96`), so load path fails and is silently swallowed (`executor.py:891`).
  - Duplicate persistence with kernel:
    - `_persist_task` writes task result (`executor.py:859`) and kernel writes same task again after `submit_and_wait` (`isaac_core.py:389`).

- `memory.py`
  - Duplicate retrieval/context channels exist in implementation:
    - Full structured retrieval builder (`memory.py:323`) + formatter (`memory.py:431`) + legacy `build_context` wrapper (`memory.py:489`) still present.
    - Legacy wrapper is unused in runtime flow (only referenced in tests), so there are two context APIs with one effectively dead.
  - Behavioral risk tagging is coarse and can over-trigger:
    - Any result containing `"tool"` tags `tool_overreach_risk` (`memory.py:400`), which then affects strategy decisions in kernel (`isaac_core.py:811`, `isaac_core.py:818`), potentially suppressing provider switching on weak signal.
  - Retrieval context is also duplicated into task object but not consumed later:
    - Stored in `Task.retrieved_context` (`executor.py:158`, set at `isaac_core.py:363`) but not used in execution logic; only propagated to subtasks (`executor.py:822`).

- `tool_runtime.py`
  - Boundary bypass relative to registry governance:
    - `select_live_tool_for_task` always appends discovered MCP bridge tools as candidates regardless of registry activation/trust toggles (`tool_runtime.py:274`, `tool_runtime.py:285`).
  - Wrong-tool execution defect for registry MCP tools:
    - For `tool.kind == "mcp"`, runtime discovers bridge tools and invokes `tools[0]` (`tool_runtime.py:125`, `tool_runtime.py:128`, `tool_runtime.py:129`) instead of binding to selected tool identity.
  - No explicit privilege gate checks inside runtime dispatch:
    - API/script/MCP execution proceeds directly (`tool_runtime.py:122`, `tool_runtime.py:168`, `tool_runtime.py:303`) and relies entirely on upstream caller policy; if `_should_try_tool` gate is opened, this path has broad effect.

**Duplicate retrieval/context logic (explicit)**
- Structured retrieval appears both as:
  - Prompt prefix (`isaac_core.py:350` using `memory.format_retrieval_context` from `isaac_core.py:831`), and
  - Unused task field copy (`isaac_core.py:363` into `executor.py:158`).
- Directives are duplicated in:
  - Retrieval block `[active_directives]` (`memory.py:438`) and
  - System prompt directives context (`isaac_core.py:852`).

**Unstable execution paths (explicit)**
- Search query polluted by retrieval markup (`isaac_core.py:350` -> `executor.py:620`).
- MCP registry path may invoke wrong remote tool (`tool_runtime.py:128`).
- Persisted-task restore path is broken by schema mismatch (`executor.py:876` vs `memory.py:95`).

If you want, I can next provide a minimal, file-specific fix plan ordered by risk (no redesign, just targeted patches).

---

## User

Fix critical execution inconsistencies in Isaac.

STRICT SCOPE:
Only fix the following two issues. Do NOT refactor unrelated code. Do NOT introduce new architecture.

--------------------------------
TASK 1 — Fix Tool Routing Inconsistency
--------------------------------

Problem:
- TOOL_REQUEST is routed to SEARCH in isaac_core.py
- Executor only allows tool usage for TaskType.CHAT
- Result: _should_try_tool is unreachable in real flows

Required Fix (minimal):
- Ensure that TOOL_REQUEST or SEARCH tasks can actually reach tool execution

Allowed approaches (choose minimal safe one):
EITHER:
- Allow tool execution for SEARCH task type in executor

OR:
- Adjust routing so TOOL_REQUEST maps to a task type that permits tool usage

Constraints:
- Do NOT introduce new task types unless absolutely necessary
- Do NOT change classification system broadly
- Keep existing behavior intact except for fixing this inconsistency

--------------------------------
TASK 2 — Stabilize _should_try_tool
--------------------------------

Problem:
- Decision ignores prompt/iteration context
- Defaults to permissive behavior when classification missing
- Tool boundary is inconsistent

Required Fix:
- Make decision deterministic and conservative

Rules:
- If classification is missing or unclear → return False
- Respect explicit allow_tools flag strictly
- Do NOT infer tool usage from vague context
- Keep logic simple and explicit

--------------------------------
VALIDATION
--------------------------------

- Verify that:
  - Tool execution is reachable from a TOOL_REQUEST flow
  - _should_try_tool no longer defaults to True on missing classification
  - No other behavior is changed

--------------------------------
OUTPUT
--------------------------------

- Show exact code changes
- Show affected files and functions
- Explain why each change is safe 

---

## Assistant (Plan · GPT-5.3 Codex · 46.3s)

_Thinking:_



Understood. I’m in read-only plan mode, so I cannot apply edits yet, but here is the minimal patch plan scoped strictly to your two tasks.

**Planned Changes (Only 2 files, 2 functions + 1 call site)**

- `executor.py` → `Executor._should_try_tool(...)`
- `executor.py` → `Executor._execute_search(...)`

---

**1) Task 1 — Make tool execution reachable from TOOL_REQUEST flow**

Current inconsistency:
- `isaac_core.py` maps `TOOL_REQUEST -> Intent.SEARCH` (`isaac_core.py:750`)
- Tool runtime is only invoked from `_execute_ai(...)` via `_maybe_use_tool(...)`
- SEARCH path (`_execute_search`) never calls `_maybe_use_tool(...)`

Minimal safe fix:
- Keep routing as-is (no intent/classifier redesign)
- Add a single `_maybe_use_tool(...)` call inside `_execute_search(...)` so SEARCH tasks can reach tool execution

Proposed code change (exact snippet style):

```python
# executor.py in _execute_search(self, task: Task)

task.log("Websuche gestartet")

used_tool_ids: set[str] = set()
tool_context, _ = await self._maybe_use_tool(task, task.prompt, iteration=0, used_tool_ids=used_tool_ids)

search = self._get_search()
result = await search.search(
    task.prompt,
    max_hits=10,
    load_fulltext=True,
)

# ...
synth_prompt = (
    f"Basierend auf diesen Suchergebnissen, beantworte: {task.prompt}\n\n"
    f"Suchergebnisse:\n{kontext}\n\n"
    f"Antworte ausführlich, strukturiert, mit Quellenangaben."
)

if tool_context:
    synth_prompt += f"\n\nZusätzlicher Tool-Kontext:\n{tool_context}"
```

Why safe:
- No routing changes, no new task types
- Existing SEARCH behavior remains intact when tool policy denies tool usage
- Only adds optional tool step when policy explicitly allows it

---

**2) Task 2 — Stabilize `_should_try_tool` to be conservative/deterministic**

Current issue:
- Missing classification can still lead to `True` (permissive default)
- `iteration`/`prompt` unused
- CHAT-only gate conflicts with SEARCH route for tool requests

Required conservative policy:
- Explicit `allow_tools` required
- Classification must exist and be explicit
- No vague inference
- Deterministic boundary

Proposed code change:

```python
# executor.py in _should_try_tool(self, task: Task, prompt: str, iteration: int) -> bool

if not task.allow_tools:
    return False

if task.typ not in (TaskType.CHAT, TaskType.SEARCH):
    return False

if not (prompt or "").strip():
    return False

# Conservative: no classification => no tools
if not task.classification:
    return False

interaction_class = task.current_interaction_class
if interaction_class != "TOOL_REQUEST":
    return False

# Deterministic boundary: only first pass
if iteration != 0:
    return False

return True
```

Why safe:
- Strictly policy-driven, no keyword guessing
- Removes permissive fallback for missing classification
- Uses `iteration` and `prompt` explicitly
- Keeps logic small and auditable

---

**Affected Files / Functions**

- `executor.py`
  - `Executor._should_try_tool` (policy boundary hardening)
  - `Executor._execute_search` (tool path reachability for SEARCH/TOOL_REQUEST)

No changes needed in:
- `isaac_core.py` (keep current `TOOL_REQUEST -> SEARCH` mapping)
- `memory.py`
- `tool_runtime.py`

---

**Validation Checklist (post-apply)**

- TOOL_REQUEST flow now can hit tool runtime:
  - `isaac_core._resolve_intent_from_classification(...) -> Intent.SEARCH`
  - `Executor._execute_search(...) -> _maybe_use_tool(...)` reachable
- `_should_try_tool(...)` returns `False` when classification missing
- Explicit `allow_tools=False` still blocks tools
- Non-`TOOL_REQUEST` classes do not trigger tools
- No broader behavior changes beyond these two boundaries

---

If you want, I can execute this exact patch immediately once plan mode is lifted.

---

## User

Fix tool reachability issue introduced by previous change.

---

## User

Problem:

---

## User

- _should_try_tool now only allows TOOL_REQUEST

---

## User

- but routing maps TOOL_REQUEST → SEARCH

---

## User

- result: tools are no longer reachable

---

## User

Fix:

---

## User

- Update _should_try_tool to allow both TOOL_REQUEST and SEARCH interaction classes

---

## User

Constraints:

---

## User

- Do NOT change routing

---

## User

- Do NOT introduce new task types

---

## User

- Keep logic minimal

---

## User

Validation:

---

## User

- TOOL_REQUEST flow must reach tool execution

---

## Assistant (Build · GPT-5.3 Codex · 4.8s)

---

## User

Fix tool reachability issue introduced by previous change.

Problem:
- _should_try_tool now only allows TOOL_REQUEST
- but routing maps TOOL_REQUEST → SEARCH
- result: tools are no longer reachable

Fix:
- Update _should_try_tool to allow both TOOL_REQUEST and SEARCH interaction classes

Constraints:
- Do NOT change routing
- Do NOT introduce new task types
- Keep logic minimal

Validation:
- TOOL_REQUEST flow must reach tool execution
- SEARCH tasks triggered by TOOL_REQUEST must allow tool usage 

---

## Assistant (Build · GPT-5.3 Codex · 7.9s)

_Thinking:_



**Tool: read**

**Input:**
```json
{
  "filePath": "/root/Isaac/executor.py",
  "offset": 400,
  "limit": 60
}
```

**Output:**
```
<path>/root/Isaac/executor.py</path>
<type>file</type>
<content>
400:             task.log(f"Fehler: {e}")
401:             AuditLog.error("Executor", str(e), f"task={task.id}")
402:         finally:
403:             task.dauer_sek     = round(time.monotonic() - t0, 2)
404:             task.abgeschlossen = time.strftime("%Y-%m-%d %H:%M:%S")
405:             task.progress      = 1.0
406:             self._tool_state.set_status(task.id, task.status.value)
407:             task.tool_strategy = self._tool_state.get_or_create(task.id).to_dict()
408:             self._persist_task(task)
409:             self._notify(task)
410: 
411:     def _should_try_tool(self, task: Task, prompt: str, iteration: int) -> bool:
412:         if not task.allow_tools:
413:             return False
414:         if task.typ != TaskType.CHAT:
415:             return False
416:         interaction_class = task.current_interaction_class
417:         if interaction_class and (
418:             is_lightweight_local_class(interaction_class) or interaction_class == "STATUS_QUERY"
419:         ):
420:             return False
421:         return True
422: 
423:     def _tool_context_block(self, tool_name: str, tool_kind: str, via: str, result: dict) -> str:
424:         content = (result.get('content') or result.get('error') or '').strip()[:2200]
425:         return (
426:             "\n\n[Tool-Kontext]\n"
427:             f"Tool: {tool_name}\n"
428:             f"Typ: {tool_kind} via {via}\n"
429:             f"Ergebnis:\n{content}\n"
430:             "[/Tool-Kontext]"
431:         )
432: 
433:     def _tool_limit(self) -> int:
434:         return 3 if bool(getattr(get_config(), "multi_tool_mode", False)) else 1
435: 
436:     async def _maybe_use_tool(self, task: Task, prompt: str, iteration: int, used_tool_ids: set[str]) -> tuple[str, str]:
437:         if not self._should_try_tool(task, prompt, iteration):
438:             return "", ""
439:         context_blocks: list[str] = []
440:         successful_outputs: list[str] = []
441:         tool_runs = 0
442: 
443:         while tool_runs < self._tool_limit():
444:             selection = await select_live_tool_for_task(task, prompt, iteration)
445:             if not selection or selection.get("identifier") in used_tool_ids:
446:                 break
447:             task.log(f"Tool-Auswahl: {selection.get('name')} [{selection.get('kind')}/{selection.get('category')}]")
448:             self._notify(task)
449:             result = await run_selected_tool(selection, prompt)
450:             identifier = selection.get("identifier", "")
451:             name = selection.get("name", identifier)
452:             kind = selection.get("kind", "")
453:             category = selection.get("category", "general")
454:             via = result.get('via') or selection.get('source') or kind
455:             self._tool_state.record_call(
456:                 task.id, source=selection.get("source", "unknown"), identifier=identifier, name=name,
457:                 feature_type=selection.get("mcp_feature", "tool"), ok=bool(result.get('ok')), category=category,
458:                 kind=kind, note=result.get('error', '') or result.get('via', ''), status_code=result.get('status_code'),
459:                 output=result.get('content', '') or result.get('error', '')

(Showing lines 400-459 of 969. Use offset=460 to continue.)
</content>
```

---

## Assistant (Build · GPT-5.3 Codex · 25.8s)

_Thinking:_



**Tool: read**

**Input:**
```json
{
  "filePath": "/root/Isaac/executor.py",
  "offset": 608,
  "limit": 48
}
```

**Output:**
```
<path>/root/Isaac/executor.py</path>
<type>file</type>
<content>
608:             "done" if task.status == TaskStatus.DONE else "failed",
609:             f"score={task.score.total:.1f} iter={task.iteration+1}" if task.score else f"iter={task.iteration+1}",
610:             score=task.score.total if task.score else 0.0,
611:             iteration=task.iteration
612:         )
613: 
614:     # ── Search-Task ───────────────────────────────────────────────────────────
615:     async def _execute_search(self, task: Task):
616:         """Echte Websuche über MultiSearch."""
617:         task.log("Websuche gestartet")
618:         search = self._get_search()
619:         result = await search.search(
620:             task.prompt,
621:             max_hits=10,
622:             load_fulltext=True,
623:         )
624:         task.progress = 0.6
625:         self._notify(task)
626: 
627:         # Suchergebnisse an KI zur Synthese schicken
628:         kontext = result.als_kontext(max_hits=8)
629:         synth_prompt = (
630:             f"Basierend auf diesen Suchergebnissen, beantworte: {task.prompt}\n\n"
631:             f"Suchergebnisse:\n{kontext}\n\n"
632:             f"Antworte ausführlich, strukturiert, mit Quellenangaben."
633:         )
634:         antwort, prov = await self.relay.ask_with_fallback(
635:             synth_prompt,
636:             system="Du bist ein Recherche-Synthesizer. "
637:                    "Fasse Suchergebnisse zu einer vollständigen Antwort zusammen.",
638:             task_id=task.id
639:         )
640:         task.antwort       = antwort
641:         task.provider_used = prov
642:         task.status        = TaskStatus.DONE
643:         task.score         = self.logic.evaluate(antwort, task.prompt, task.id)
644:         task.log(f"Suche: {len(result.hits)} Hits aus {result.quellen}")
645: 
646:     # ── Multi-KI-Task ─────────────────────────────────────────────────────────
647:     async def _execute_multi_ki(self, task: Task):
648:         """Verteilt Task auf mehrere KI-Instanzen."""
649:         dispatcher = self._get_dispatcher()
650:         from browser import get_browser
651:         browser    = get_browser()
652:         instance_ids = browser.get_active_ids()
653: 
654:         if not instance_ids:
655:             # Fallback: API-Provider als "Instanzen"

(Showing lines 608-655 of 969. Use offset=656 to continue.)
</content>
```

---

## Assistant (Build · GPT-5.3 Codex · 23.9s)

_Thinking:_



**Tool: apply_patch**

**Input:**
```json
{
  "patchText": "*** Begin Patch\n*** Update File: /root/Isaac/executor.py\n@@\n     def _should_try_tool(self, task: Task, prompt: str, iteration: int) -> bool:\n         if not task.allow_tools:\n             return False\n-        if task.typ != TaskType.CHAT:\n+        if task.typ not in (TaskType.CHAT, TaskType.SEARCH):\n             return False\n-        interaction_class = task.current_interaction_class\n-        if interaction_class and (\n-            is_lightweight_local_class(interaction_class) or interaction_class == \"STATUS_QUERY\"\n-        ):\n+        if not (prompt or \"\").strip():\n+            return False\n+        interaction_class = (task.current_interaction_class or \"\").strip()\n+        if interaction_class not in (\"TOOL_REQUEST\", \"SEARCH\"):\n             return False\n         return True\n@@\n     async def _execute_search(self, task: Task):\n         \"\"\"Echte Websuche über MultiSearch.\"\"\"\n         task.log(\"Websuche gestartet\")\n+        used_tool_ids: set[str] = set()\n+        tool_context, _ = await self._maybe_use_tool(task, task.prompt, iteration=0, used_tool_ids=used_tool_ids)\n         search = self._get_search()\n         result = await search.search(\n             task.prompt,\n             max_hits=10,\n             load_fulltext=True,\n@@\n         synth_prompt = (\n             f\"Basierend auf diesen Suchergebnissen, beantworte: {task.prompt}\\n\\n\"\n             f\"Suchergebnisse:\\n{kontext}\\n\\n\"\n             f\"Antworte ausführlich, strukturiert, mit Quellenangaben.\"\n         )\n+        if tool_context:\n+            synth_prompt = f\"{synth_prompt}\\n\\nZusätzlicher Tool-Kontext:\\n{tool_context}\"\n         antwort, prov = await self.relay.ask_with_fallback(\n             synth_prompt,\n             system=\"Du bist ein Recherche-Synthesizer. \"\n                    \"Fasse Suchergebnisse zu einer vollständigen Antwort zusammen.\",\n*** End Patch"
}
```

**Output:**
```
Success. Updated the following files:
M executor.py
```

---

## Assistant (Build · GPT-5.3 Codex · 13.2s)

_Thinking:_



**Tool: bash**

**Input:**
```json
{
  "command": "python3 - <<'PY'\nfrom executor import Executor, Task, TaskType, Strategy\nfrom low_complexity import ClassificationResult, InteractionClass\n\nex = object.__new__(Executor)\n\ndef mk(task_type, iclass, allow=True, prompt='Suche Wetter Berlin'):\n    return Task(\n        id='t',\n        typ=task_type,\n        prompt=prompt,\n        beschreibung='x',\n        strategy=Strategy(allow_tools=allow),\n        interaction_class=iclass,\n        classification=ClassificationResult(\n            interaction_class=iclass,\n            normalized_text='suche wetter berlin',\n            has_question=False,\n            word_count=3,\n        ) if iclass else None,\n    )\n\n# TOOL_REQUEST routed to SEARCH task should now permit tools\nsearch_task = mk(TaskType.SEARCH, InteractionClass.TOOL_REQUEST)\nprint('SEARCH+TOOL_REQUEST ->', ex._should_try_tool(search_task, search_task.prompt, 0))\n\n# SEARCH interaction class should also permit tools\nchat_search_class = mk(TaskType.CHAT, 'SEARCH')\nprint('CHAT+SEARCH class ->', ex._should_try_tool(chat_search_class, chat_search_class.prompt, 0))\n\n# Missing classification/class should be blocked (conservative)\nno_class = mk(TaskType.SEARCH, '', prompt='Suche Wetter Berlin')\nno_class.classification = None\nprint('SEARCH+missing class ->', ex._should_try_tool(no_class, no_class.prompt, 0))\nPY",
  "timeout": 120000,
  "workdir": "/root/Isaac",
  "description": "Validate _should_try_tool gating behavior"
}
```

**Output:**
```
Traceback (most recent call last):
  File "<stdin>", line 1, in <module>
  File "/root/Isaac/executor.py", line 33, in <module>
    from relay     import get_relay
  File "/root/Isaac/relay.py", line 17, in <module>
    import aiohttp
ModuleNotFoundError: No module named 'aiohttp'

```

---

## Assistant (Build · GPT-5.3 Codex · 9.1s)

_Thinking:_



**Tool: bash**

**Input:**
```json
{
  "command": "/root/Isaac/.venv/bin/python - <<'PY'\nfrom executor import Executor, Task, TaskType, Strategy\nfrom low_complexity import ClassificationResult, InteractionClass\n\nex = object.__new__(Executor)\n\ndef mk(task_type, iclass, allow=True, prompt='Suche Wetter Berlin'):\n    return Task(\n        id='t',\n        typ=task_type,\n        prompt=prompt,\n        beschreibung='x',\n        strategy=Strategy(allow_tools=allow),\n        interaction_class=iclass,\n        classification=ClassificationResult(\n            interaction_class=iclass,\n            normalized_text='suche wetter berlin',\n            has_question=False,\n            word_count=3,\n        ) if iclass else None,\n    )\n\nsearch_task = mk(TaskType.SEARCH, InteractionClass.TOOL_REQUEST)\nprint('SEARCH+TOOL_REQUEST ->', ex._should_try_tool(search_task, search_task.prompt, 0))\n\nchat_search_class = mk(TaskType.CHAT, 'SEARCH')\nprint('CHAT+SEARCH class ->', ex._should_try_tool(chat_search_class, chat_search_class.prompt, 0))\n\nno_class = mk(TaskType.SEARCH, '', prompt='Suche Wetter Berlin')\nno_class.classification = None\nprint('SEARCH+missing class ->', ex._should_try_tool(no_class, no_class.prompt, 0))\nPY",
  "timeout": 120000,
  "workdir": "/root/Isaac",
  "description": "Validate tool gating with virtualenv"
}
```

**Output:**
```
/usr/bin/bash: line 1: /root/Isaac/.venv/bin/python: No such file or directory

```

---

## Assistant (Build · GPT-5.3 Codex · 5.5s)

_Thinking:_



**Tool: bash**

**Input:**
```json
{
  "command": "python3 -m py_compile executor.py",
  "timeout": 120000,
  "workdir": "/root/Isaac",
  "description": "Compile executor file for syntax validation"
}
```

---

## Assistant (Build · GPT-5.3 Codex · 5.3s)

_Thinking:_



**Tool: read**

**Input:**
```json
{
  "filePath": "/root/Isaac/executor.py",
  "offset": 408,
  "limit": 35
}
```

**Output:**
```
<path>/root/Isaac/executor.py</path>
<type>file</type>
<content>
408:             self._persist_task(task)
409:             self._notify(task)
410: 
411:     def _should_try_tool(self, task: Task, prompt: str, iteration: int) -> bool:
412:         if not task.allow_tools:
413:             return False
414:         if task.typ not in (TaskType.CHAT, TaskType.SEARCH):
415:             return False
416:         if not (prompt or "").strip():
417:             return False
418:         interaction_class = (task.current_interaction_class or "").strip()
419:         if interaction_class not in ("TOOL_REQUEST", "SEARCH"):
420:             return False
421:         return True
422: 
423:     def _tool_context_block(self, tool_name: str, tool_kind: str, via: str, result: dict) -> str:
424:         content = (result.get('content') or result.get('error') or '').strip()[:2200]
425:         return (
426:             "\n\n[Tool-Kontext]\n"
427:             f"Tool: {tool_name}\n"
428:             f"Typ: {tool_kind} via {via}\n"
429:             f"Ergebnis:\n{content}\n"
430:             "[/Tool-Kontext]"
431:         )
432: 
433:     def _tool_limit(self) -> int:
434:         return 3 if bool(getattr(get_config(), "multi_tool_mode", False)) else 1
435: 
436:     async def _maybe_use_tool(self, task: Task, prompt: str, iteration: int, used_tool_ids: set[str]) -> tuple[str, str]:
437:         if not self._should_try_tool(task, prompt, iteration):
438:             return "", ""
439:         context_blocks: list[str] = []
440:         successful_outputs: list[str] = []
441:         tool_runs = 0
442: 

(Showing lines 408-442 of 973. Use offset=443 to continue.)
</content>
```

**Tool: read**

**Input:**
```json
{
  "filePath": "/root/Isaac/executor.py",
  "offset": 612,
  "limit": 42
}
```

**Output:**
```
<path>/root/Isaac/executor.py</path>
<type>file</type>
<content>
612:         )
613: 
614:     # ── Search-Task ───────────────────────────────────────────────────────────
615:     async def _execute_search(self, task: Task):
616:         """Echte Websuche über MultiSearch."""
617:         task.log("Websuche gestartet")
618:         used_tool_ids: set[str] = set()
619:         tool_context, _ = await self._maybe_use_tool(task, task.prompt, iteration=0, used_tool_ids=used_tool_ids)
620:         search = self._get_search()
621:         result = await search.search(
622:             task.prompt,
623:             max_hits=10,
624:             load_fulltext=True,
625:         )
626:         task.progress = 0.6
627:         self._notify(task)
628: 
629:         # Suchergebnisse an KI zur Synthese schicken
630:         kontext = result.als_kontext(max_hits=8)
631:         synth_prompt = (
632:             f"Basierend auf diesen Suchergebnissen, beantworte: {task.prompt}\n\n"
633:             f"Suchergebnisse:\n{kontext}\n\n"
634:             f"Antworte ausführlich, strukturiert, mit Quellenangaben."
635:         )
636:         if tool_context:
637:             synth_prompt = f"{synth_prompt}\n\nZusätzlicher Tool-Kontext:\n{tool_context}"
638:         antwort, prov = await self.relay.ask_with_fallback(
639:             synth_prompt,
640:             system="Du bist ein Recherche-Synthesizer. "
641:                    "Fasse Suchergebnisse zu einer vollständigen Antwort zusammen.",
642:             task_id=task.id
643:         )
644:         task.antwort       = antwort
645:         task.provider_used = prov
646:         task.status        = TaskStatus.DONE
647:         task.score         = self.logic.evaluate(antwort, task.prompt, task.id)
648:         task.log(f"Suche: {len(result.hits)} Hits aus {result.quellen}")
649: 
650:     # ── Multi-KI-Task ─────────────────────────────────────────────────────────
651:     async def _execute_multi_ki(self, task: Task):
652:         """Verteilt Task auf mehrere KI-Instanzen."""
653:         dispatcher = self._get_dispatcher()

(Showing lines 612-653 of 973. Use offset=654 to continue.)
</content>
```

---

## Assistant (Build · GPT-5.3 Codex · 4.5s)

_Thinking:_



**Tool: bash**

**Input:**
```json
{
  "command": "git diff -- executor.py",
  "timeout": 120000,
  "workdir": "/root/Isaac",
  "description": "Show patch for executor changes"
}
```

**Output:**
```
diff --git a/executor.py b/executor.py
index 3418428..a66fc7a 100644
--- a/executor.py
+++ b/executor.py
@@ -411,12 +411,12 @@ class Executor:
     def _should_try_tool(self, task: Task, prompt: str, iteration: int) -> bool:
         if not task.allow_tools:
             return False
-        if task.typ != TaskType.CHAT:
+        if task.typ not in (TaskType.CHAT, TaskType.SEARCH):
             return False
-        interaction_class = task.current_interaction_class
-        if interaction_class and (
-            is_lightweight_local_class(interaction_class) or interaction_class == "STATUS_QUERY"
-        ):
+        if not (prompt or "").strip():
+            return False
+        interaction_class = (task.current_interaction_class or "").strip()
+        if interaction_class not in ("TOOL_REQUEST", "SEARCH"):
             return False
         return True
 
@@ -615,6 +615,8 @@ class Executor:
     async def _execute_search(self, task: Task):
         """Echte Websuche über MultiSearch."""
         task.log("Websuche gestartet")
+        used_tool_ids: set[str] = set()
+        tool_context, _ = await self._maybe_use_tool(task, task.prompt, iteration=0, used_tool_ids=used_tool_ids)
         search = self._get_search()
         result = await search.search(
             task.prompt,
@@ -631,6 +633,8 @@ class Executor:
             f"Suchergebnisse:\n{kontext}\n\n"
             f"Antworte ausführlich, strukturiert, mit Quellenangaben."
         )
+        if tool_context:
+            synth_prompt = f"{synth_prompt}\n\nZusätzlicher Tool-Kontext:\n{tool_context}"
         antwort, prov = await self.relay.ask_with_fallback(
             synth_prompt,
             system="Du bist ein Recherche-Synthesizer. "

```

---

## Assistant (Build · GPT-5.3 Codex · 11.3s)

_Thinking:_



Implemented the reachability fix with minimal scope in `executor.py`, without touching routing or task types.

**What I changed**
- `executor.py:411` in `Executor._should_try_tool`
  - Kept strict `allow_tools` check.
  - Expanded task-type gate from `CHAT` only to `CHAT` or `SEARCH`.
  - Added explicit non-empty prompt guard.
  - Updated interaction-class gate to allow both `"TOOL_REQUEST"` and `"SEARCH"`.

- `executor.py:615` in `Executor._execute_search`
  - Added a call to `_maybe_use_tool(...)` at the start of search execution.
  - Appended returned tool context into the search synthesis prompt when present.

**Why this fixes your issue**
- TOOL requests still route `TOOL_REQUEST -> SEARCH` (unchanged, as requested).
- SEARCH tasks now actually enter tool execution path via `_maybe_use_tool(...)`.
- `_should_try_tool` now explicitly permits both interaction classes you requested, so SEARCH tasks triggered by TOOL requests are no longer blocked.

**Exact patch effect**
- Before: SEARCH tasks never attempted tools and `_should_try_tool` blocked non-CHAT.
- After: SEARCH tasks can attempt tools, and gating accepts `"TOOL_REQUEST"` and `"SEARCH"` classes.

**Validation run**
- Syntax check passed: `python3 -m py_compile executor.py`.
- I could not run runtime-level behavior tests here because this environment is missing project runtime deps (`aiohttp` import path), but code path now directly wires SEARCH flow to tool execution in `executor.py:619`.

If you want, I can add a focused regression test in `tests_phase_a_stabilization.py` for:
1) `_should_try_tool` allowing SEARCH + `TOOL_REQUEST`/`SEARCH`, and  
2) `_execute_search` invoking `_maybe_use_tool` once.

---

## User

Fix _should_try_tool to respect explicit Strategy.allow_tools over classification.

Requirements:
- If allow_tools=True, explicit strategy must remain authoritative
- Remove blocking on missing classification
- Do not make classification stronger than explicit strategy
- Keep other gates as intact as possible
- Minimal change only

Validation:
- python tests_phase_a_stabilization.py must pass
- test_bug_6_executor_uses_explicit_tool_policy_for_normal_chat must pass 

---

## Assistant (Build · GPT-5.3 Codex · 5.2s)

_Thinking:_



**Tool: bash**

**Input:**
```json
{
  "command": "ls",
  "timeout": 120000,
  "workdir": "/root/Isaac",
  "description": "List repository root files"
}
```

**Output:**
```
00_hauptanweisung_und_architekturleitlinie.txt
00b_arbeitsanweisung_kodex_isaac_evo2.txt
01_aktueller_phasenstand_und_arbeitsziel.txt
02_bekannte_probleme_root_causes_und_schutzregeln.txt
03_validierung_und_modulkarte.txt
AGENTS.md
ANALYSIS_REPORT.txt
BUILD_MANIFEST.json
BUILD_REPORT.txt
COMBINED_UPDATE_MANIFEST.json
COMBINED_UPDATE_README.txt
COMPILE_CHECK.txt
DEPLOY_GUIDE_TERMUX_ALPINE.txt
DEPLOY_MANIFEST.json
DEPLOY_RUNTIME_AUDIT.md
DEPLOY_RUNTIME_AUDIT.txt
HEALTHCHECK_REPORT.json
IMPLEMENTATION_NOTES_20260328.txt
IMPLEMENTATION_NOTES_20260328_PHASE5.txt
INSTALL_ORDER.txt
INTEGRATION.txt
ISAAC_V1_ARCHITECTURE_PATCH.md
LATEST_STATE_COMPILE_CHECK.txt
LATEST_STATE_MANIFEST.json
LATEST_STATE_REPORT.txt
LICENSE
MASTER_MANIFEST.json
MASTER_START_HERE.txt
MASTER_VALIDATION.txt
MERGE_MANIFEST.json
MERGE_REPORT.txt
MODULE_MAP.txt
ORCHESTRATOR_OPENROUTER_COMPILE.txt
ORCHESTRATOR_OPENROUTER_MANIFEST.json
ORCHESTRATOR_OPENROUTER_REPORT.txt
PACKAGE_MANIFEST.json
PACKAGE_TEST_REPORT.txt
PHASE1_UNIFIED_MANIFEST.json
PHASE1_UNIFIED_NOTES.txt
PHASE2_IMPLEMENTATION_NOTES.md
PHASE3_IMPLEMENTATION_NOTES.md
PHASE4_IMPLEMENTATION_NOTES.md
PHASE4_VALIDATION_REPORT.txt
QUICKSTART.txt
QUICKSTART_MASTER.txt
QUICKSTART_ULTRA.txt
README.md
README.txt
README_DEPLOY.md
README_EXTENSIONS.txt
README_MASTER.md
README_MASTER_PACKAGE.txt
README_ULTRA_PACKAGE.txt
RELEASE_MANIFEST.json
RELEASE_NOTES_COMPLETE_PACKAGE.txt
ROADMAP_NEXT_STEPS.md
RUNTIME_CLASSIFICATION.txt
START_FOLDER_AUDIT.txt
START_FOLDER_NOTE.txt
ULTRA_MANIFEST.json
__pycache__
app_bridge.py
apply_cumulative_stability_fix.sh
apply_model_override_fix.sh
audit.py
background_loop.py
bootstrap_example.py
browser.py
browser_chat.py
claude_compact_master_implementation_prompt_for_isaac.txt
config.py
constitution.py
dashboard.html
dashboard_api.py
dashboard_home_mobile.html
dashboard_live.html
dashboard_tools.html
dashboard_unified_redesign.html
data
dateiliste.txt
decomposer.py
decomposer_adaptive.py
dispatcher.py
docs
empathie.py
evals
executor.py
healthcheck_isaac.py
install.sh
install_alpine.sh
install_alpine_master.sh
install_isaac_package.sh
install_master.sh
install_or_patch_isaac.sh
install_or_patch_latest_state.sh
install_termux.sh
install_termux_master.sh
installer_dashboard.html
instincts.py
integration_example.py
isaac.out
isaac_architecture_master_brief.txt
isaac_core.py
isaac_core_orchestrator.py
isaac_ctl.sh
isaac_merged_final.py
isaac_programmcode_export_relevant_files.txt
isaac_startup_config.py
isaac_upload_pack_uebersicht.txt
ki_dialog.py
ki_skills.py
launch_dashboard.sh
learning_engine.py
learning_policy.py
logic.py
logs
low_complexity.py
mcp_client.py
mcp_registry.py
mcp_server.py
meaning.py
memory.py
monitor_api.py
monitor_server.py
privilege.py
reflection.py
regelwerk.json
regelwerk.py
relay.py
requirements.txt
run_healthcheck.sh
run_isaac.sh
runtime_readme.txt
sanity_check.py
search.py
secrets_store.py
security_policy.py
self_model.py
start_alpine.sh
start_isaac.sh
start_isaac.sh.before_rewrite
start_master_here.sh
start_termux.sh
stop_isaac.sh
sudo_gate.py
task_tool_state.py
tests_phase_a_stabilization.py
tool_catalog.py
tool_registry.py
tool_runtime.py
tools_patch_README.txt
trust_engine.py
update_master.sh
updater.py
value_decisions.py
values.py
vector_memory.py
watchdog.py
web_urldispatcher.py
workspace

```

---

## Assistant (Build · GPT-5.3 Codex · 19.2s)

_Thinking:_



**Tool: apply_patch**

**Input:**
```json
{
  "patchText": "*** Begin Patch\n*** Update File: /root/Isaac/executor.py\n@@\n     def _should_try_tool(self, task: Task, prompt: str, iteration: int) -> bool:\n         if not task.allow_tools:\n             return False\n         if task.typ not in (TaskType.CHAT, TaskType.SEARCH):\n             return False\n         if not (prompt or \"\").strip():\n             return False\n-        interaction_class = (task.current_interaction_class or \"\").strip()\n-        if interaction_class not in (\"TOOL_REQUEST\", \"SEARCH\"):\n+        interaction_class = task.current_interaction_class\n+        if interaction_class and (\n+            is_lightweight_local_class(interaction_class) or interaction_class == \"STATUS_QUERY\"\n+        ):\n             return False\n         return True\n*** End Patch"
}
```

**Output:**
```
Success. Updated the following files:
M executor.py
```

---

## Assistant (Build · GPT-5.3 Codex · 3.4s)

_Thinking:_



**Tool: bash**

**Input:**
```json
{
  "command": "python3 tests_phase_a_stabilization.py",
  "timeout": 120000,
  "workdir": "/root/Isaac",
  "description": "Run phase A stabilization test suite"
}
```

**Output:**
```
Traceback (most recent call last):
  File "/root/Isaac/tests_phase_a_stabilization.py", line 5, in <module>
    from executor import Executor, Strategy, Task, TaskType
  File "/root/Isaac/executor.py", line 33, in <module>
    from relay     import get_relay
  File "/root/Isaac/relay.py", line 17, in <module>
    import aiohttp
ModuleNotFoundError: No module named 'aiohttp'

```

---

## Assistant (Build · GPT-5.3 Codex · 6.0s)

_Thinking:_



**Tool: bash**

**Input:**
```json
{
  "command": "python3 -m pip install aiohttp",
  "timeout": 120000,
  "workdir": "/root/Isaac",
  "description": "Install aiohttp dependency for test execution"
}
```

**Output:**
```
error: externally-managed-environment

× This environment is externally managed
╰─> To install Python packages system-wide, try apt install
    python3-xyz, where xyz is the package you are trying to
    install.
    
    If you wish to install a non-Kali-packaged Python package,
    create a virtual environment using python3 -m venv path/to/venv.
    Then use path/to/venv/bin/python and path/to/venv/bin/pip. Make
    sure you have pypy3-venv installed.
    
    If you wish to install a non-Kali-packaged Python application,
    it may be easiest to use pipx install xyz, which will manage a
    virtual environment for you. Make sure you have pipx installed.
    
    For more information, refer to the following:
    * https://www.kali.org/docs/general-use/python3-external-packages/
    * /usr/share/doc/python3.13/README.venv

note: If you believe this is a mistake, please contact your Python installation or OS distribution provider. You can override this, at the risk of breaking your Python installation or OS, by passing --break-system-packages.
hint: See PEP 668 for the detailed specification.

```

---

## Assistant (Build · GPT-5.3 Codex · 11.1s)

_Thinking:_



**Tool: bash**

**Input:**
```json
{
  "command": "python3 -m venv .venv && .venv/bin/pip install aiohttp && .venv/bin/python tests_phase_a_stabilization.py",
  "timeout": 120000,
  "workdir": "/root/Isaac",
  "description": "Create venv, install aiohttp, run stabilization tests"
}
```

**Output:**
```
Requirement already satisfied: aiohttp in ./.venv/lib/python3.13/site-packages (3.13.5)
Requirement already satisfied: aiohappyeyeballs>=2.5.0 in ./.venv/lib/python3.13/site-packages (from aiohttp) (2.6.1)
Requirement already satisfied: aiosignal>=1.4.0 in ./.venv/lib/python3.13/site-packages (from aiohttp) (1.4.0)
Requirement already satisfied: attrs>=17.3.0 in ./.venv/lib/python3.13/site-packages (from aiohttp) (26.1.0)
Requirement already satisfied: frozenlist>=1.1.1 in ./.venv/lib/python3.13/site-packages (from aiohttp) (1.8.0)
Requirement already satisfied: multidict<7.0,>=4.5 in ./.venv/lib/python3.13/site-packages (from aiohttp) (6.7.1)
Requirement already satisfied: propcache>=0.2.0 in ./.venv/lib/python3.13/site-packages (from aiohttp) (0.4.1)
Requirement already satisfied: yarl<2.0,>=1.17.0 in ./.venv/lib/python3.13/site-packages (from aiohttp) (1.23.0)
Requirement already satisfied: idna>=2.0 in ./.venv/lib/python3.13/site-packages (from yarl<2.0,>=1.17.0->aiohttp) (3.11)
........create_task: allow_* flags ignoriert, da Strategy explizit gesetzt ist
..........
----------------------------------------------------------------------
Ran 18 tests in 0.014s

OK

```

---

## Assistant (Build · GPT-5.3 Codex · 2.4s)

_Thinking:_



---

