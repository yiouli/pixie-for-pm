# Hosted MCP 401 Refresh Unwrapping

- fixed hosted MCP unauthorized detection to unwrap `ExceptionGroup` wrappers emitted by the current MCP client stack
- restored automatic token refresh for refresh-capable hosted MCP providers such as Notion when the inner failure is an HTTP 401
- added regression coverage for wrapped 401 failures so refresh/retry behavior keeps working if the transport continues surfacing task-group exceptions
