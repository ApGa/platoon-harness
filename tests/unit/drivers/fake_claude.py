"""A stand-in for `claude -p`: it says what a script tells it, in the real frames, and writes down what it heard."""

import json
import os
import sys
import time
from pathlib import Path

SCRIPT = Path(sys.argv[1])
script = json.loads(SCRIPT.read_text())
arguments = sys.argv[2:]


def say(text: str) -> None:
    sys.stdout.write(text + "\n")
    sys.stdout.flush()


def play(frames: list, input: str = "") -> None:
    for frame in frames:
        say(frame if isinstance(frame, str) else json.dumps(frame).replace("$input", input))


def control(id: str, subtype: str) -> None:
    answers = {
        "initialize": {"claude_code_version": script.get("version", "9.9.9"), "account": {"email": "someone"}},
        "get_settings": {"applied": script.get("applied", {"model": "fake-model", "effort": "high"})},
        "mcp_status": {"mcpServers": script.get("servers", [])},
        "interrupt": {"still_queued": []},
    }
    if subtype == script.get("deaf_after"):
        time.sleep(600)
    if subtype == "interrupt":
        for input in inputs[script.get("queued_from", len(inputs)) :]:
            say(json.dumps({"type": "command_lifecycle", "state": "cancelled", "command_uuid": input}))
    response = {"subtype": "success", "request_id": id, "response": answers.get(subtype)}
    say(json.dumps({"type": "control_response", "response": response}))
    if subtype == "interrupt":
        play(script.get("on_interrupt", ()))


if arguments[:2] == ["auth", "status"]:
    time.sleep(script.get("status_seconds", 0))
    say(script.get("status", ""))
    sys.exit(script.get("status_code", 0))

launch = {"argv": arguments, "env": dict(os.environ), "pid": os.getpid()}
SCRIPT.with_suffix(".launch").write_text(json.dumps(launch))
if "exit_at_once" in script:
    play(script.get("said_at_once", ()))
    sys.exit(script["exit_at_once"])

inputs = []
turns = iter(script.get("turns", ()))
heard = SCRIPT.with_suffix(".heard").open("a", buffering=1)
for line in sys.stdin:
    heard.write(line)
    frame = json.loads(line)
    match frame:
        case {"type": "control_request", "request_id": id, "request": {"subtype": subtype}}:
            control(id, subtype)
        case {"type": "user", "uuid": id}:
            if script.get("deaf_after") == "user":
                time.sleep(600)
            inputs.append(id)
            say(json.dumps({"type": "command_lifecycle", "state": "queued", "command_uuid": id}))
            play(next(turns, ()), id)
        case {"type": "control_response"}:
            play(script.get("on_answer", ()))
sys.exit(script.get("exit_on_eof", 0))
