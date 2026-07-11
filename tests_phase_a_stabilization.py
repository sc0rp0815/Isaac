import os

os.environ.setdefault("ISAAC_DISABLE_VECTOR_MEMORY", "1")

import asyncio
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from executor import Executor, Strategy, Task, TaskStatus, TaskType
from decision_trace import DecisionTrace, TracePhase
from logic import QualityScore
from isaac_core import IsaacKernel, Intent, detect_intent
from tool_policy import ToolDecisionReason
from tool_runtime import select_live_tool_for_task
from low_complexity import (
    ClassificationResult,
    InteractionClass,
    classify_interaction_result,
    is_lightweight_local_class,
)
from hermes_compat import (
    BrowserAction,
    ComputerAction,
    ExecutionContext,
    HermesBrowserAdapter,
    HermesCompatibilityAdapter,
    HermesComputerUseAdapter,
    HermesToolSchemaMapper,
    PermissionMetadata,
)
from mcp_registry import MCPRegistry
from security_policy import ConfirmationPolicy


class TestCriticalBugs(unittest.TestCase):
    def setUp(self):
        self.kernel = object.__new__(IsaacKernel)

    def test_bug_1_greeting_stays_lightweight_local(self):
        result = classify_interaction_result("Hallo Isaac")
        self.assertEqual(result.interaction_class, InteractionClass.SOCIAL_GREETING)
        self.assertTrue(is_lightweight_local_class(result.interaction_class))

    def test_bug_2_status_query_maps_to_status_intent(self):
        intent = self.kernel._resolve_intent_from_classification(
            "status", Intent.CHAT, InteractionClass.STATUS_QUERY
        )
        self.assertEqual(intent, Intent.STATUS)

    def test_bug_3_tool_request_maps_to_search_intent(self):
        intent = self.kernel._resolve_intent_from_classification(
            "Suche: Wetter Berlin", Intent.SEARCH, InteractionClass.TOOL_REQUEST
        )
        self.assertEqual(intent, Intent.SEARCH)

    def test_bug_4_question_without_status_or_tool_stays_chat(self):
        intent = self.kernel._resolve_intent_from_classification(
            "Was ist 2+2?", Intent.CHAT, InteractionClass.NORMAL_CHAT
        )
        self.assertEqual(intent, Intent.CHAT)

    def test_bug_5_detected_search_is_ignored_without_tool_classification(self):
        intent = self.kernel._resolve_intent_from_classification(
            "Erkläre mir das Wetter als sprachliches Motiv in Literatur",
            Intent.SEARCH,
            InteractionClass.NORMAL_CHAT,
        )
        self.assertEqual(intent, Intent.CHAT)

    def test_bug_6_executor_uses_explicit_tool_policy_for_normal_chat(self):
        task = Task(
            id="t1",
            typ=TaskType.CHAT,
            prompt="Was ist 2+2?",
            beschreibung="chat",
            strategy=Strategy(allow_tools=True),
            interaction_class=InteractionClass.NORMAL_CHAT,
            classification=ClassificationResult(
                interaction_class=InteractionClass.NORMAL_CHAT,
                normalized_text="was ist 2 2",
                has_question=True,
                word_count=3,
            ),
        )
        executor = object.__new__(Executor)
        self.assertTrue(executor._should_try_tool(task, task.prompt, iteration=2))

    def test_bug_7_executor_respects_explicit_tool_disable_even_for_tool_request(self):
        task = Task(
            id="t2",
            typ=TaskType.CHAT,
            prompt="Suche: Wetter Berlin",
            beschreibung="chat",
            strategy=Strategy(allow_tools=False),
            interaction_class=InteractionClass.TOOL_REQUEST,
            classification=ClassificationResult(
                interaction_class=InteractionClass.TOOL_REQUEST,
                normalized_text="suche wetter berlin",
                has_question=False,
                word_count=3,
            ),
        )
        executor = object.__new__(Executor)
        self.assertFalse(executor._should_try_tool(task, task.prompt, iteration=0))

    def test_bug_8_kernel_uses_structured_retrieval_contract_without_legacy_build_context(self):
        class FakeRetrievalContext:
            def as_dict(self):
                return {
                    "active_directives": [{"text": "Antworten klar halten", "priority": 20}],
                    "relevant_facts": [{"key": "answer_style", "value": "nuechtern"}],
                    "semantic_context": "[semantik] routing context",
                    "conversation_history": [{"role": "steffen", "text": "Bitte stabil halten"}],
                    "relevant_task_results": [{"description": "alt", "result": "tools genutzt", "score": 3.0}],
                    "preferences_context": [{"source": "directive", "text": "Antworten klar halten", "priority": 20}],
                    "project_context": [{"role": "steffen", "text": "routing fokus"}],
                    "behavioral_risks": [{"description": "alt", "score": 3.0, "risks": ["tool_overreach_risk"]}],
                    "relevant_reflections": ["pattern"],
                    "open_questions": [],
                }

        class FakeMemory:
            def __init__(self):
                self.calls = []

            def build_retrieval_context(self, user_input, intent="", interaction_class="", n_history=6):
                self.calls.append((user_input, intent, interaction_class, n_history))
                return FakeRetrievalContext()

            def build_context(self, *args, **kwargs):
                raise AssertionError("legacy build_context should not be used")
            
            def format_retrieval_context(self, retrieval_ctx):
                return (
                    "[active_directives]\n  - prio=20: Antworten klar halten\n"
                    "[semantic_context]\n[semantik] routing context"
                )

            def add_conversation(self, *args, **kwargs):
                return None

            def save_task_result(self, *args, **kwargs):
                return None

        class FakeExecutor:
            def __init__(self):
                self.prompt = None

            def create_task(self, **kwargs):
                self.prompt = kwargs["prompt"]
                return SimpleNamespace(
                    typ=kwargs["typ"],
                    prompt=kwargs["prompt"],
                    antwort="ok",
                    fehler="",
                    score=SimpleNamespace(total=7.0),
                    provider_used="test-provider",
                    iteration=0,
                    id="task1",
                    decision_trace=DecisionTrace(),
                )

            async def submit_and_wait(self, task, timeout=180.0):
                return task

        from neural_core import get_neural_cortex
        from learning_engine import get_learning_engine

        kernel = object.__new__(IsaacKernel)
        kernel.memory = FakeMemory()
        kernel.executor = FakeExecutor()
        kernel.meaning = SimpleNamespace(record_impact=lambda *args, **kwargs: None)
        kernel.values = SimpleNamespace(update=lambda *args, **kwargs: None)
        kernel.neural = get_neural_cortex()
        kernel.learning = get_learning_engine()
        kernel._build_system = lambda sudo_aktiv, emp, wissen_kontext="", strategy_note="": "system"
        kernel._provider_hint = lambda user_input: None
        classification = ClassificationResult(
            interaction_class=InteractionClass.NORMAL_CHAT,
            normalized_text="was ist 2 2",
            has_question=True,
            word_count=3,
        )

        result, score = asyncio.run(
            kernel._standard_task(
                user_input="Was ist 2+2?",
                intent=Intent.CHAT,
                sudo_aktiv=False,
                emp=SimpleNamespace(),
                wissen_kontext="",
                interaction_class=InteractionClass.NORMAL_CHAT,
                classification=classification,
            )
        )

        self.assertEqual(result, "ok")
        self.assertEqual(score, 7.0)
        self.assertEqual(kernel.memory.calls[0][0], "Was ist 2+2?")
        self.assertIn("[active_directives]", kernel.executor.prompt)
        self.assertIn("[semantic_context]", kernel.executor.prompt)
        self.assertNotIn("[Steffen-Direktiven]", kernel.executor.prompt)

    def test_bug_9_kernel_detects_natural_openrouter_browser_request(self):
        self.assertTrue(
            self.kernel._is_browser_request(
                "Isaac geh auf openrouter.com, öffne settings und generiere ein token"
            )
        )

    def test_bug_23_kernel_detects_groq_provider_provision_request(self):
        self.assertTrue(
            self.kernel._is_provider_provision_request("verbinde groq und erstelle api key")
        )
        self.assertTrue(
            self.kernel._is_browser_request("provider: groq api key holen")
        )
        self.assertEqual(
            self.kernel._resolve_provider_provision_target("verbinde groq"),
            "groq",
        )

    def test_bug_24_low_complexity_provider_setup_is_tool_request(self):
        result = classify_interaction_result("bitte groq verbinden")
        self.assertEqual(result.interaction_class, InteractionClass.TOOL_REQUEST)

    def test_bug_26_kernel_detects_provision_all_providers_request(self):
        self.assertTrue(
            self.kernel._wants_provision_all_providers("hole alle api keys und verbinde alle provider")
        )
        self.assertEqual(
            self.kernel._resolve_provider_provision_target("alle provider keys holen"),
            "all",
        )

    def test_bug_27_provision_specs_cover_major_providers(self):
        from browser import provisionable_provider_ids

        ids = set(provisionable_provider_ids())
        self.assertTrue({"groq", "openrouter", "mistral", "together", "huggingface"}.issubset(ids))

    def test_bug_25_browser_providers_needing_provision_detects_missing_groq(self):
        from browser import BrowserManager, PROVIDER_PROVISION_SPECS

        browser = object.__new__(BrowserManager)
        browser.cfg = SimpleNamespace(
            relay=SimpleNamespace(primary_provider="groq"),
            providers={
                "groq": SimpleNamespace(
                    enabled=True,
                    api_key="",
                    provider_type="openai_compat",
                ),
                "ollama": SimpleNamespace(
                    enabled=True,
                    api_key="",
                    provider_type="ollama",
                ),
            },
            free_only_providers=True,
            is_provider_allowed=lambda _pid: False,
        )
        missing = browser.providers_needing_provision()
        self.assertIn("groq", missing)
        self.assertNotIn("ollama", missing)
        self.assertIn("groq", PROVIDER_PROVISION_SPECS)

    def test_bug_10_kernel_parses_structured_browser_flow(self):
        parsed = self.kernel._parse_browser_request(
            "browser: openrouter | https://openrouter.ai/settings/keys | click Settings; wait 1; extract #token -> token"
        )
        self.assertEqual(parsed["instance_id"], "openrouter")
        self.assertEqual(parsed["url"], "https://openrouter.ai/settings/keys")
        self.assertEqual(parsed["actions"][0]["action"], "click")
        self.assertEqual(parsed["actions"][1]["action"], "wait")
        self.assertEqual(parsed["actions"][2]["action"], "extract_text")

    def test_capability_browser_auf_maps_to_browser_intent(self):
        intent = self.kernel._resolve_intent_from_classification(
            "Browser auf GitHub",
            Intent.CHAT,
            InteractionClass.TOOL_REQUEST,
        )
        self.assertEqual(intent, Intent.BROWSER)
        parsed = self.kernel._parse_simple_browser_request("Browser auf GitHub")
        self.assertEqual(parsed["url"], "https://github.com")

    def test_capability_recherche_maps_to_research_intent(self):
        intent = self.kernel._resolve_intent_from_classification(
            "recherche: aktuelle KI Sicherheitsstandards",
            Intent.RESEARCH,
            InteractionClass.TOOL_REQUEST,
        )
        self.assertEqual(intent, Intent.RESEARCH)

    def test_capability_agent_observe_parses_and_routes(self):
        from computer_use import parse_agent_body, parse_agent_flow

        intent = self.kernel._resolve_intent_from_classification(
            "agent: observe",
            Intent.AGENT,
            InteractionClass.TOOL_REQUEST,
        )
        self.assertEqual(intent, Intent.AGENT)
        action = parse_agent_body("observe")
        self.assertEqual(action.action, "observe")
        flow = parse_agent_flow("flow shell pwd; screenshot")
        self.assertEqual(len(flow), 2)
        self.assertEqual(flow[0].action, "shell")
        self.assertEqual(flow[1].action, "screenshot")

    def test_capability_file_access_list_and_read(self):
        from file_access import parse_file_command, execute_file_command
        from unittest.mock import patch
        import tempfile
        from pathlib import Path

        with patch("file_access.access_tier", return_value="full"), tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sample = root / "probe.txt"
            sample.write_text("hello isaac", encoding="utf-8")
            list_cmd = parse_file_command(f"datei: list {root}")
            self.assertIsNotNone(list_cmd)
            self.assertEqual(list_cmd.operation, "list")
            list_out, list_ok = execute_file_command(list_cmd)
            self.assertTrue(list_ok)
            self.assertIn("probe.txt", list_out)

            read_cmd = parse_file_command(f"lese: {sample}")
            self.assertIsNotNone(read_cmd)
            read_out, read_ok = execute_file_command(read_cmd)
            self.assertTrue(read_ok)
            self.assertIn("hello isaac", read_out)


    def test_bug_11_process_short_circuits_greeting_without_runtime_dependencies(self):
        kernel = object.__new__(IsaacKernel)
        result = asyncio.run(kernel.process("Hallo Isaac"))
        self.assertEqual(result, "Hallo. Ich bin da.")

    def test_bug_12_process_short_circuits_ack_without_runtime_dependencies(self):
        kernel = object.__new__(IsaacKernel)
        result = asyncio.run(kernel.process("Danke"))
        self.assertEqual(result, "Gern. Ich bin da.")

    def test_bug_17_regelwerk_does_not_repeat_known_term_questions(self):
        from regelwerk import Regelwerk

        rw = object.__new__(Regelwerk)
        rw._regeln = {}
        rw._fragen = []
        rw._history = []

        first = rw._neue_frage(
            "Was meinst du genau mit 'Status'? Für zukünftige Anfragen wichtig.",
            "Unbekannter Begriff: Status",
            0.5,
        )
        self.assertIsNotNone(first)

        again = rw._neue_frage(
            "Was meinst du genau mit 'Status'? Für zukünftige Anfragen wichtig.",
            "Unbekannter Begriff: Status",
            0.5,
        )
        self.assertIsNone(again)
        self.assertTrue(rw._term_already_asked("Status"))
        self.assertEqual(rw._erkenne_unbekannte_begriffe("Wie ist der System Status?"), "")

    def test_bug_22_regelwerk_ignores_kennst_du_owner_question(self):
        from regelwerk import Regelwerk

        rw = object.__new__(Regelwerk)
        rw._regeln = {}
        rw._fragen = []
        rw._history = []
        self.assertEqual(rw._erkenne_unbekannte_begriffe("Kennst du steffen"), "")
        fragen = rw._generiere_fragen("Kennst du steffen", "Ja, ich kenne dich.", 7.0)
        self.assertEqual(fragen, [])

    def test_bug_18_kernel_resolves_pending_regelwerk_answer(self):
        from regelwerk import Frage

        kernel = object.__new__(IsaacKernel)
        frage = Frage(
            id="F-test",
            text="Was meinst du genau mit 'Status'? Für zukünftige Anfragen wichtig.",
            kontext="test",
            prioritaet=0.5,
        )
        saved_facts = []

        kernel.regelwerk = SimpleNamespace(
            beantworte_frage=lambda fid, text: setattr(frage, "beantwortet", True),
            build_answer_ack=lambda fid, text: f"Verstanden: {text}",
            analysiere=lambda *args, **kwargs: [],
            get_pending_frage=lambda: None,
            get_top_pending_frage=lambda: None,
            get_frage=lambda fid: frage if fid == "F-test" else None,
            _extract_term_from_frage=lambda f: "Status",
        )
        kernel.memory = SimpleNamespace(
            set_fact=lambda key, value, **kwargs: saved_facts.append((key, value)) or True
        )
        kernel._background = None
        kernel._awaiting_frage_id = "F-test"
        kernel.empathie = SimpleNamespace(
            analysiere=lambda text: SimpleNamespace(
                node=SimpleNamespace(zustand="neutral"),
                interface_fehler="",
            )
        )

        result = asyncio.run(
            kernel.process("Status meint bei mir den Systemzustand aller Module.")
        )

        self.assertIn("Verstanden", result)
        self.assertTrue(frage.beantwortet)
        self.assertIsNone(kernel._awaiting_frage_id)
        self.assertEqual(saved_facts, [
            ("definition.status", "Status meint bei mir den Systemzustand aller Module.")
        ])

    def test_bug_20_kernel_constitution_gate_blocks_self_modify_code(self):
        kernel = object.__new__(IsaacKernel)
        msg, gate = kernel._enforce_constitution_gate(
            "code: ändere die constitution.json komplett",
            Intent.CODE,
            sudo_aktiv=False,
        )
        self.assertIsNotNone(msg)
        self.assertIn("[Verfassung]", msg)
        self.assertIn("constitution_not_self_editable", msg)
        self.assertIsNotNone(gate)
        self.assertFalse(gate.get("allowed"))

    def test_bug_21_kernel_constitution_gate_allows_normal_code(self):
        kernel = object.__new__(IsaacKernel)
        msg, gate = kernel._enforce_constitution_gate(
            "code: print('hello')",
            Intent.CODE,
            sudo_aktiv=False,
        )
        self.assertIsNone(msg)
        self.assertIsNotNone(gate)
        self.assertTrue(gate.get("allowed"))

    def test_bug_19_retrieval_surfaces_definition_facts(self):
        import memory as memory_module
        from memory import Memory

        mem = object.__new__(Memory)
        mem._vector = None
        mem.get_directives = lambda: []
        mem.get_working_memory = lambda n: []
        mem.get_relevant_results = lambda query, limit=4: []
        mem.search_procedures = lambda query, limit=3: []
        mem.search_facts = lambda query, limit=8: []
        mem.get_fact_record = lambda key: {
            "key": key,
            "value": "Systemzustand aller Module",
            "confidence": 1.0,
            "source": "Steffen",
        } if key == "definition.status" else None

        ctx = mem.build_retrieval_context(
            "Wie ist der Status der Module?",
            intent="chat",
            interaction_class="NORMAL_CHAT",
        )
        facts = ctx.as_dict().get("relevant_facts", [])
        self.assertTrue(any(f.get("key") == "definition.status" for f in facts))

    def test_bug_16_post_process_accepts_frage_objects_from_background(self):
        from regelwerk import Frage
        from empathie import EmpathieResponse, NodeZustand

        kernel = object.__new__(IsaacKernel)
        kernel.regelwerk = SimpleNamespace(
            analysiere=lambda *args, **kwargs: [],
            get_pending_frage=lambda: None,
        )
        kernel._background = SimpleNamespace(
            get_erkenntnisse=lambda: [
                Frage(
                    id="F1",
                    text="Was meinst du genau mit 'Status'?",
                    kontext="test",
                    prioritaet=0.5,
                )
            ]
        )
        emp = EmpathieResponse(
            node=NodeZustand(),
            ton="standard",
            anpassungs_hinweis="",
            interface_fehler="",
            low_res_aktiv=False,
        )

        result = kernel._post_process(
            "Hallo Isaac. Laufen alle deine module?",
            "Alle Module laufen.",
            emp,
            score=8.0,
            t0=__import__("time").monotonic(),
        )

        self.assertIn("Alle Module laufen.", result)
        self.assertNotIn("[Fehler]", result)

    def test_bug_13_translate_keyword_without_prefix_stays_chat(self):
        intent = self.kernel._resolve_intent_from_classification(
            "Kannst du das bitte übersetzen?",
            detect_intent("Kannst du das bitte übersetzen?"),
            InteractionClass.NORMAL_CHAT,
        )
        self.assertEqual(intent, Intent.CHAT)

    def test_bug_14_explicit_translate_prefix_remains_command(self):
        intent = self.kernel._resolve_intent_from_classification(
            "Übersetze: Guten Morgen auf Englisch",
            detect_intent("Übersetze: Guten Morgen auf Englisch"),
            InteractionClass.NORMAL_CHAT,
        )
        self.assertEqual(intent, Intent.TRANSLATE)

    def test_bug_15_strategy_defaults_keep_chat_tooling_disabled(self):
        kernel = object.__new__(IsaacKernel)
        strategy = kernel._select_response_strategy(
            user_input="Was ist 2+2?",
            intent=Intent.CHAT,
            interaction_class=InteractionClass.NORMAL_CHAT,
            retrieval_ctx={},
        )
        self.assertFalse(strategy.allow_tools)
        self.assertTrue(strategy.allow_followup)


    def test_bug_16_translate_command_without_colon_is_preserved(self):
        detected = detect_intent("Übersetze bitte Hallo auf Englisch")
        self.assertEqual(detected, Intent.TRANSLATE)
        intent = self.kernel._resolve_intent_from_classification(
            "Übersetze bitte Hallo auf Englisch",
            detected,
            InteractionClass.NORMAL_CHAT,
        )
        self.assertEqual(intent, Intent.TRANSLATE)

    def test_bug_30_detect_intent_is_narrowed_to_explicit_command_patterns(self):
        detected = detect_intent("Kannst du den Satz bitte übersetzen?")
        self.assertEqual(detected, Intent.CHAT)

    def test_bug_31_status_classification_has_priority_over_regex_detection(self):
        intent = self.kernel._resolve_intent_from_classification(
            "status",
            detect_intent("status"),
            InteractionClass.STATUS_QUERY,
        )
        self.assertEqual(intent, Intent.STATUS)

    def test_bug_32_tool_classification_has_priority_for_search_routing(self):
        intent = self.kernel._resolve_intent_from_classification(
            "Suche: Wetter Berlin",
            detect_intent("Suche: Wetter Berlin"),
            InteractionClass.TOOL_REQUEST,
        )
        self.assertEqual(intent, Intent.SEARCH)

    def test_bug_33_status_classification_overrides_explicit_command_regex(self):
        intent = self.kernel._resolve_intent_from_classification(
            "übersetze hallo",
            Intent.TRANSLATE,
            InteractionClass.STATUS_QUERY,
        )
        self.assertEqual(intent, Intent.STATUS)

    def test_bug_17_executor_keeps_explicit_tool_policy_for_status_class(self):
        task = Task(
            id="t3",
            typ=TaskType.CHAT,
            prompt="status",
            beschreibung="chat",
            strategy=Strategy(allow_tools=True),
            interaction_class=InteractionClass.STATUS_QUERY,
        )
        executor = object.__new__(Executor)
        self.assertTrue(executor._should_try_tool(task, task.prompt, iteration=0))

    def test_bug_18_create_task_prefers_explicit_strategy_over_legacy_flags(self):
        executor = object.__new__(Executor)
        executor._tasks = {}
        executor.next_task_id = lambda: "t-fixed"
        strategy = Strategy(allow_tools=False, allow_followup=False, allow_provider_switch=False)
        task = executor.create_task(
            typ=TaskType.CHAT,
            prompt="Was ist 2+2?",
            strategy=strategy,
            allow_tools=True,
            allow_followup=True,
            allow_provider_switch=True,
        )
        self.assertFalse(task.allow_tools)
        self.assertFalse(task.allow_followup)
        self.assertFalse(task.allow_provider_switch)

    def test_bug_19_allow_tools_true_lightweight_is_eligible(self):
        task = Task(
            id="t-light",
            typ=TaskType.CHAT,
            prompt="Hallo",
            beschreibung="chat",
            strategy=Strategy(allow_tools=True),
            interaction_class=InteractionClass.SOCIAL_GREETING,
        )
        executor = object.__new__(Executor)
        decision = executor._evaluate_tool_eligibility(task, task.prompt, iteration=0)
        self.assertTrue(decision.eligible)
        self.assertEqual(decision.reason, ToolDecisionReason.ELIGIBLE)

    def test_bug_20_allow_tools_false_blocks_with_reason(self):
        task = Task(
            id="t-block",
            typ=TaskType.CHAT,
            prompt="Suche Wetter Berlin",
            beschreibung="chat",
            strategy=Strategy(allow_tools=False),
            interaction_class=InteractionClass.TOOL_REQUEST,
        )
        executor = object.__new__(Executor)
        decision = executor._evaluate_tool_eligibility(task, task.prompt, iteration=0)
        self.assertFalse(decision.eligible)
        self.assertEqual(decision.reason, ToolDecisionReason.BLOCKED_ALLOW_TOOLS_FALSE)

    def test_bug_21_no_candidate_returns_eligible_but_no_candidate(self):
        task = Task(
            id="t-no-candidate",
            typ=TaskType.SEARCH,
            prompt="Suche Wetter Berlin",
            beschreibung="search",
            strategy=Strategy(allow_tools=True),
            interaction_class=InteractionClass.TOOL_REQUEST,
        )

        class FakeRegistry:
            def list_tools(self, active_only=True):
                return []

        async def fake_discover(*args, **kwargs):
            return {"tools": [], "source": "remote", "url": "http://127.0.0.1:8766"}

        with patch("tool_runtime.get_tool_registry", return_value=FakeRegistry()), patch("tool_runtime.discover_mcp_bridge", fake_discover):
            decision = asyncio.run(select_live_tool_for_task(task, task.prompt, 0, task.tool_policy))
        self.assertIsNone(decision.selected)
        self.assertEqual(decision.reason, ToolDecisionReason.ELIGIBLE_BUT_NO_CANDIDATE)

    def test_bug_22_classification_does_not_change_eligibility(self):
        executor = object.__new__(Executor)
        task_a = Task(
            id="t-class-a",
            typ=TaskType.CHAT,
            prompt="Prüfe Tools",
            beschreibung="chat",
            strategy=Strategy(allow_tools=True),
            interaction_class=InteractionClass.NORMAL_CHAT,
        )
        task_b = Task(
            id="t-class-b",
            typ=TaskType.CHAT,
            prompt="Prüfe Tools",
            beschreibung="chat",
            strategy=Strategy(allow_tools=True),
            interaction_class=InteractionClass.SOCIAL_GREETING,
        )
        decision_a = executor._evaluate_tool_eligibility(task_a, task_a.prompt, iteration=0)
        decision_b = executor._evaluate_tool_eligibility(task_b, task_b.prompt, iteration=0)
        self.assertEqual(decision_a.eligible, decision_b.eligible)
        self.assertEqual(decision_a.reason, decision_b.reason)

    def test_bug_23_lightweight_no_longer_forces_followup_break(self):
        class FakeScore:
            total = 3.0
            acceptable = False

            def summary(self):
                return "score=3.0"

        class FakeDecision:
            needed = False
            mode = "none"
            reason = "done"
            switch_provider = False
            followup_prompt = ""
            sub_tasks = []

        class FakeLogic:
            def __init__(self):
                self.followup_calls = 0

            def evaluate(self, *args, **kwargs):
                return FakeScore()

            def decide_followup(self, *args, **kwargs):
                self.followup_calls += 1
                return FakeDecision()

        class FakeRelay:
            async def ask_with_fallback(self, *args, **kwargs):
                return "Antwort", "test-provider"

        class FakeWatchdog:
            def record_progress(self, task_id):
                return None

        class FakeState:
            def to_dict(self):
                return {}

        class FakeToolState:
            def get_or_create(self, *args, **kwargs):
                return FakeState()

            def pop_next_input(self, *args, **kwargs):
                return ""

        executor = object.__new__(Executor)
        executor.logic = FakeLogic()
        executor.relay = FakeRelay()
        executor._tool_state = FakeToolState()
        executor._notify = lambda *args, **kwargs: None
        executor._get_watchdog = lambda: FakeWatchdog()

        task = Task(
            id="t-follow",
            typ=TaskType.CHAT,
            prompt="Hallo",
            beschreibung="chat",
            strategy=Strategy(allow_tools=False, allow_followup=True),
            interaction_class=InteractionClass.SOCIAL_GREETING,
        )

        asyncio.run(executor._execute_ai(task))
        self.assertEqual(executor.logic.followup_calls, 1)

    def test_bug_24_decision_trace_blocked_allow_tools_false(self):
        executor = object.__new__(Executor)
        task = Task(
            id="t-trace-blocked",
            typ=TaskType.CHAT,
            prompt="Nutze ein Tool",
            beschreibung="chat",
            strategy=Strategy(allow_tools=False),
        )

        decision = executor._evaluate_tool_eligibility(task, task.prompt, iteration=0)
        self.assertFalse(decision.eligible)
        self.assertEqual(task.decision_trace.entries[-1].phase, TracePhase.ELIGIBILITY)
        self.assertEqual(task.decision_trace.entries[-1].data["reason"], ToolDecisionReason.BLOCKED_ALLOW_TOOLS_FALSE.value)

    def test_bug_25_decision_trace_allowed_explicit_policy(self):
        executor = object.__new__(Executor)
        task = Task(
            id="t-trace-allowed",
            typ=TaskType.CHAT,
            prompt="Was ist 2+2?",
            beschreibung="chat",
            strategy=Strategy(allow_tools=True),
        )

        decision = executor._evaluate_tool_eligibility(task, task.prompt, iteration=0)
        self.assertTrue(decision.eligible)
        self.assertEqual(task.decision_trace.entries[-1].data["reason"], ToolDecisionReason.ELIGIBLE.value)

    def test_bug_26_decision_trace_eligible_but_no_candidate(self):
        class FakeState:
            def to_dict(self):
                return {}

        class FakeToolState:
            def record_call(self, *args, **kwargs):
                return None

            def get_or_create(self, *args, **kwargs):
                return FakeState()

            def generate_next_input(self, *args, **kwargs):
                return ""

        executor = object.__new__(Executor)
        executor._tool_state = FakeToolState()
        executor._notify = lambda *args, **kwargs: None

        task = Task(
            id="t-trace-no-candidate",
            typ=TaskType.CHAT,
            prompt="Suche Wetter Berlin",
            beschreibung="chat",
            strategy=Strategy(allow_tools=True),
        )

        async def fake_select(*args, **kwargs):
            from tool_policy import ToolSelectionDecision
            return ToolSelectionDecision(selected=None, reason=ToolDecisionReason.ELIGIBLE_BUT_NO_CANDIDATE, metadata={"candidate_count": 0})

        with patch("executor.select_live_tool_for_task", fake_select):
            ctx, follow = asyncio.run(executor._maybe_use_tool(task, task.prompt, iteration=0, used_tool_ids=set()))

        self.assertEqual(ctx, "")
        self.assertEqual(follow, "")
        events = [e.event for e in task.decision_trace.entries if e.phase == TracePhase.SELECTION]
        self.assertIn("no_candidate", events)

    def test_bug_27_decision_trace_tool_execution_failed(self):
        class FakeState:
            def to_dict(self):
                return {}

        class FakeToolState:
            def record_call(self, *args, **kwargs):
                return None

            def get_or_create(self, *args, **kwargs):
                return FakeState()

            def generate_next_input(self, *args, **kwargs):
                return ""

        executor = object.__new__(Executor)
        executor._tool_state = FakeToolState()
        executor._notify = lambda *args, **kwargs: None

        task = Task(
            id="t-trace-failed",
            typ=TaskType.CHAT,
            prompt="Nutze Tool",
            beschreibung="chat",
            strategy=Strategy(allow_tools=True),
        )

        async def fake_select(*args, **kwargs):
            from tool_policy import ToolSelectionDecision
            return ToolSelectionDecision(
                selected={
                    "identifier": "tool.fail",
                    "name": "Fail Tool",
                    "kind": "api",
                    "category": "general",
                    "source": "registry",
                },
                reason=ToolDecisionReason.SELECTED_CANDIDATE,
                metadata={"candidate_count": 1},
            )

        async def fake_run(*args, **kwargs):
            return {"ok": False, "error": "boom", "via": "api", "status_code": 500}

        with patch("executor.select_live_tool_for_task", fake_select), patch("executor.run_selected_tool", fake_run):
            ctx, follow = asyncio.run(executor._maybe_use_tool(task, task.prompt, iteration=0, used_tool_ids=set()))

        self.assertEqual(ctx, "")
        self.assertEqual(follow, "")
        events = [e.event for e in task.decision_trace.entries]
        self.assertIn("execution_failed", events)
        self.assertIn("context_skipped", events)
        self.assertIn("followup_not_generated", events)

    def test_bug_28_decision_trace_tool_execution_succeeded(self):
        class FakeState:
            def to_dict(self):
                return {}

        class FakeToolState:
            def record_call(self, *args, **kwargs):
                return None

            def get_or_create(self, *args, **kwargs):
                return FakeState()

            def generate_next_input(self, *args, **kwargs):
                return "next prompt"

        executor = object.__new__(Executor)
        executor._tool_state = FakeToolState()
        executor._notify = lambda *args, **kwargs: None

        task = Task(
            id="t-trace-success",
            typ=TaskType.CHAT,
            prompt="Nutze Tool",
            beschreibung="chat",
            strategy=Strategy(allow_tools=True),
        )

        async def fake_select(*args, **kwargs):
            from tool_policy import ToolSelectionDecision
            return ToolSelectionDecision(
                selected={
                    "identifier": "tool.ok",
                    "name": "OK Tool",
                    "kind": "api",
                    "category": "general",
                    "source": "registry",
                },
                reason=ToolDecisionReason.SELECTED_CANDIDATE,
                metadata={"candidate_count": 1},
            )

        async def fake_run(*args, **kwargs):
            return {"ok": True, "content": "sunny", "via": "api", "status_code": 200}

        with patch("executor.select_live_tool_for_task", fake_select), patch("executor.run_selected_tool", fake_run):
            ctx, follow = asyncio.run(executor._maybe_use_tool(task, task.prompt, iteration=0, used_tool_ids=set()))

        self.assertIn("[Tool-Kontext]", ctx)
        self.assertEqual(follow, "next prompt")
        events = [e.event for e in task.decision_trace.entries]
        self.assertIn("execution_succeeded", events)
        self.assertIn("context_appended", events)
        self.assertIn("followup_generated", events)

    def test_bug_29_task_to_dict_contains_serializable_decision_trace(self):
        task = Task(
            id="t-trace-serialize",
            typ=TaskType.CHAT,
            prompt="Hallo",
            beschreibung="chat",
        )
        task.decision_trace.add(TracePhase.ELIGIBILITY, "evaluated", {"eligible": True, "reason": "eligible"})

        data = task.to_dict()
        self.assertIn("decision_trace", data)
        self.assertEqual(data["decision_trace"][0]["phase"], "eligibility")
        self.assertEqual(data["decision_trace"][0]["event"], "evaluated")
        json.dumps(data)

    def test_bug_34_explanatory_weather_prompt_stays_normal_chat(self):
        result = classify_interaction_result(
            "Erkläre mir das Wetter als sprachliches Motiv in Literatur"
        )
        self.assertEqual(result.interaction_class, InteractionClass.NORMAL_CHAT)

    def test_bug_35_explanatory_api_github_prompt_stays_normal_chat(self):
        result = classify_interaction_result(
            "Erkläre mir die GitHub API Architektur konzeptionell"
        )
        self.assertEqual(result.interaction_class, InteractionClass.NORMAL_CHAT)

    def test_bug_36_explicit_search_prompt_remains_tool_request(self):
        result = classify_interaction_result("Suche GitHub API Dokumentation")
        self.assertEqual(result.interaction_class, InteractionClass.TOOL_REQUEST)

    def test_neural_core_propagates_seven_regions(self):
        from neural_core import NeuralCortex, NeuralRegion, PIPELINE_ORDER

        cortex = NeuralCortex()
        trace = cortex.propagate(
            interaction_class="NORMAL_CHAT",
            intent="chat",
            retrieval_ctx={
                "relevant_facts": [{"key": "test"}],
                "conversation_history": [],
                "relevant_task_results": [],
                "semantic_context": "",
                "active_directives": [],
                "behavioral_risks": [],
            },
            word_count=5,
            execution_score=7.5,
        )
        self.assertEqual(len(trace.signals), len(PIPELINE_ORDER))
        self.assertEqual(trace.signals[0].region, NeuralRegion.PERCEPTION)
        self.assertEqual(trace.signals[-1].region, NeuralRegion.CONSOLIDATION)

    def test_neural_core_reinforce_adjusts_weights_on_success(self):
        from neural_core import NeuralCortex, NeuralRegion

        cortex = NeuralCortex()
        before = cortex.get_weight(NeuralRegion.PERCEPTION, NeuralRegion.RETRIEVAL)
        trace = cortex.propagate(
            interaction_class="NORMAL_CHAT",
            intent="chat",
            retrieval_ctx={},
            word_count=3,
        )
        changed = cortex.reinforce(trace, 8.0)
        after = cortex.get_weight(NeuralRegion.PERCEPTION, NeuralRegion.RETRIEVAL)
        self.assertTrue(changed or after >= before)

    def test_neural_core_low_activation_disables_tools(self):
        from neural_core import NeuralCortex

        cortex = NeuralCortex()
        trace = cortex.propagate(
            interaction_class="SOCIAL_ACKNOWLEDGMENT",
            intent="chat",
            retrieval_ctx={},
            word_count=1,
        )
        modulation = cortex.modulate_strategy(
            allow_tools=True,
            allow_followup=True,
            allow_provider_switch=True,
            trace=trace,
        )
        self.assertFalse(modulation.allow_tools)

    def test_neural_core_stats_exposes_dashboard_payload(self):
        from neural_core import NeuralCortex

        stats = NeuralCortex().stats()
        self.assertEqual(stats["regions"], 7)
        self.assertIn("weights", stats)
        self.assertIn("perception:retrieval", stats["weights"])
        self.assertIn("pipeline", stats)

    def test_vector_memory_stats_when_chromadb_available(self):
        from vector_memory import get_vector_memory

        stats = get_vector_memory().stats()
        self.assertIn("aktiv", stats)
        self.assertFalse(stats["aktiv"])
        self.assertEqual(stats.get("grund"), "deaktiviert")


