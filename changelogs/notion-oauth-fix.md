# Notion OAuth Fix

- fixed the Notion OAuth authorize URL to include the required `owner=user` parameter
- fixed the Notion token exchange to use HTTP Basic authentication with a JSON request body instead of the generic form-encoded client credential flow
- added regression coverage for the Notion-specific authorize URL and token exchange request shape
