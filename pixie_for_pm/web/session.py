"""Session codec: Fernet-encrypted, signed, time-limited session cookies.

The payload is a JSON object encrypted with a Fernet key stored in
SESSION_SECRET_KEY.  The cookie is HttpOnly and SameSite=Lax so it is sent
automatically by the browser on same-origin requests without being readable
from JavaScript.

Typical lifetime is 30 days.  Sessions are stateless — there is no server-side
session table — so logout is handled by deleting the cookie on the client side.
To invalidate all sessions (e.g. after a security incident) rotate
SESSION_SECRET_KEY.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from cryptography.fernet import Fernet, InvalidToken


@dataclass(frozen=True)
class SessionUser:
    """Decoded contents of a session cookie."""

    discord_user_id: str
    display_name: str | None
    email: str | None


class SessionCodec:
    """Encode and decode session cookies using Fernet symmetric encryption.

    A valid session cookie is an opaque string produced by :meth:`encode`.
    It decodes back to a :class:`SessionUser` until the embedded expiry is
    reached.  Tampered or expired cookies return ``None`` from :meth:`decode`.
    """

    COOKIE_NAME = "session"
    DEFAULT_TTL_SECONDS = 60 * 60 * 24 * 30  # 30 days

    def __init__(self, secret_key: str) -> None:
        self._fernet = Fernet(secret_key.encode())

    def encode(
        self,
        user: SessionUser,
        *,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
    ) -> str:
        """Return an encrypted, time-limited session token for *user*."""
        expiry = datetime.now(UTC) + timedelta(seconds=ttl_seconds)
        payload = {
            "discord_user_id": user.discord_user_id,
            "display_name": user.display_name,
            "email": user.email,
            "exp": expiry.isoformat(),
        }
        return self._fernet.encrypt(json.dumps(payload).encode()).decode()

    def decode(self, token: str) -> SessionUser | None:
        """Return the :class:`SessionUser` for *token*, or ``None`` if invalid."""
        try:
            raw = self._fernet.decrypt(token.encode()).decode()
            payload = json.loads(raw)
            exp = datetime.fromisoformat(payload["exp"])
            if exp < datetime.now(UTC):
                return None
            return SessionUser(
                discord_user_id=str(payload["discord_user_id"]),
                display_name=payload.get("display_name"),
                email=payload.get("email"),
            )
        except (InvalidToken, KeyError, ValueError, json.JSONDecodeError):
            return None