class TestHermesCompatibilityLayer(unittest.TestCase):
    def setUp(self):
        self.policy = ConfirmationPolicy(path=Path('/tmp/isaac_test_confirmation_queue.json'))
        self.policy._queue = []
        self.adapter = HermesCompatibilityAdapter(confirmation_policy=self.policy)

    def test_skill_registration(self):
        self.adapter.register_skill({"name": "search_assist", "description": "help", "tools": ["search"]})
        self.assertIsNotNone(self.adapter.skill_registry.get("search_assist"))

    def test_tool_schema_mapping(self):
        normalized = HermesToolSchemaMapper.normalize({"name": "lookup", "inputSchema": {"type": "object"}})
        self.assertEqual(normalized["name"], "lookup")
        self.assertEqual(normalized["risk"], "medium")

    def test_permission_blocking(self):
        self.adapter.register_tool(
            {"name": "danger_tool", "description": "x", "risk": "critical", "outside_effect": True},
            lambda payload: {"ok": True, "payload": payload},
        )
        result = self.adapter.execute_tool("danger_tool", {"a": 1}, ExecutionContext(caller="user", level=0))
        self.assertFalse(result.ok)
        self.assertIn("Review-ID", result.error)

    def test_confirmation_queue(self):
        self.adapter.register_tool(
            {"name": "confirm_tool", "description": "x", "risk": "critical", "outside_effect": True},
            lambda payload: {"ok": True},
        )
        _ = self.adapter.execute_tool("confirm_tool", {}, ExecutionContext(caller="user", level=0))
        self.assertGreaterEqual(len(self.policy.pending()), 1)

    def test_browser_adapter_dry_run(self):
        browser = HermesBrowserAdapter()
        result = browser.run(BrowserAction(action="browser_navigate", url="https://example.org"), dry_run=True)
        self.assertTrue(result.ok)
        self.assertTrue(result.output["dry_run"])

    def test_computer_use_action_validation(self):
        cu = HermesComputerUseAdapter()
        result = cu.validate(ComputerAction(action="shell_command", params={"command": "echo ok"}, permission=PermissionMetadata(timeout=5, allowed_scope="workspace")))
        self.assertTrue(result.ok)

    def test_computer_use_shell_blocks_unsafe_commands_in_runtime(self):
        from computer_use import ComputerUseRuntime, AgentAction

        runtime = ComputerUseRuntime()
        result = asyncio.run(runtime.execute(AgentAction("shell", {"command": "sudo rm -rf /"})))
        self.assertFalse(result.get("ok"))


    def test_computer_use_action_blocks_unsafe_shell(self):
        cu = HermesComputerUseAdapter()
        result = cu.validate(ComputerAction(
            action="shell_command",
            params={"command": "sudo rm -rf /"},
            permission=PermissionMetadata(timeout=5, allowed_scope="workspace"),
        ))
        self.assertFalse(result.ok)

    def test_computer_use_action_scope_validation(self):
        cu = HermesComputerUseAdapter()
        result = cu.validate(ComputerAction(
            action="observe",
            permission=PermissionMetadata(timeout=5, allowed_scope="internet"),
        ))
        self.assertFalse(result.ok)

    def test_failed_tool_execution(self):
        self.adapter.register_tool({"name": "broken", "description": "x"}, lambda payload: 1 / 0)
        result = self.adapter.execute_tool("broken", {}, ExecutionContext(caller="user", level=9))
        self.assertFalse(result.ok)

    def test_audit_logging_and_memory_writeback_and_mcp_mirror(self):
        writes = []
        self.adapter.register_tool({"name": "safe_tool", "description": "x", "risk": "low"}, lambda payload: {"value": 1})
        mcp = MCPRegistry()
        self.adapter.mirror_tool_to_mcp(mcp, "safe_tool")
        result = self.adapter.execute_flow(
            user_task="use safe tool",
            tool_name="safe_tool",
            payload={},
            ctx=ExecutionContext(caller="user", level=9, task_id="t-hermes"),
            memory_writeback=lambda task, tool_result: writes.append((task, tool_result.ok)),
        )
        mcp_result = mcp.invoke_tool("safe_tool", {})
        self.assertTrue(result.ok)
        self.assertTrue(mcp_result["ok"])
        self.assertIn("output", mcp_result)
        self.assertIn("metadata", mcp_result)
        self.assertEqual(writes[0][0], "use safe tool")

    def test_mcp_mirror_propagates_blocked_tool_failure(self):
        self.adapter.register_tool(
            {"name": "danger_tool", "description": "x", "risk": "critical", "outside_effect": True},
            lambda payload: {"ignored": True},
        )
        mcp = MCPRegistry()
        self.adapter.mirror_tool_to_mcp(mcp, "danger_tool")
        mcp_result = mcp.invoke_tool("danger_tool", {})
        self.assertFalse(mcp_result["ok"])
        self.assertIn("danger_tool", mcp_result["error"])
        self.assertIn("Review-ID", mcp_result["error"])
        self.assertIn("queue_id", mcp_result)

    def test_result_contract_direct_and_mcp_paths(self):
        self.adapter.register_tool(
            {"name": "contract_ok", "description": "x", "risk": "low", "input_schema": {"type": "object", "required": ["query"]}},
            lambda payload: {"echo": payload["query"]},
        )
        self.adapter.register_tool(
            {"name": "contract_fail", "description": "x", "risk": "low"},
            lambda payload: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        mcp = MCPRegistry()
        self.adapter.mirror_tool_to_mcp(mcp, "contract_ok")
        self.adapter.mirror_tool_to_mcp(mcp, "contract_fail")

        direct_ok = self.adapter.execute_tool("contract_ok", {"query": "hi"}, ExecutionContext(caller="user", level=9))
        self.assertTrue(direct_ok.ok)
        self.assertIsInstance(direct_ok.metadata, dict)

        direct_arg_error = self.adapter.execute_tool("contract_ok", {}, ExecutionContext(caller="user", level=9))
        self.assertFalse(direct_arg_error.ok)
        self.assertIn("invalid_arguments", direct_arg_error.error)

        direct_handler_error = self.adapter.execute_tool("contract_fail", {}, ExecutionContext(caller="user", level=9))
        self.assertFalse(direct_handler_error.ok)
        self.assertIn("boom", direct_handler_error.error)

        mcp_ok = mcp.invoke_tool("contract_ok", {"query": "world"})
        self.assertTrue(mcp_ok["ok"])
        self.assertIn("output", mcp_ok)
        self.assertIn("metadata", mcp_ok)

        mcp_arg_error = mcp.invoke_tool("contract_ok", {})
        self.assertFalse(mcp_arg_error["ok"])
        self.assertIn("invalid_arguments", mcp_arg_error["error"])

        mcp_handler_error = mcp.invoke_tool("contract_fail", {})
        self.assertFalse(mcp_handler_error["ok"])
        self.assertIn("boom", mcp_handler_error["error"])

    def test_mcp_registry_wraps_raw_handler_payloads_in_output(self):
        mcp = MCPRegistry()
        mcp.register_tool("raw_list", {"description": "x"}, handler=lambda **kwargs: [1, 2, 3])
        mcp.register_tool("raw_status", {"description": "x"}, handler=lambda **kwargs: {"ok": True, "tasks": [{"id": "t1"}]})

        list_result = mcp.invoke_tool("raw_list", {})
        self.assertTrue(list_result["ok"])
        self.assertEqual(list_result["output"], [1, 2, 3])

        status_result = mcp.invoke_tool("raw_status", {})
        self.assertTrue(status_result["ok"])
        self.assertEqual(status_result["output"]["tasks"][0]["id"], "t1")


    def test_mcp_mirror_propagates_handler_failure(self):
        self.adapter.register_tool({"name": "broken_tool", "description": "x"}, lambda payload: 1 / 0)
        mcp = MCPRegistry()
        self.adapter.mirror_tool_to_mcp(mcp, "broken_tool")
        mcp_result = mcp.invoke_tool("broken_tool", {})
        self.assertFalse(mcp_result["ok"])
        self.assertIn("broken_tool", mcp_result["error"])
        self.assertIn("division by zero", mcp_result["error"])


class TestSelfModelHooks(unittest.TestCase):
    def test_preference_extracted_from_owner_statement(self):
        from self_model_hooks import process_interaction
        from self_model import get_self_model

        updates = process_interaction(
            user_input="Ich bevorzuge kurze nüchterne Antworten",
            interaction_class="NORMAL_CHAT",
            score=7.0,
        )
        self.assertTrue(updates.get("preferences"))
        prefs = get_self_model().relevant_preferences(limit=5)
        self.assertTrue(any(p.get("key") in ("prefer", "response_style") for p in prefs))

    def test_correction_records_high_confidence_preference(self):
        import self_model as self_model_module
        import tempfile
        from pathlib import Path
        from self_model_hooks import process_interaction
        from self_model import SelfModel
        from low_complexity import InteractionClass

        key = f"answer_style_{id(self)}"
        with tempfile.TemporaryDirectory() as tmp:
            isolated = SelfModel(path=Path(tmp) / "self_model.json")
            previous = self_model_module._model
            self_model_module._model = isolated
            try:
                process_interaction(
                    user_input=f"korrektur: {key} = kurz und direkt",
                    interaction_class=InteractionClass.NORMAL_CHAT,
                    score=7.0,
                )
            finally:
                self_model_module._model = previous
            owner_prefers = isolated.data.get("preference_state", {}).get("owner_prefers", [])
        self.assertTrue(
            any(
                p.get("key") == key and p.get("confidence", 0) >= 0.9
                for p in owner_prefers
                if isinstance(p, dict)
            )
        )

    def test_shared_theme_requires_recurrence(self):
        import self_model as self_model_module
        import tempfile
        from pathlib import Path
        from self_model import SelfModel
        from self_model_hooks import process_interaction, _extract_topic_theme

        theme_text = "routing executor klassifikation stabil"
        expected_theme = _extract_topic_theme(theme_text)
        self.assertEqual(expected_theme, "routing executor klassifikation")

        with tempfile.TemporaryDirectory() as tmp:
            isolated = SelfModel(path=Path(tmp) / "self_model.json")
            previous = self_model_module._model
            self_model_module._model = isolated
            try:
                first = process_interaction(
                    user_input=theme_text,
                    interaction_class="NORMAL_CHAT",
                    score=6.0,
                )
                self.assertEqual(first.get("themes"), [])
                second = process_interaction(
                    user_input=theme_text,
                    interaction_class="NORMAL_CHAT",
                    score=6.0,
                )
            finally:
                self_model_module._model = previous

        self.assertEqual(len(second.get("themes", [])), 1)
        self.assertEqual(second["themes"][0].get("theme"), expected_theme)
        self.assertEqual(second["themes"][0].get("count"), 2)

    def test_retrieval_enriched_with_self_model_preferences(self):
        from self_model_hooks import enrich_retrieval_with_self_model
        from self_model import get_self_model

        get_self_model().record_owner_preference(
            key="test_pref",
            value="knapp antworten",
            confidence=0.8,
            source="test",
        )
        enriched = enrich_retrieval_with_self_model({"preferences_context": []})
        self.assertTrue(enriched.get("self_model_preferences"))
        self.assertTrue(enriched.get("preferences_context"))

    def test_greeting_does_not_record_preference(self):
        import self_model as self_model_module
        import tempfile
        from pathlib import Path
        from self_model import SelfModel
        from self_model_hooks import process_interaction
        from low_complexity import InteractionClass

        with tempfile.TemporaryDirectory() as tmp:
            isolated = SelfModel(path=Path(tmp) / "self_model.json")
            previous = self_model_module._model
            self_model_module._model = isolated
            try:
                updates = process_interaction(
                    user_input="Hallo Isaac, antworte bitte kürzer",
                    interaction_class=InteractionClass.SOCIAL_GREETING,
                    score=7.0,
                )
            finally:
                self_model_module._model = previous

        self.assertEqual(updates.get("preferences"), [])
        owner_prefers = isolated.data.get("preference_state", {}).get("owner_prefers", [])
        self.assertEqual(owner_prefers, [])

    def test_casual_style_mention_not_recorded_as_preference(self):
        import self_model as self_model_module
        import tempfile
        from pathlib import Path
        from self_model import SelfModel
        from self_model_hooks import process_interaction
        from low_complexity import InteractionClass

        with tempfile.TemporaryDirectory() as tmp:
            isolated = SelfModel(path=Path(tmp) / "self_model.json")
            previous = self_model_module._model
            self_model_module._model = isolated
            try:
                updates = process_interaction(
                    user_input="Kannst du das Wetter als Motiv kürzer erklären?",
                    interaction_class=InteractionClass.NORMAL_CHAT,
                    score=7.0,
                )
            finally:
                self_model_module._model = previous

        self.assertEqual(updates.get("preferences"), [])
        owner_prefers = isolated.data.get("preference_state", {}).get("owner_prefers", [])
        self.assertEqual(owner_prefers, [])

    def test_positive_confirmation_boosts_pending_preference(self):
        import self_model as self_model_module
        import tempfile
        from pathlib import Path
        from self_model import SelfModel
        from self_model_hooks import process_interaction
        from low_complexity import InteractionClass

        with tempfile.TemporaryDirectory() as tmp:
            isolated = SelfModel(path=Path(tmp) / "self_model.json")
            previous = self_model_module._model
            self_model_module._model = isolated
            try:
                first = process_interaction(
                    user_input="Ich bevorzuge kurze nüchterne Antworten",
                    interaction_class=InteractionClass.NORMAL_CHAT,
                    score=7.0,
                )
                second = process_interaction(
                    user_input="Danke, genau so",
                    interaction_class=InteractionClass.SOCIAL_ACKNOWLEDGMENT,
                    score=6.5,
                )
            finally:
                self_model_module._model = previous

        self.assertTrue(first.get("preferences"))
        self.assertGreaterEqual(second.get("confirmations", 0), 1)
        owner_prefers = isolated.data.get("preference_state", {}).get("owner_prefers", [])
        confirmed = next(
            (
                p for p in owner_prefers
                if isinstance(p, dict) and p.get("key") == "prefer"
            ),
            None,
        )
        self.assertIsNotNone(confirmed)
        self.assertGreaterEqual(float(confirmed.get("confidence", 0)), 0.74)
        self.assertEqual(confirmed.get("source"), "owner_confirmation")

    def test_confirmed_preference_synced_to_memory(self):
        import self_model as self_model_module
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        from self_model import SelfModel
        from self_model_hooks import process_interaction
        from low_complexity import InteractionClass

        stored_facts: dict[str, str] = {}

        class FakeMemory:
            def set_fact(self, key, value, source="", confidence=1.0):
                stored_facts[key] = value
                return True

            def log_development_event(self, **kwargs):
                return None

        with tempfile.TemporaryDirectory() as tmp:
            sm_path = Path(tmp) / "self_model.json"
            isolated = SelfModel(path=sm_path)
            previous_sm = self_model_module._model
            self_model_module._model = isolated
            key = f"answer_style_{id(self)}"
            try:
                with patch("memory.get_memory", return_value=FakeMemory()):
                    process_interaction(
                        user_input=f"korrektur: {key} = kurz und direkt",
                        interaction_class=InteractionClass.NORMAL_CHAT,
                        score=7.0,
                    )
            finally:
                self_model_module._model = previous_sm

        fact_key = f"pref.{key}.kurz_und_direkt"
        self.assertEqual(stored_facts.get(fact_key), "kurz und direkt")

    def test_self_model_detects_memory_contradiction(self):
        import self_model as self_model_module
        import tempfile
        from pathlib import Path
        from self_model import SelfModel
        from self_model_hooks import detect_self_model_fact_contradictions, enrich_retrieval_with_self_model

        class FakeMemory:
            def __init__(self, facts):
                self._facts = dict(facts)

            def get_fact_record(self, key):
                value = self._facts.get(key)
                if value is None:
                    return None
                return {"key": key, "value": value, "confidence": 1.0, "source": "Steffen"}

            def all_facts(self):
                return dict(self._facts)

        with tempfile.TemporaryDirectory() as tmp:
            isolated = SelfModel(path=Path(tmp) / "self_model.json")
            previous = self_model_module._model
            self_model_module._model = isolated
            try:
                isolated.record_owner_preference(
                    key="response_style",
                    value="kurz und knapp",
                    confidence=0.9,
                    source="owner_correction",
                )
                fact_key = isolated._preference_fact_key({
                    "key": "response_style",
                    "value": "kurz und knapp",
                })
                fake_memory = FakeMemory({fact_key: "ausführlich und detailliert"})
                contradictions = detect_self_model_fact_contradictions(memory=fake_memory)
                enriched = enrich_retrieval_with_self_model(
                    {"preferences_context": [], "risk_flags": []},
                    memory=fake_memory,
                )
            finally:
                self_model_module._model = previous

        self.assertTrue(contradictions)
        self.assertTrue(enriched.get("self_model_contradictions"))
        self.assertIn("self_model_fact_contradiction", enriched.get("risk_flags", []))


class TestConstitutionOwnerOverride(unittest.TestCase):
    def test_privilege_escalation_blocked_without_override(self):
        from constitution import get_constitution
        from constitution_override import evaluate_owner_override, build_override_context
        from config import Level

        verdict = get_constitution().validate_action(
            "tool_invoke",
            {"privilege_escalation": True, "owner_approved": False, "audit_logged": True},
        )
        self.assertFalse(verdict.get("allowed"))
        result = evaluate_owner_override(
            verdict,
            build_override_context(caller_level=Level.TASK),
        )
        self.assertFalse(result.get("allowed"))

    def test_override_prefix_with_sudo_allows_and_audits(self):
        from constitution_override import apply_constitution_gate, build_override_context
        from config import Level
        from memory import get_memory

        gate = apply_constitution_gate(
            "tool_invoke",
            {"privilege_escalation": True, "owner_approved": False, "audit_logged": True},
            build_override_context(
                prompt="override: notwendiger Zugriff für Wartung",
                sudo_active=True,
                caller_level=Level.STEFFEN,
                source="test",
            ),
        )
        self.assertTrue(gate.get("allowed"))
        self.assertTrue((gate.get("override") or {}).get("overridden"))
        events = get_memory().recent_development_events(15)
        self.assertTrue(
            any(
                e.get("event_type") == "constitution_override"
                and e.get("target_key") == "tool_invoke"
                for e in events
            )
        )

    def test_constitution_self_modify_not_overridable(self):
        from constitution_override import apply_constitution_gate, build_override_context
        from config import Level

        gate = apply_constitution_gate(
            "tool_invoke",
            {"self_modify_constitution": True, "audit_logged": True},
            build_override_context(
                sudo_active=True,
                caller_level=Level.STEFFEN,
                override_reason="verfassung ändern",
                source="test",
            ),
        )
        self.assertFalse(gate.get("allowed"))
        self.assertIn("constitution_not_self_editable", gate.get("blocked_by", []))

    def test_detect_override_prefix(self):
        from constitution_override import detect_override_prefix

        explicit, reason = detect_override_prefix("override: Wartungsfenster für Tool-Test")
        self.assertTrue(explicit)
        self.assertIn("Wartungsfenster", reason)


class TestMcpJsonRpc(unittest.TestCase):
    def setUp(self):
        from mcp_jsonrpc import get_jsonrpc_handler
        from mcp_registry import get_mcp_registry

        self.handler = get_jsonrpc_handler(get_mcp_registry())

    def _call(self, method: str, params: dict | None = None, req_id: int = 1) -> dict:
        return self.handler.dispatch({
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params or {},
        })

    def test_jsonrpc_initialize(self):
        resp = self._call(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1"},
            },
        )
        self.assertEqual(resp.get("id"), 1)
        self.assertIn("result", resp)
        self.assertEqual(resp["result"].get("protocolVersion"), "2024-11-05")
        self.assertEqual(resp["result"]["serverInfo"]["name"], "isaac")

    def test_jsonrpc_tools_list_and_call(self):
        self._call("initialize", {"protocolVersion": "2024-11-05", "capabilities": {}})
        tools_resp = self._call("tools/list", req_id=2)
        tools = tools_resp["result"]["tools"]
        self.assertTrue(any(t.get("name") == "isaac.query_memory" for t in tools))

        call_resp = self._call(
            "tools/call",
            {"name": "isaac.query_memory", "arguments": {"query": "status", "limit": 2}},
            req_id=3,
        )
        self.assertIn("result", call_resp)
        self.assertFalse(call_resp["result"].get("isError"))
        self.assertTrue(call_resp["result"]["content"])

    def test_jsonrpc_resources_read(self):
        self._call("initialize", {"protocolVersion": "2024-11-05", "capabilities": {}})
        resp = self._call(
            "resources/read",
            {"uri": "resource://constitution", "params": {}},
            req_id=4,
        )
        self.assertIn("result", resp)
        self.assertTrue(resp["result"]["contents"])
        self.assertIn("constitution", resp["result"]["contents"][0]["text"])

    def test_jsonrpc_unknown_method(self):
        resp = self._call("does/not/exist", req_id=5)
        self.assertIn("error", resp)
        self.assertEqual(resp["error"]["code"], -32601)

    def test_stdio_transport_ping(self):
        import json
        import subprocess
        import sys

        proc = subprocess.run(
            [sys.executable, "mcp_server.py", "--stdio"],
            input='{"jsonrpc":"2.0","id":9,"method":"ping","params":{}}\n',
            capture_output=True,
            text=True,
            cwd=str(Path(__file__).resolve().parent),
            timeout=10,
        )
        self.assertEqual(proc.returncode, 0)
        line = proc.stdout.strip().splitlines()[-1]
        data = json.loads(line)
        self.assertEqual(data.get("id"), 9)
        self.assertEqual(data.get("result"), {})


