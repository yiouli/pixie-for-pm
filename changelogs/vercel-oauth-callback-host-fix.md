# Vercel OAuth Callback Host Fix

- fixed provider OAuth authorize and callback handling to derive the public callback URL from the current request when the configured callback URL still points at localhost
- fixed post-auth settings redirects to fall back to the current request origin when `WEB_APP_URL` is unset or still local-only
- added regression coverage for the Vercel OAuth flow on a non-local host with localhost-configured URLs
