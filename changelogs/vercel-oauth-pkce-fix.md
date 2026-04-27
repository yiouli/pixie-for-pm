# Vercel OAuth PKCE Fix

- fixed the Vercel token exchange endpoint to use `https://api.vercel.com/login/oauth/token` instead of the legacy `v2/oauth/access_token` path
- added PKCE support for Vercel OAuth by generating an S256 code challenge during authorize and sending the matching code verifier during callback exchange
- stored the PKCE verifier in a short-lived HttpOnly cookie for both redirect and `response_mode=json` authorize flows so the frontend settings page keeps working
- added regression coverage for Vercel authorize PKCE parameters, the corrected token endpoint, and callback exchanges on non-local hosts