class TestEvalSuites(unittest.TestCase):
    def _assert_eval_suite(self, result: dict):
        self.assertGreater(int(result.get("total", 0)), 0)
        failed = [c for c in result.get("cases", []) if not c.get("ok")]
        self.assertEqual(result.get("passed"), result.get("total"), msg=failed)

    def test_mcp_eval_suite_passes(self):
        from evals.mcp_eval import run

        result = run()
        self.assertEqual(result.get("suite"), "mcp")
        self._assert_eval_suite(result)

    def test_replay_eval_suite_passes(self):
        from evals.replay_eval import run

        result = run()
        self.assertEqual(result.get("suite"), "replay")
        self._assert_eval_suite(result)

    def test_learning_eval_regelwerk_memory_cases(self):
        from evals.learning_eval import run

        result = run()
        self.assertEqual(result.get("suite"), "learning")
        names = {c["name"] for c in result.get("cases", [])}
        self.assertIn("regelwerk_answer_persists_definition_fact", names)
        self.assertIn("definition_fact_surfaces_in_retrieval", names)
        for case in result.get("cases", []):
            if case["name"] in {
                "regelwerk_answer_persists_definition_fact",
                "definition_fact_surfaces_in_retrieval",
            }:
                self.assertTrue(case.get("ok"), msg=case)


