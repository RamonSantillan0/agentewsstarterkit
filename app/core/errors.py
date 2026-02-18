class AgentError(Exception):
    pass


class LLMError(AgentError):
    pass


class ToolError(AgentError):
    pass


class SecurityError(AgentError):
    pass