// What the `pi` driver loads with `-e`, beside whatever the user's own setup loads.

import { readFileSync } from "node:fs";
import { streamSimple } from "@earendil-works/pi-ai";
import { compact } from "@earendil-works/pi-coding-agent";

const { namespace, server, environment, provider, compaction, instructions } = JSON.parse(
  process.env.PLATOON_HARNESS_PI,
);
const READS = new Set(["read", "grep", "find", "ls"]);
const CONNECTING_MS = 10_000;
const LOOKING_MS = 25;

export default function (pi) {
  if (server) pi.registerMcpServer(namespace, server);
  if (environment) pi.registerMcpServer(...environment);
  if (provider) pi.registerProvider(...provider);

  // Pi connects MCP servers once its session starts, after this extension's start, declares their tools once they
  // connect, and says nothing when that is. So the tools it declares are said, as a status the driver waits for, once
  // ours are among them, and the environment's, or after as long as pi's own first prompt waits for a server.
  if (server) {
    pi.on("session_start", (_event, ctx) => {
      const connected = () => {
        const names = pi.getAllTools().map(({ name }) => name);
        return names.some(ours) && (environment === undefined || names.some(environments));
      };
      void (async () => {
        for (let waited = 0; !connected() && waited < CONNECTING_MS; waited += LOOKING_MS) {
          await new Promise((resolve) => setTimeout(resolve, LOOKING_MS));
        }
        ctx.ui.setStatus("platoon_harness.tools", JSON.stringify(pi.getActiveTools()));
      })();
    });
  }

  // A section of its own: `--append-system-prompt` would take the place of the user's `APPEND_SYSTEM.md`.
  if (instructions) {
    const words = readFileSync(instructions, "utf8");
    pi.on("before_agent_start", ({ systemPromptOptions }) => {
      systemPromptOptions.sections.platoon_harness = words;
    });
  }

  const ours = (tool) => tool.startsWith(`mcp__${namespace}__`);
  const environments = (tool) => environment !== undefined && tool.startsWith(`mcp__${environment[0]}__`);
  const asks = (tool) => {
    if (ours(tool) || environments(tool) || READS.has(tool)) return false;
    return !pi.getAllTools().find(({ name }) => name === tool)?.annotations?.readOnlyHint;
  };

  // Pi's MCP client sends no id with a call, so a call of ours carries pi's own among its arguments, as `_meta`, which
  // the shim moves to where MCP keeps it. Pi has checked the arguments by now, and a tool is handed a copy of them.
  // The title is the tool call's id, which is how the driver ties a verdict to what came of it.
  pi.on("tool_call", async ({ toolName, toolCallId, input }, ctx) => {
    if (ours(toolName)) input._meta = { "pi/toolCallId": toolCallId };
    if (!asks(toolName)) return undefined;
    const said = `${toolName} ${JSON.stringify(input)}`;
    if (await ctx.ui.confirm(toolCallId, said, { signal: ctx.signal })) return undefined;
    return { block: true, reason: "The runtime denied this." };
  });

  // A sealed launch compacts with pi's own `compact`, each of whose one or two calls carries the gateway's compaction
  // headers and keeps the id the model gave it, which the details pi keeps of the compaction hand the driver. One that
  // fails is cancelled, as pi would otherwise compact again by itself, with neither the headers nor the ids.
  if (compaction) {
    pi.on("session_before_compact", async (event, ctx) => {
      const calls = [];
      const keeping = async (model, context, options) => {
        const stream = streamSimple(model, context, options);
        return {
          result: async () => {
            const message = await stream.result();
            calls.push(message.responseId ?? null);
            return message;
          },
        };
      };
      try {
        const key = process.env[compaction.bearer];
        const { preparation, customInstructions, signal } = event;
        const made = await compact(
          preparation, ctx.model, key, compaction.headers, customInstructions, signal, ctx.thinkingLevel, keeping,
        );
        return { compaction: { ...made, details: { ...made.details, platoon_harness: { calls } } } };
      } catch {
        return { cancel: true };
      }
    });
  }
}
