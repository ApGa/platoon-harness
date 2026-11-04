// What the `pi` driver loads with `-e`, beside whatever the user's own setup loads.

import { readFileSync } from "node:fs";

const { namespace, server, provider, instructions } = JSON.parse(process.env.PLATOON_HARNESS_PI);
const READS = new Set(["read", "grep", "find", "ls"]);

export default function (pi) {
  if (server) pi.registerMcpServer(namespace, server);
  if (provider) pi.registerProvider(...provider);

  // A section of its own: `--append-system-prompt` would take the place of the user's `APPEND_SYSTEM.md`.
  if (instructions) {
    const words = readFileSync(instructions, "utf8");
    pi.on("before_agent_start", ({ systemPromptOptions }) => {
      systemPromptOptions.sections.platoon_harness = words;
    });
  }

  const ours = (tool) => tool.startsWith(`mcp__${namespace}__`);
  const asks = (tool) => {
    if (ours(tool) || READS.has(tool)) return false;
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
}
