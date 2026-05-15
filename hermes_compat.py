from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from audit import AuditLog
from mcp_registry import MCPRegistry
from security_policy import ConfirmationPolicy, SecurityVerdict


@dataclass(frozen=True)
class ToolInput:
    payload: dict[str, Any]


@dataclass
class ToolResult:
    ok: bool
    output: Any = None
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ExecutionContext:
    caller: str = "hermes"
    level: int = 0
    r_trace: str = ""
    task_id: str = ""


@dataclass(frozen=True)
class PermissionMetadata:
    risk: str = "medium"
    outside_effect: bool = False
    requires_confirmation: bool = False
    timeout: float = 30.0
    allowed_scope: str = "local"

    def as_policy_meta(self) -> dict[str, Any]:
        return {
            "risk": self.risk,
            "outside_effect": self.outside_effect,
            "requires_confirmation": self.requires_confirmation,
            "timeout": self.timeout,
            "allowed_scope": self.allowed_scope,
        }


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    category: str
    input_schema: dict[str, Any]
    permission: PermissionMetadata
    handler: Callable[[ToolInput, ExecutionContext], ToolResult]
    enabled: bool = True


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    tools: tuple[str, ...] = ()
    enabled: bool = True


@dataclass(frozen=True)
class ComputerAction:
    action: str
    params: dict[str, Any] = field(default_factory=dict)
    permission: PermissionMetadata = field(default_factory=PermissionMetadata)


@dataclass(frozen=True)
class BrowserAction(ComputerAction):
    url: str = ""


class SkillRegistry:
    def __init__(self):
        self._skills: dict[str, Skill] = {}

    def register(self, skill: Skill):
        self._skills[skill.name] = skill

    def get(self, name: str) -> Optional[Skill]:
        return self._skills.get(name)


class HermesToolSchemaMapper:
    @staticmethod
    def normalize(raw: dict[str, Any]) -> dict[str, Any]:
        return {
            "name": raw.get("name", "").strip(),
            "description": raw.get("description", "").strip(),
            "category": (raw.get("category") or "general").strip(),
            "input_schema": dict(raw.get("input_schema") or raw.get("inputSchema") or {"type": "object"}),
            "risk": (raw.get("risk") or "medium").lower(),
            "outside_effect": bool(raw.get("outside_effect", False)),
            "requires_confirmation": bool(raw.get("requires_confirmation", False)),
            "timeout": float(raw.get("timeout", 30.0)),
            "enabled": bool(raw.get("enabled", True)),
        }


class HermesToolAdapter:
    def __init__(self, schema: dict[str, Any], handler: Callable[[dict[str, Any]], Any]):
        self.schema = HermesToolSchemaMapper.normalize(schema)
        self._handler = handler

    def to_tool(self) -> Tool:
        permission = PermissionMetadata(
            risk=self.schema["risk"],
            outside_effect=self.schema["outside_effect"],
            requires_confirmation=self.schema["requires_confirmation"],
            timeout=self.schema["timeout"],
        )

        def _wrapped(tool_input: ToolInput, _ctx: ExecutionContext) -> ToolResult:
            try:
                return ToolResult(ok=True, output=self._handler(tool_input.payload), metadata={"adapter": "hermes"})
            except Exception as e:
                return ToolResult(ok=False, error=str(e), metadata={"adapter": "hermes"})

        return Tool(
            name=self.schema["name"],
            description=self.schema["description"],
            category=self.schema["category"],
            input_schema=self.schema["input_schema"],
            permission=permission,
            handler=_wrapped,
            enabled=self.schema["enabled"],
        )


class HermesSkillAdapter:
    def __init__(self, raw_skill: dict[str, Any]):
        self.raw_skill = raw_skill

    def to_skill(self) -> Skill:
        return Skill(
            name=self.raw_skill.get("name", "unnamed_skill"),
            description=self.raw_skill.get("description", ""),
            tools=tuple(self.raw_skill.get("tools", [])),
            enabled=bool(self.raw_skill.get("enabled", True)),
        )