class TestMcpToolRuntime(unittest.TestCase):
    def test_invoke_mcp_tool_uses_local_registry_fallback(self):
        from tool_runtime import invoke_mcp_tool

        async def fake_discover(*args, **kwargs):
            return {
                "ok": False,
                "source": "local-fallback",
                "tools": [{"name": "isaac.query_memory"}],
                "url": "http://127.0.0.1:8766",
            }

        with patch("tool_runtime.discover_mcp_bridge", fake_discover):
            result = asyncio.run(
                invoke_mcp_tool("isaac.query_memory", {"query": "status", "limit": 2})
            )
        self.assertTrue(result.get("ok"))
        self.assertEqual(result.get("via"), "mcp")
        self.assertEqual(result.get("transport"), "local")

    def test_run_selected_tool_unified_mcp_source(self):
        from tool_runtime import run_selected_tool

        async def fake_invoke(name, arguments, **kwargs):
            self.assertEqual(name, "isaac.query_memory")
            return {
                "ok": True,
                "output": {"blocks": []},
                "error": "",
                "metadata": {"tool": name},
                "via": "mcp",
                "transport": "local",
            }

        selection = {
            "source": "mcp",
            "mcp_name": "isaac.query_memory",
            "kind": "mcp",
            "identifier": "mcp:isaac.query_memory",
        }
        with patch("tool_runtime.invoke_mcp_tool", fake_invoke):
            result = asyncio.run(run_selected_tool(selection, "status"))
        self.assertTrue(result.get("ok"))
        self.assertEqual(result.get("via"), "mcp")

    def test_select_live_tool_marks_unified_mcp_source(self):
        from tool_runtime import select_live_tool_for_task

        task = Task(
            id=f"t-mcp-unified-{id(self)}",
            typ=TaskType.SEARCH,
            prompt="Suche Wetter Berlin",
            beschreibung="search",
            strategy=Strategy(allow_tools=True),
            interaction_class=InteractionClass.TOOL_REQUEST,
        )

        class FakeRegistry:
            def list_tools(self, active_only=True):
                return []

        async def fake_discover(*args, **kwargs):
            return {
                "ok": True,
                "source": "local-fallback",
                "tools": [{"name": "isaac.search_web", "description": "search"}],
                "url": "http://127.0.0.1:8766",
            }

        with patch("tool_runtime.get_tool_registry", return_value=FakeRegistry()), patch(
            "tool_runtime.discover_mcp_bridge", fake_discover
        ):
            decision = asyncio.run(select_live_tool_for_task(task, task.prompt, 0, task.tool_policy))
        self.assertIsNotNone(decision.selected)
        self.assertEqual(decision.selected.get("source"), "mcp")
        self.assertEqual(decision.selected.get("mcp_name"), "isaac.search_web")

    def test_legacy_mcp_remote_source_still_routes_through_invoke(self):
        from tool_runtime import run_selected_tool

        calls = {"count": 0}

        async def fake_invoke(name, arguments, **kwargs):
            calls["count"] += 1
            return {"ok": True, "output": "ok", "error": "", "metadata": {}, "via": "mcp"}

        selection = {
            "source": "mcp_remote",
            "mcp_name": "isaac.query_memory",
            "kind": "mcp",
        }
        with patch("tool_runtime.invoke_mcp_tool", fake_invoke):
            asyncio.run(run_selected_tool(selection, "status"))
        self.assertEqual(calls["count"], 1)


