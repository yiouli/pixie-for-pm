# Discord Thread And Command Sync Fixes

- stopped globally syncing slash commands during bot startup so `/settings` no longer appears twice alongside its guild-scoped copy
- reused a referenced starter message's thread as the Discord thread context when a reply targets that thread from the parent channel
- routed bot responses back into the existing thread instead of posting a new top-level channel message for that reply path
- added focused regression coverage for command sync behavior and reply-to-thread routing
