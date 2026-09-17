import json
import os
import sys

if len(sys.argv) > 1 and sys.argv[1] == "--version":
    print("codex-cli 0.150.0-enterprise (Zhixing Runtime Harness)")
    sys.exit(0)

thread_id = "thread-root"
turn_number = 0
for raw in sys.stdin:
    raw = raw.strip()
    if not raw:
        continue
    try:
        message = json.loads(raw)
    except Exception:
        continue
    method = message.get("method")
    request_id = message.get("id")
    if method == "initialize":
        print(json.dumps({"id": request_id, "result": {"platformFamily": "windows", "version": "0.150.0"}}), flush=True)
    elif method == "initialized":
        continue
    elif method == "thread/start":
        print(json.dumps({"id": request_id, "result": {"thread": {"id": thread_id, "sessionId": "session-root"}}}), flush=True)
    elif method == "thread/resume":
        tid = message.get("params", {}).get("threadId", thread_id)
        print(json.dumps({"id": request_id, "result": {"thread": {"id": tid, "sessionId": "session-root"}}}), flush=True)
    elif method == "turn/start":
        turn_number += 1
        turn_id = f"turn-{turn_number}"
        print(json.dumps({"id": request_id, "result": {"turn": {"id": turn_id, "status": "inProgress"}}}), flush=True)
        print(json.dumps({"method": "turn/started", "params": {"turn": {"id": turn_id, "status": "inProgress"}}}), flush=True)
        print(json.dumps({"method": "item/agentMessage/delta", "params": {"delta": "经营正常"}}), flush=True)
        print(json.dumps({"method": "item/completed", "params": {"item": {"id": "msg-1", "type": "agentMessage", "text": "经营分析与受控决策完成", "phase": "final_answer"}}}), flush=True)
        print(json.dumps({"method": "turn/completed", "params": {"turn": {"id": turn_id, "status": "completed", "items": []}}}), flush=True)
    elif method == "turn/interrupt":
        print(json.dumps({"id": request_id, "result": {}}), flush=True)
        print(json.dumps({"method": "turn/completed", "params": {"turn": {"id": turn_id, "status": "interrupted", "items": []}}}), flush=True)
    elif request_id is not None:
        print(json.dumps({"id": request_id, "result": {}}), flush=True)