class TestForgettingDecay(unittest.TestCase):
    def test_contradicted_fact_degrades_confidence(self):
        from memory import get_memory

        mem = get_memory()
        key = f"pref_contradict_{id(self)}"
        mem.set_fact(key, "alpha", source="inferred", confidence=0.7)
        mem.set_fact(key, "beta", source="inferred", confidence=0.7)
        record = mem.get_fact_record(key)
        self.assertIsNotNone(record)
        self.assertLess(float(record["confidence"]), 0.7)

    def test_owner_correction_keeps_high_confidence(self):
        from memory import get_memory

        mem = get_memory()
        key = f"pref_owner_{id(self)}"
        mem.set_fact(key, "alpha", source="inferred", confidence=0.4)
        mem.set_fact(key, "beta", source="Steffen", confidence=1.0)
        record = mem.get_fact_record(key)
        self.assertEqual(float(record["confidence"]), 1.0)

    def test_old_development_events_are_archived(self):
        from memory import get_memory, _conn

        mem = get_memory()
        event_id = mem.log_development_event(
            event_type="test_archive",
            target_kind="test",
            target_key=f"archive_{id(self)}",
            reason="archive regression",
        )
        with _conn() as con:
            con.execute(
                "UPDATE development_events SET ts=? WHERE id=?",
                ("2018-01-01 00:00:00", event_id),
            )
        for i in range(8):
            mem.log_development_event(
                event_type="filler",
                target_kind="test",
                target_key=f"filler_{id(self)}_{i}",
                reason="archive filler",
            )
        archived = mem.archive_development_events(older_than_days=30, keep_recent=5)
        self.assertGreaterEqual(archived, 1)
        archived_rows = mem.recent_archived_development_events(30)
        self.assertTrue(any(int(r["id"]) == event_id for r in archived_rows))

    def test_weak_preference_decays_when_old(self):
        from forgetting_decay import decay_weak_preference_facts
        from memory import get_memory, _conn

        mem = get_memory()
        key = f"chat_pref_{id(self)}"
        mem.set_fact(key, "kurz", source="inferred", confidence=0.5)
        with _conn() as con:
            con.execute(
                "UPDATE facts SET updated=? WHERE key=?",
                ("2019-05-01 00:00:00", key),
            )
        changes = decay_weak_preference_facts(mem)
        self.assertTrue(any(c["key"] == key for c in changes))
        record = mem.get_fact_record(key)
        self.assertLess(float(record["confidence"]), 0.5)


