"""A stand-in for `codex app-server`: it says what a script tells it, in real frames, and writes down what it heard."""

import json
import os
import sys
import time
from pathlib import Path

SCRIPT = Path(sys.argv[1])
script = json.loads(SCRIPT.read_text())
arguments = sys.argv[2:]
THREAD = script.get("thread", "thread-1")


def say(frame: object) -> None:
    sys.stdout.write((frame if isinstance(frame, str) else json.dumps(frame)) + "\n")
    sys.stdout.flush()


def play(frames: list, turn: str = "") -> None:
    for frame in frames:
        text = frame if isinstance(frame, str) else json.dumps(frame)
        say(text.replace("$thread", THREAD).replace("$turn", turn))


def answer(id: int, method: str, params: dict) -> None:
    if method == script.get("deaf_after"):
        time.sleep(600)
    refusal = script.get("refused", {}).get(method) or script.get("refused_once", {}).pop(method, None)
    if refusal is not None:
        play(script.get("before_refusal", ()), params.get("turnId", ""))
        say({"id": id, "error": {"code": -32600, "message": refusal}})
        return
    match method:
        case "initialize":
            say({"id": id, "result": {"userAgent": "fake", "codexHome": "/nowhere"}})
        case "config/read":
            say({"id": id, "result": {"config": script.get("config", {})}})
        case "thread/start" | "thread/resume":
            thread = {"id": THREAD, "cliVersion": script.get("version", "9.9.9")}
            effort = script.get("effort", params.get("config", {}).get("model_reasoning_effort"))
            model = script.get("model", params.get("model"))
            say({"id": id, "result": {"thread": thread, "model": model, "reasoningEffort": effort}})
            if method == "thread/resume":
                play(script.get("on_resume", ()))
        case "turn/start":
            global turns
            turns += 1
            turn = f"turn-{turns}"
            say({"id": id, "result": {"turn": {"id": turn, "status": "inProgress", "items": []}}})
            played = script.get("turns", ())
            play(played[turns - 1] if turns <= len(played) else (), turn)
        case "turn/interrupt":
            say({"id": id, "result": {}})
            play(script.get("on_interrupt", ()), params["turnId"])
        case "thread/turns/list":
            say({"id": id, "result": {"data": script.get("history", [])}})
        case _:
            say({"id": id, "error": {"code": -32601, "message": f"no {method}"}})


if arguments[:2] == ["login", "status"]:
    time.sleep(script.get("status_seconds", 0))
    sys.stderr.write(script.get("status", ""))
    sys.exit(script.get("status_code", 0))

launch = {"argv": arguments, "env": dict(os.environ), "pid": os.getpid()}
SCRIPT.with_suffix(".launch").write_text(json.dumps(launch))
if "exit_at_once" in script:
    sys.exit(script["exit_at_once"])

turns = 0
heard = SCRIPT.with_suffix(".heard").open("a", buffering=1)
for line in sys.stdin:
    heard.write(line)
    frame = json.loads(line)
    match frame:
        case {"id": id, "method": method}:
            answer(id, method, frame.get("params", {}))
        case {"id": _, "result": _} | {"id": _, "error": _}:
            play(script.get("on_answer", ()), f"turn-{turns}")
sys.exit(script.get("exit_on_eof", 0))
