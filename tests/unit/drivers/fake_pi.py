"""A stand-in for `pi --mode rpc`: it says what a script tells it, in the real frames, and writes down what it heard."""

import json
import os
import signal
import sys
import time
from pathlib import Path

SCRIPT = Path(sys.argv[1])
script = json.loads(SCRIPT.read_text())
arguments = sys.argv[2:]
entries = list(script.get("entries", []))  # What pi has written down, as it does each user message once it ends.


def say(text: str) -> None:
    sys.stdout.write(text + "\n")
    sys.stdout.flush()


def play(frames: list) -> None:
    for frame in frames:
        say(frame if isinstance(frame, str) else json.dumps(frame))
        if isinstance(frame, dict) and frame.get("type") == "message_end" and frame["message"]["role"] == "user":
            entries.append({"type": "message", "id": f"entry-{len(entries) + 1}", "message": frame["message"]})


def reply(id: str, command: str, data: object = None, error: str | None = None) -> None:
    frame = {"id": id, "type": "response", "command": command, "success": error is None}
    say(json.dumps({**frame, "data": data} if error is None else {**frame, "error": error}))


def since(after: str | None) -> list:
    """The entries after one, or all of them."""
    ids = [entry.get("id") for entry in entries if isinstance(entry, dict)]
    return entries[ids.index(after) + 1 :] if after in ids else entries


def answer(id: str, command: str, frame: dict) -> None:
    refused = script.get("refuses", {})
    if command in refused:
        reply(id, command, error=refused[command])
        return
    model = {"id": script.get("model", "fake-model"), "provider": script.get("provider", "fake")}
    data = {
        "get_state": {"model": model, "thinkingLevel": script.get("thinking", "off"), "sessionId": "ignored"},
        "get_available_models": {"models": script.get("available", [model])},
        "get_entries": {"entries": since(frame.get("since")), "leafId": script.get("leaf")},
        "clear_queue": {"steering": [], "followUp": []},
    }.get(command)
    reply(id, command, data)


if arguments[:1] == ["--version"]:
    say(script.get("version", "9.9.9"))
    sys.exit(0)
if arguments[:2] == ["auth", "check"]:
    time.sleep(script.get("status_seconds", 0))
    SCRIPT.with_suffix(".status").write_text(json.dumps(arguments))
    say(script.get("status", ""))
    sys.exit(script.get("status_code", 0))

launch = {"argv": arguments, "env": dict(os.environ), "pid": os.getpid()}
SCRIPT.with_suffix(".launch").write_text(json.dumps(launch))
if "exit_at_once" in script:
    print(script.get("stderr", ""), file=sys.stderr)
    sys.exit(script["exit_at_once"])
if script.get("ignores_term"):
    signal.signal(signal.SIGTERM, signal.SIG_IGN)

turns = iter(script.get("turns", ()))
heard = SCRIPT.with_suffix(".heard").open("a", buffering=1)
for line in sys.stdin:
    heard.write(line)
    frame = json.loads(line)
    match frame:
        case {"type": "prompt", "id": id}:
            if "prompt" in script.get("refuses", {}):
                reply(id, "prompt", error=script["refuses"]["prompt"])
            else:
                reply(id, "prompt", {"disposition": script.get("disposition", "started")})
                play(next(turns, ()))
        case {"type": "extension_ui_response"}:
            play(script.get("on_answer", ()))
        case {"type": command, "id": id}:
            if command == script.get("deaf_to"):
                time.sleep(600)
            if command == script.get("gone_at"):
                sys.exit(1)
            answer(id, command, frame)
            play(script.get(f"after_{command}", ()))
if script.get("outlives_stdin"):
    while True:
        time.sleep(1)