class TestTaskCheckpointing(unittest.TestCase):
    def test_checkpoint_state_machine_constants(self):
        from task_checkpoint import CheckpointState, is_resumable_state, normalize_state

        self.assertIn(CheckpointState.PLANNING, CheckpointState.ALL)
        self.assertIn(CheckpointState.TOOL_PENDING, CheckpointState.ALL)
        self.assertIn(CheckpointState.EVALUATING, CheckpointState.ALL)
        self.assertIn(CheckpointState.LEARNING_COMMIT, CheckpointState.ALL)
        self.assertTrue(is_resumable_state(CheckpointState.PLANNING))
        self.assertTrue(is_resumable_state(CheckpointState.TOOL_RUNNING))
        self.assertFalse(is_resumable_state(CheckpointState.DONE))
        self.assertEqual(normalize_state("tool_running"), CheckpointState.TOOL_PENDING)

    def test_checkpoint_writes_input_snapshot_with_current_prompt(self):
        from executor import get_executor, Task, TaskType, TaskStatus
        from memory import get_memory
        from task_checkpoint import CheckpointState, build_input_snapshot

        exe = get_executor()
        mem = get_memory()
        tid = f"cp_input_{id(self)}"
        task = Task(id=tid, typ=TaskType.CHAT, prompt="original", beschreibung="original")
        task.status = TaskStatus.RUNNING
        exe._tasks[tid] = task
        exe._checkpoint(task, CheckpointState.PLANNING, current_prompt="follow-up prompt")
        cp = mem.get_latest_checkpoint(tid)
        self.assertIsNotNone(cp)
        snap = json.loads(cp["input_snapshot"])
        self.assertEqual(snap["prompt"], "original")
        self.assertEqual(snap["current_prompt"], "follow-up prompt")
        expected = build_input_snapshot(task, current_prompt="follow-up prompt")
        self.assertEqual(snap["task_id"], expected["task_id"])

    def test_resume_task_queues_resumable_task(self):
        from executor import get_executor, Task, TaskType, TaskStatus
        from task_checkpoint import CheckpointState

        exe = get_executor()
        tid = f"cp_resume_{id(self)}"
        task = Task(id=tid, typ=TaskType.CHAT, prompt="resume me", beschreibung="resume me")
        task.status = TaskStatus.RESUMABLE
        exe._tasks[tid] = task
        exe._checkpoint(task, CheckpointState.EVALUATING)
        ok = exe.resume_task(tid)
        task2 = exe.get_task(tid)
        self.assertTrue(ok)
        self.assertEqual(task2.status, TaskStatus.QUEUED)
        self.assertEqual(task2.resume_strategy, "from_checkpoint")

    def test_mark_resumable_sets_status_and_reason(self):
        from executor import get_executor, Task, TaskType, TaskStatus
        from memory import get_memory
        from task_checkpoint import CheckpointState

        exe = get_executor()
        mem = get_memory()
        tid = f"cp_mark_{id(self)}"
        task = Task(id=tid, typ=TaskType.CHAT, prompt="relay fail", beschreibung="relay fail")
        task.status = TaskStatus.RUNNING
        task.checkpoint_state = CheckpointState.EVALUATING
        exe._tasks[tid] = task
        exe._mark_resumable(task, "relay_failure")
        self.assertEqual(task.status, TaskStatus.RESUMABLE)
        cp = mem.get_latest_checkpoint(tid)
        result = json.loads(cp["result_snapshot"])
        self.assertEqual(result.get("resume_reason"), "relay_failure")
        self.assertTrue(result.get("partial"))

    def test_resume_from_evaluating_uses_saved_answer(self):
        import asyncio
        from executor import get_executor, Task, TaskType, TaskStatus
        from logic import QualityScore
        from memory import get_memory

        async def _run():
            exe = get_executor()
            mem = get_memory()
            tid = f"cp_eval_{id(self)}"
            task = Task(id=tid, typ=TaskType.CHAT, prompt="saved answer", beschreibung="saved answer")
            task.status = TaskStatus.RESUMABLE
            exe._tasks[tid] = task
            mem.save_task_checkpoint(
                tid,
                "evaluating",
                input_snapshot={
                    "task_id": tid,
                    "typ": "chat",
                    "prompt": "saved answer",
                    "iteration": 0,
                    "status": "evaluating",
                },
                result_snapshot={
                    "answer_preview": "kurze Antwort",
                    "answer_full": "kurze Antwort mit genug Inhalt für eine Bewertung.",
                    "provider": "test-provider",
                },
            )
            good_score = QualityScore(total=9.0)
            with patch.object(exe.logic, "evaluate", return_value=good_score):
                action = await exe._resume_from_checkpoint(task)
            return action, task

        action, task = asyncio.run(_run())
        self.assertEqual(action, "done")
        self.assertEqual(task.status, TaskStatus.DONE)

    def test_resume_from_planning_continues_execution(self):
        import asyncio
        from executor import get_executor, Task, TaskType, TaskStatus
        from memory import get_memory

        async def _run():
            exe = get_executor()
            mem = get_memory()
            tid = f"cp_plan_{id(self)}"
            task = Task(id=tid, typ=TaskType.CHAT, prompt="plan resume", beschreibung="plan resume")
            task.status = TaskStatus.RESUMABLE
            exe._tasks[tid] = task
            mem.save_task_checkpoint(
                tid,
                "planning",
                input_snapshot={
                    "task_id": tid,
                    "typ": "chat",
                    "prompt": "plan resume",
                    "current_prompt": "plan resume iter 1",
                    "iteration": 1,
                    "status": "running",
                },
            )
            action = await exe._resume_from_checkpoint(task)
            return action, task

        action, task = asyncio.run(_run())
        self.assertEqual(action, "continue")
        self.assertEqual(task.status, TaskStatus.RUNNING)
        self.assertEqual(task.resume_current_prompt, "plan resume iter 1")

    def test_resume_task_skips_when_already_running(self):
        from executor import get_executor, Task, TaskType, TaskStatus
        from task_checkpoint import CheckpointState

        exe = get_executor()
        tid = f"cp_running_{id(self)}"
        task = Task(id=tid, typ=TaskType.CHAT, prompt="running", beschreibung="running")
        task.status = TaskStatus.RESUMABLE
        exe._tasks[tid] = task
        exe._running.add(tid)
        exe._checkpoint(task, CheckpointState.PLANNING)
        self.assertFalse(exe.resume_task(tid))

    def test_resume_evaluating_unacceptable_score_continues_followup(self):
        import asyncio
        from executor import get_executor, Task, TaskType, TaskStatus
        from logic import FollowUpDecision, QualityScore
        from memory import get_memory

        async def _run():
            exe = get_executor()
            mem = get_memory()
            tid = f"cp_follow_{id(self)}"
            task = Task(
                id=tid,
                typ=TaskType.CHAT,
                prompt="explain quantum computing in detail",
                beschreibung="explain",
                strategy=Strategy(allow_followup=True),
            )
            task.status = TaskStatus.RESUMABLE
            exe._tasks[tid] = task
            mem.save_task_checkpoint(
                tid,
                "evaluating",
                input_snapshot={
                    "task_id": tid,
                    "typ": "chat",
                    "prompt": task.prompt,
                    "current_prompt": task.prompt,
                    "iteration": 0,
                    "status": "evaluating",
                },
                result_snapshot={
                    "answer_full": "too short",
                    "answer_preview": "too short",
                    "provider": "test-provider",
                },
            )
            bad_score = QualityScore(total=2.0)
            followup = FollowUpDecision(
                needed=True,
                mode="refine",
                reason="needs detail",
                followup_prompt="Bitte ausführlicher antworten.",
            )
            with patch.object(exe.logic, "evaluate", return_value=bad_score), patch.object(
                exe.logic, "decide_followup", return_value=followup,
            ):
                action = await exe._resume_from_checkpoint(task)
            return action, task

        action, task = asyncio.run(_run())
        self.assertEqual(action, "continue")
        self.assertEqual(task.status, TaskStatus.RUNNING)
        self.assertEqual(task.resume_current_prompt, "Bitte ausführlicher antworten.")
        self.assertEqual(task.resume_start_iteration, 1)

    def test_resume_tool_pending_skips_completed_tool(self):
        import asyncio
        from executor import get_executor, Task, TaskType, TaskStatus
        from memory import get_memory

        async def _run():
            exe = get_executor()
            mem = get_memory()
            tid = f"cp_tool_{id(self)}"
            task = Task(id=tid, typ=TaskType.CHAT, prompt="search weather", beschreibung="search")
            task.status = TaskStatus.RESUMABLE
            exe._tasks[tid] = task
            mem.save_task_checkpoint(
                tid,
                "tool_pending",
                input_snapshot={
                    "task_id": tid,
                    "typ": "chat",
                    "prompt": "search weather",
                    "current_prompt": "search weather",
                    "iteration": 0,
                    "status": "running",
                },
                tool_snapshot={
                    "tool": "search",
                    "identifier": "search:web",
                    "kind": "search",
                    "pending": False,
                },
                result_snapshot={
                    "answer_preview": "sunny",
                    "answer_full": "sunny 20C",
                    "via": "search",
                },
                side_effect_refs=["search:search weather"],
            )
            action = await exe._resume_from_checkpoint(task)
            return action, task

        action, task = asyncio.run(_run())
        self.assertEqual(action, "continue")
        self.assertEqual(task.resume_used_tool_ids, ["search:web"])
        self.assertIn("[Tool-Kontext]", task.resume_tool_context)

    def test_exception_marks_resumable_from_db_checkpoint(self):
        import asyncio
        from executor import get_executor, Task, TaskType, TaskStatus
        from task_checkpoint import CheckpointState

        async def _run():
            exe = get_executor()
            tid = f"cp_exc_{id(self)}"
            task = Task(id=tid, typ=TaskType.CHAT, prompt="boom", beschreibung="boom")
            task.status = TaskStatus.RUNNING
            exe._tasks[tid] = task
            exe._checkpoint(task, CheckpointState.EVALUATING)
            task.checkpoint_state = "resume_completed"

            async def _boom(_task):
                raise RuntimeError("simulated failure")

            with patch.object(exe, "_execute_ai", side_effect=_boom):
                await exe._execute(task)
            return task

        task = asyncio.run(_run())
        self.assertEqual(task.status, TaskStatus.RESUMABLE)
        self.assertIn("simulated failure", task.fehler)

    def test_watchdog_checkpoint_resume_increments_restarts(self):
        from executor import get_executor, Task, TaskType, TaskStatus
        from memory import get_memory
        from task_checkpoint import CheckpointState
        from watchdog import TaskWatchdog

        exe = get_executor()
        wd = TaskWatchdog()
        wd.set_executor(exe)
        tid = f"cp_wd_{id(self)}"
        task = Task(id=tid, typ=TaskType.CHAT, prompt="hang", beschreibung="hang")
        task.status = TaskStatus.RUNNING
        exe._tasks[tid] = task
        get_memory().save_task_checkpoint(
            tid,
            CheckpointState.PLANNING,
            input_snapshot={"task_id": tid, "prompt": "hang", "iteration": 0},
        )
        asyncio.run(wd._handle_hang(task, 120.0))
        self.assertEqual(wd._restarts.get(tid), 1)
        self.assertEqual(task.status, TaskStatus.QUEUED)

    def test_interrupted_chat_task_full_resume_execute_cycle(self):
        import asyncio
        from executor import get_executor, Task, TaskType, TaskStatus, Strategy
        from logic import QualityScore

        async def _run():
            exe = get_executor()
            tid = f"cp_chat_full_{id(self)}"
            task = Task(
                id=tid,
                typ=TaskType.CHAT,
                prompt="Was ist Isaac?",
                beschreibung="unterbrochener CHAT",
                strategy=Strategy(allow_followup=True),
            )
            task.status = TaskStatus.QUEUED
            exe._tasks[tid] = task
            calls = {"ai": 0}

            async def _flaky_ai(current_task):
                calls["ai"] += 1
                if calls["ai"] == 1:
                    raise ConnectionError("relay timeout")
                current_task.antwort = "Isaac ist ein lokaler kognitiver Kernel."
                current_task.provider_used = "mock-provider"
                current_task.score = QualityScore(total=8.5)
                current_task.status = TaskStatus.DONE

            with patch.object(exe, "_execute_ai", side_effect=_flaky_ai):
                await exe._execute(task)

            self.assertEqual(task.status, TaskStatus.RESUMABLE)
            self.assertTrue(exe.resume_task(tid))
            resumed = exe.get_task(tid)
            self.assertEqual(resumed.status, TaskStatus.QUEUED)
            self.assertEqual(resumed.resume_strategy, "from_checkpoint")

            with patch.object(exe, "_execute_ai", side_effect=_flaky_ai):
                await exe._execute(resumed)

            self.assertEqual(resumed.status, TaskStatus.DONE)
            self.assertEqual(calls["ai"], 2)
            self.assertIn("Kernel", resumed.antwort)
            return resumed

        asyncio.run(_run())

    def test_regelwerk_open_questions_payload_for_dashboard(self):
        from regelwerk import Frage, get_regelwerk
        from monitor_server import MonitorServer

        rw = get_regelwerk()
        qid = f"F_dash_{id(self)}"
        rw._fragen.append(
            Frage(
                id=qid,
                text="Was meinst du mit Dashboard?",
                kontext="dashboard regression",
                prioritaet=0.66,
            )
        )
        payload = rw.open_questions_dict()
        self.assertTrue(any(item.get("id") == qid for item in payload))

        state = MonitorServer()._build_state()
        self.assertIn("open_questions", state)
        self.assertTrue(any(item.get("id") == qid for item in state["open_questions"]))
        self.assertIn("regelwerk", state)
        self.assertGreaterEqual(int(state["regelwerk"].get("offene_fragen", 0)), 1)

    def test_dashboard_task_resume_localhost_only(self):
        from monitor_server import is_localhost_request

        self.assertTrue(is_localhost_request("127.0.0.1"))
        self.assertTrue(is_localhost_request("::1"))
        self.assertTrue(is_localhost_request("localhost"))
        self.assertFalse(is_localhost_request("172.20.10.7"))
        self.assertFalse(is_localhost_request("10.0.0.5"))

    def test_checkpoint_retention_trims_per_task(self):
        from memory import get_memory
        from task_checkpoint import CHECKPOINT_MAX_PER_TASK

        mem = get_memory()
        tid = f"cp_retention_{id(self)}"
        for idx in range(CHECKPOINT_MAX_PER_TASK + 5):
            mem.save_task_checkpoint(
                tid,
                "planning",
                input_snapshot={"step": idx},
            )
        rows = mem.list_checkpoints(tid, limit=100)
        self.assertLessEqual(len(rows), CHECKPOINT_MAX_PER_TASK)
        self.assertEqual(int(rows[0]["checkpoint_id"]), max(int(r["checkpoint_id"]) for r in rows))
        latest = mem.get_latest_checkpoint(tid)
        self.assertIsNotNone(latest)
        self.assertEqual(latest["checkpoint_id"], rows[0]["checkpoint_id"])

    def test_checkpoint_age_cleanup_removes_old_terminal_states(self):
        from memory import get_memory, _conn
        from task_checkpoint import CheckpointState

        mem = get_memory()
        tid = f"cp_age_{id(self)}"
        with _conn() as con:
            con.execute(
                "INSERT INTO task_checkpoints "
                "(task_id, ts, state_name, input_snapshot, tool_snapshot, "
                "result_snapshot, memory_refs, side_effect_refs) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (
                    tid,
                    "2020-01-01 00:00:00",
                    CheckpointState.DONE,
                    "{}",
                    "{}",
                    "{}",
                    "[]",
                    "[]",
                ),
            )
            con.execute(
                "INSERT INTO task_checkpoints "
                "(task_id, ts, state_name, input_snapshot, tool_snapshot, "
                "result_snapshot, memory_refs, side_effect_refs) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (
                    tid,
                    "2026-07-11 00:00:00",
                    CheckpointState.PLANNING,
                    '{"keep": true}',
                    "{}",
                    "{}",
                    "[]",
                    "[]",
                ),
            )
        summary = mem.cleanup_task_checkpoints(task_id=tid, max_age_days=30)
        after = mem.list_checkpoints(tid, limit=20)
        self.assertGreaterEqual(summary.get("removed", 0), 1)
        self.assertEqual(len(after), 1)
        self.assertEqual(after[0].get("state_name"), CheckpointState.PLANNING)

    def test_checkpoint_cleanup_stats(self):
        from memory import get_memory

        mem = get_memory()
        tid = f"cp_stats_{id(self)}"
        mem.save_task_checkpoint(tid, "planning")
        stats = mem.checkpoint_stats()
        self.assertGreaterEqual(int(stats.get("total", 0)), 1)
        self.assertGreaterEqual(int(stats.get("tasks", 0)), 1)


