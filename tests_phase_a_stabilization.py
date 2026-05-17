import asyncio
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from executor import Executor, Strategy, Task, TaskType
from decision_trace import TracePhase
from isaac_core import IsaacKernel, Intent, detect_intent
from tool_policy import ToolDecisionReason
from tool_runtime import select_live_tool_for_task
from low_complexity import (
    ClassificationResult,
    InteractionClass,
    classify_interaction_result,
    is_lightweight_local_class,
)


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
                )

            async def submit_and_wait(self, task, timeout=180.0):
                return task

        kernel = object.__new__(IsaacKernel)
        kernel.memory = FakeMemory()
        kernel.executor = FakeExecutor()
        kernel.meaning = SimpleNamespace(record_impact=lambda *args, **kwargs: None)
        kernel.values = SimpleNamespace(update=lambda *args, **kwargs: None)
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

    def test_bug_10_kernel_parses_structured_browser_flow(self):
        parsed = self.kernel._parse_browser_request(
            "browser: openrouter | https://openrouter.ai/settings/keys | click Settings; wait 1; extract #token -> token"
        )
        self.assertEqual(parsed["instance_id"], "openrouter")
        self.assertEqual(parsed["url"], "https://openrouter.ai/settings/keys")
        self.assertEqual(parsed["actions"][0]["action"], "click")
        self.assertEqual(parsed["actions"][1]["action"], "wait")
        self.assertEqual(parsed["actions"][2]["action"], "extract_text")


    def test_bug_11_process_short_circuits_greeting_without_runtime_dependencies(self):
        kernel = object.__new__(IsaacKernel)
        result = asyncio.run(kernel.process("Hallo Isaac"))
        self.assertEqual(result, "Hallo. Ich bin da.")

    def test_bug_12_process_short_circuits_ack_without_runtime_dependencies(self):
        kernel = object.__new__(IsaacKernel)
        result = asyncio.run(kernel.process("Danke"))
        self.assertEqual(result, "Gern. Ich bin da.")

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



if __name__ == '__main__':
    unittest.main()
