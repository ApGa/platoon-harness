"""OpenCode, driven through `opencode acp`."""

from . import AgentSpec, DriverError, Reporter
from .acp import AcpDriver

__all__ = ["OpenCodeDriver"]


class OpenCodeDriver(AcpDriver):
    """OpenCode, by `opencode acp`, on the user's own setup with ours beside it, reaching the network as the shell
    does. A start that names no model is refused, as OpenCode with none set sends prompts to a hosted model nobody
    chose."""

    name = "opencode"
    inherits = (
        "HTTPS_PROXY",
        "HTTP_PROXY",
        "ALL_PROXY",
        "NO_PROXY",
        "https_proxy",
        "http_proxy",
        "all_proxy",
        "no_proxy",
        "SSL_CERT_FILE",
    )

    def __init__(self) -> None:
        super().__init__(("opencode", "acp"))

    async def start(self, spec: AgentSpec, report: Reporter) -> None:
        if spec.model is None:
            raise DriverError("set a model: OpenCode with none set sends prompts to a hosted model nobody chose")
        await super().start(spec, report)
