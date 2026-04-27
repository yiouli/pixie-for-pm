# Hosted MCP OAuth Fix

- fixed Notion and Vercel hosted MCP connections to use protected-resource discovery, dynamic client registration, and resource-bound authorization instead of treating them like generic OAuth app integrations
- fixed Vercel MCP authorization to request the provider's advertised hosted-MCP scopes and token endpoint rather than the legacy REST OAuth contract
- fixed Vercel hosted MCP authorization to keep using the configured Vercel OAuth app client when one is present, preserving previously registered callback URLs like `http://localhost:8000/api/connections/oauth/callback`
- persisted hosted MCP client metadata with encrypted credentials so future refresh-token exchanges can renew expired MCP access tokens without surfacing a 401 during tool initialization
- added runtime refresh-and-retry support for hosted MCP providers and clearer reconnect messaging for legacy stored connections that were created before the hosted MCP flow stored refresh metadata
- added regression coverage for provider discovery, callback credential storage, hosted MCP refresh, and persisted credential updates
