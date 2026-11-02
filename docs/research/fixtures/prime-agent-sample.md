# Prime Agent sample: no live capture

There is no event capture in this file. Do not treat anything here as recorded
wire traffic, and do not build a replay fixture from it.

## What ran

Prime Agent 0.10.2, Linux x64 release tarball (sha256 prefix `09659961dfde201c`),
extracted to a scratch directory, 2026-11-02:

| Command | Result |
|---|---|
| `prime-agent --version` | Printed `0.10.2` |
| `prime-agent --help` | Printed usage, including `--mode <text\|json\|rpc\|acp\|daemon>` |

## What did not run

The model turn did not run. The harness permission classifier denied the command
before it executed and gave no reason. It was not retried by another route, so
no scripted turn, RPC session or ACP session was started.

The intended command, for whoever approves it:

```text
PRIME_AGENT_CODING_AGENT_DIR=<scratch>/agent PRIME_AGENT_TELEMETRY=0 DO_NOT_TRACK=1 \
PRIME_AGENT_DAEMON_SOCKET=<scratch>/d.sock \
prime-agent --mode json --offline --provider fake --model fake-model \
  --session-dir <scratch>/sessions "TOOLTEST please call the tool" </dev/null
```

with `<scratch>/agent/models.json` defining provider `fake` (`baseUrl` on a local
scripted server, `api: openai-completions`, `apiKey`, `headers`, one model). That
`models.json` shape is taken from the source and is itself unverified live.

## To finish this fixture

1. Approve the run above, or choose the test-only scripted provider
   (`PRIME_AGENT_FAUX_SCRIPT`) that upstream's end-to-end tests use.
2. Capture `--mode json`, then `--mode rpc`, then `--mode acp`.
3. Run `prime-agent shutdown` afterwards if the run started a daemon.
4. Replace this file with a redacted `prime-agent-sample.jsonl`.