class TestProcedureMemory(unittest.TestCase):
    def test_procedure_capture_success_and_failure_downgrade(self):
        from procedure_memory import record_task_outcome, build_signature
        from memory import get_memory

        unique = f"procedure_test_{id(self)}"
        mem = get_memory()

        task = Task(
            id=f"proc-{unique}",
            typ=TaskType.SEARCH,
            prompt=f"Suche Wetter Berlin {unique}",
            beschreibung=f"Suche Wetter Berlin {unique}",
        )
        task.used_tools = [{"name": "search_web", "kind": "search"}]
        task.status = TaskStatus.DONE
        task.score = QualityScore(total=7.5)
        task.decision_trace = DecisionTrace()
        task.decision_trace.add(TracePhase.EXECUTION, "search_web ok")

        result = record_task_outcome(task)
        self.assertIsNotNone(result)
        self.assertGreater(result["reliability"], 0.5)
        self.assertFalse(result["degraded"])

        sig = build_signature(task)
        stored = mem.get_procedure_by_signature(sig)
        self.assertIsNotNone(stored)
        rel_after_success = float(stored["reliability"])

        task.status = TaskStatus.FAILED
        task.score = QualityScore(total=2.0)
        fail_result = record_task_outcome(task)
        self.assertIsNotNone(fail_result)
        self.assertLess(fail_result["reliability"], rel_after_success)
        self.assertTrue(fail_result["degraded"])

    def test_retrieval_context_exposes_procedures(self):
        from memory import get_memory

        mem = get_memory()
        ctx = mem.build_retrieval_context("Wetter Berlin Suche procedure")
        data = ctx.as_dict()
        self.assertIn("relevant_procedures", data)
        self.assertIsInstance(data["relevant_procedures"], list)
        formatted = mem.format_retrieval_context(ctx)
        if data["relevant_procedures"]:
            self.assertIn("[relevant_procedures]", formatted)


