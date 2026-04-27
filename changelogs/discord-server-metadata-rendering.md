# Discord Server Metadata Rendering

- fetch Discord guild metadata during the settings server-claim flow using the bot token
- persist guild `name` and `icon_url` in the shared server store so follow-up requests reuse the same metadata
- render the settings workspace header with the Discord server icon and human-readable name instead of the raw guild ID when metadata is available