class HermesComputerUseAdapter:
    ALLOWED_ACTIONS = {
        "screenshot", "browser_navigate", "browser_click", "browser_type", "browser_extract",
        "file_read", "file_write", "shell_command", "wait", "observe",
    }
    BLOCKED_ACTIONS = {"file_delete", "credential_access", "privilege_escalation", "background_persist"}

    def validate(self, action: ComputerAction) -> ToolResult:
        if action.action in self.BLOCKED_ACTIONS:
            return ToolResult(ok=False, error=f"Blocked action: {action.action}")
        if action.action not in self.ALLOWED_ACTIONS:
            return ToolResult(ok=False, error=f"Unknown action: {action.action}")
        if action.permission.timeout <= 0:
            return ToolResult(ok=False, error="Timeout must be positive")
        if action.permission.allowed_scope not in {"local", "workspace", "browser"}:
            return ToolResult(ok=False, error=f"Unsupported scope: {action.permission.allowed_scope}")
        if action.action == "shell_command":
            cmd = str(action.params.get("command", "")).strip()
            if not cmd:
                return ToolResult(ok=False, error="shell_command requires command")
            blocked_fragments = ("sudo ", "rm -rf", "chmod 777", "curl ", "wget ")
            if any(fragment in cmd for fragment in blocked_fragments):
                return ToolResult(ok=False, error="shell_command violates safety policy")
        return ToolResult(ok=True, output={"validated": True, "action": action.action, "scope": action.permission.allowed_scope})


class HermesBrowserAdapter:
    def run(self, action: BrowserAction, dry_run: bool = True) -> ToolResult:
        if dry_run:
            return ToolResult(ok=True, output={"dry_run": True, "action": action.action, "url": action.url})
        return ToolResult(ok=False, error="Live browser execution disabled in adapter")


class HermesCompatibilityAdapter:
    def __init__(self, confirmation_policy: ConfirmationPolicy, audit_log=AuditLog):
        self.confirmation_policy = confirmation_policy
        self.audit_log = audit_log
        self.skill_registry = SkillRegistry()
        self.tools: dict[str, Tool] = {}

    def register_skill(self, raw_skill: dict[str, Any]):
        self.skill_registry.register(HermesSkillAdapter(raw_skill).to_skill())

    def register_tool(self, schema: dict[str, Any], handler: Callable[[dict[str, Any]], Any]):
        tool = HermesToolAdapter(schema, handler).to_tool()
        self.tools[tool.name] = tool

    def mirror_tool_to_mcp(self, mcp_registry: MCPRegistry, tool_name: str):
        tool = self.tools[tool_name]
        mcp_registry.register_tool(
            tool.name,
            {"description": tool.description, "inputSchema": tool.input_schema, "category": tool.category},
            handler=lambda **kwargs: self.execute_tool(tool.name, kwargs, ExecutionContext(caller="mcp")).output,
        )

    def _permission_check(self, tool: Tool, ctx: ExecutionContext) -> SecurityVerdict:
        meta = tool.permission.as_policy_meta()
        return self.confirmation_policy.analyze(tool.name, ctx, meta)

    def execute_tool(self, tool_name: str, payload: dict[str, Any], ctx: ExecutionContext) -> ToolResult:
        tool = self.tools.get(tool_name)
        if not tool or not tool.enabled:
            return ToolResult(ok=False, error=f"Tool unavailable: {tool_name}")

        verdict = self._permission_check(tool, ctx)
        if not verdict.allowed:
            self.audit_log.action(ctx.caller, "tool_blocked", f"{tool_name} | {verdict.reason}", level=ctx.level, erfolg=False)
            return ToolResult(ok=False, error=verdict.reason, metadata={"queue_id": verdict.queue_id, "risk": verdict.risk})

        self.audit_log.action(ctx.caller, "tool_execute", tool_name, level=ctx.level, erfolg=True)
        result = tool.handler(ToolInput(payload), ctx)
        self.audit_log.task(ctx.task_id or "hermes-task", "tool_result", detail=tool_name, score=1.0 if result.ok else 0.0)
        return result

    def execute_flow(self, user_task: str, tool_name: str, payload: dict[str, Any], ctx: ExecutionContext, memory_writeback: Optional[Callable[[str, ToolResult], None]] = None) -> ToolResult:
        self.audit_log.action(ctx.caller, "intent_detected", user_task[:120], level=ctx.level, erfolg=True)
        result = self.execute_tool(tool_name, payload, ctx)
        if result.ok and memory_writeback:
            memory_writeback(user_task, result)
            self.audit_log.memory_write("HermesCompatibilityAdapter", "tool_result", tool_name)
        return result
