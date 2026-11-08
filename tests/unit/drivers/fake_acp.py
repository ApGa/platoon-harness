"""A stand-in for an ACP agent: it says what a script tells it, in real frames, and writes down what it heard.

A turn is a list of steps, one turn a prompt: `say` a frame or a line, `ask` a permission request and wait for its
answer, or `wait` until the prompt is cancelled. `$session` in a frame is the session's id.
"""

import json
import sys
from pathlib import Path

script = json.loads(Path(sys.argv[1]).read_text())
heard = Path(sys.argv[2]).open("a")  # noqa: SIM115  Open for as long as the agent runs.
SESSION = script.get("session", "s-1")
CAPABILITIES = {"loadSession": False, "mcpCapabilities": {"http": True}, "sessionCapabilities": {"resume": {}}}
options = script.get("options", [])
turns = iter(script.get("turns", ()))
asked = 0
cancelled = False


def say(frame: object) -> None:
    text = frame if isinstance(frame, str) else json.dumps(frame)
    sys.stdout.write(text.replace("$session", SESSION) + "\n")
    sys.stdout.flush()


def hear() -> dict:
    """The next frame, written down. At the end of stdin the agent ends."""
    global cancelled
    line = sys.stdin.readline()
    if not line:
        sys.exit(0)
    heard.write(line)
    heard.flush()
    frame = json.loads(line)
    cancelled |= frame.get("method") == "session/cancel"
    return frame


def ask(params: dict) -> None:
    global asked
    asked += 1
    id = f"ask-{asked}"
    say({"jsonrpc": "2.0", "id": id, "method": "session/request_permission", "params": params})
    while True:
        frame = hear()
        if frame.get("id") == id and "method" not in frame:
            return


def play(id: object) -> None:
    global cancelled
    for step in next(turns, ()):
        if "say" in step:
            say(step["say"])
        elif "ask" in step:
            ask(step["ask"])
        elif "wait" in step:
            while not cancelled:
                hear()
    say({"jsonrpc": "2.0", "id": id, "result": {"stopReason": "cancelled" if cancelled else "end_turn"}})
    cancelled = False


def answer(id: object, method: str, params: dict) -> None:
    match method:
        case "initialize":
            agent = {"name": "fake", "version": "9.9.9"}
            result = {"protocolVersion": script.get("protocol", params["protocolVersion"]), "agentInfo": agent}
            say(
                {
                    "jsonrpc": "2.0",
                    "id": id,
                    "result": {**result, "agentCapabilities": script.get("agent", CAPABILITIES)},
                }
            )
        case "session/new":
            say({"jsonrpc": "2.0", "id": id, "result": {"sessionId": SESSION, "configOptions": options}})
        case "session/resume":
            say({"jsonrpc": "2.0", "id": id, "result": {"configOptions": options}})
        case "session/set_config_option":
            for option in options:
                if option["id"] == params["configId"]:
                    option["currentValue"] = params["value"]
            say({"jsonrpc": "2.0", "id": id, "result": {"configOptions": options}})
        case "session/prompt":
            play(id)
        case _:
            say({"jsonrpc": "2.0", "id": id, "error": {"code": -32601, "message": f"no method {method}"}})


while True:
    frame = hear()
    if "method" in frame and "id" in frame:
        answer(frame["id"], frame["method"], frame.get("params") or {})