class TestPhase4Connect(unittest.TestCase):
    def test_regelwerk_open_question_surfaces_in_retrieval(self):
        from regelwerk import Frage, get_regelwerk
        from memory import get_memory

        rw = get_regelwerk()
        qid = f"F_ret_{id(self)}"
        rw._fragen.append(
            Frage(
                id=qid,
                text="Was meinst du genau mit 'Status'? Für zukünftige Anfragen wichtig.",
                kontext="retrieval test",
                prioritaet=0.8,
            )
        )
        ctx = get_memory().build_retrieval_context(
            user_input="Wie ist der System Status?",
            intent="chat",
            interaction_class="NORMAL_CHAT",
        )
        questions = ctx.as_dict().get("open_questions") or []
        self.assertTrue(any("Status" in q for q in questions))

    def test_kernel_standard_task_records_routing_trace(self):
        class FakeRetrievalContext:
            def as_dict(self):
                return {
                    "relevant_facts": [],
                    "relevant_procedures": [],
                    "open_questions": [],
                }

        class FakeMemory:
            def build_retrieval_context(self, *args, **kwargs):
                return FakeRetrievalContext()

            def format_retrieval_context(self, retrieval_ctx):
                return ""

            def add_conversation(self, *args, **kwargs):
                return None

            def save_task_result(self, *args, **kwargs):
                return None

        captured: dict = {}

        class FakeExecutor:
            def create_task(self, **kwargs):
                task_obj = SimpleNamespace(
                    typ=kwargs["typ"],
                    prompt=kwargs["prompt"],
                    antwort="ok",
                    fehler="",
                    score=SimpleNamespace(total=8.0),
                    provider_used="test",
                    iteration=0,
                    id="trace-task",
                    decision_trace=DecisionTrace(),
                )
                captured["task"] = task_obj
                return task_obj

            async def submit_and_wait(self, task, timeout=180.0):
                return task

        from neural_core import get_neural_cortex
        from learning_engine import get_learning_engine

        kernel = object.__new__(IsaacKernel)
        kernel.memory = FakeMemory()
        kernel.executor = FakeExecutor()
        kernel.meaning = SimpleNamespace(record_impact=lambda *args, **kwargs: None)
        kernel.values = SimpleNamespace(update=lambda *args, **kwargs: None)
        kernel.neural = get_neural_cortex()
        kernel.learning = get_learning_engine()
        kernel._build_system = lambda *args, **kwargs: "system"
        kernel._provider_hint = lambda user_input: None
        kernel._retrieve_relevant_context = lambda **kwargs: FakeRetrievalContext().as_dict()
        classification = ClassificationResult(
            interaction_class=InteractionClass.NORMAL_CHAT,
            normalized_text="was ist 2 2",
            has_question=True,
            word_count=3,
        )

        asyncio.run(
            kernel._standard_task(
                user_input="Was ist 2+2?",
                intent=Intent.CHAT,
                sudo_aktiv=False,
                emp=SimpleNamespace(),
                wissen_kontext="",
                interaction_class=InteractionClass.NORMAL_CHAT,
                classification=classification,
            )
        )
        events = [e.event for e in captured["task"].decision_trace.entries]
        phases = [e.phase for e in captured["task"].decision_trace.entries]
        self.assertIn("classified", events)
        self.assertIn("retrieved", events)
        self.assertIn("strategy_selected", events)
        self.assertIn(TracePhase.CLASSIFICATION, phases)
        self.assertIn(TracePhase.RETRIEVAL, phases)
        self.assertIn(TracePhase.STRATEGY, phases)

    def test_bug_31_constitution_block_audits_routing_trace(self):
        from audit import AUDIT_PATH
        from decision_trace import TracePhase

        kernel = object.__new__(IsaacKernel)
        before = AUDIT_PATH.stat().st_size if AUDIT_PATH.exists() else 0
        kernel._audit_constitution_block(
            Intent.CODE,
            {
                "allowed": False,
                "blocked_by": ["constitution_not_self_editable"],
                "verdict": {"action": "execute_code", "blocked_by": ["constitution_not_self_editable"]},
            },
        )
        self.assertTrue(AUDIT_PATH.exists())
        self.assertGreater(AUDIT_PATH.stat().st_size, before)
        last_line = AUDIT_PATH.read_text(encoding="utf-8").strip().splitlines()[-1]
        entry = json.loads(last_line)
        self.assertEqual(entry["typ"], "decision_trace")
        self.assertEqual(entry["outcome"], "blocked")
        self.assertEqual(entry["entries"][0]["phase"], TracePhase.GOVERNANCE.value)
        self.assertEqual(entry["entries"][0]["event"], "constitution_blocked")

    def test_procedure_hints_boost_matching_tool(self):
        from tool_runtime import _procedure_hints_for_prompt

        hints = _procedure_hints_for_prompt("Suche Wetter Berlin eindeutig")
        self.assertIsInstance(hints, dict)


if __name__ == '__main__':
    unittest.main()
