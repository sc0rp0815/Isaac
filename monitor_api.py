from __future__ import annotations
from flask import Blueprint, jsonify
from audit import AuditLog
from executor import get_executor
from relay import get_relay
from monitor_server import get_monitor
from tool_registry import get_tool_registry
monitor_api = Blueprint('monitor_api', __name__, url_prefix='/api/monitor')
@monitor_api.get('/state')
def state():
    mon = get_monitor(); exe = get_executor(); relay = get_relay()
    return jsonify({'ok': True, 'state': mon._build_state() if hasattr(mon, '_build_state') else {}, 'tasks': exe.all_tasks(50), 'providers': relay.provider_status(), 'tools': get_tool_registry().list_tools(), 'audit': AuditLog.recent(20)})
