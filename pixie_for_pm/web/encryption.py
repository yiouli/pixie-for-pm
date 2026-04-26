from __future__ import annotations

import json

from cryptography.fernet import Fernet


class CredentialCipher:
    def __init__(self, key: str) -> None:
        self._fernet = Fernet(key.encode())

    def encrypt_credentials(self, credentials: dict[str, str]) -> str:
        payload = json.dumps(credentials, separators=(",", ":")).encode()
        return self._fernet.encrypt(payload).decode()

    def decrypt_credentials(self, encrypted: str) -> dict[str, str]:
        payload = self._fernet.decrypt(encrypted.encode()).decode()
        data = json.loads(payload)
        if not isinstance(data, dict):
            raise ValueError("Encrypted credentials payload must decode to an object.")
        return {str(key): str(value) for key, value in data.items()}
