"""Authentication tokens and authority levels."""

from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass
from enum import IntEnum


class AuthorityLevel(IntEnum):
    USER = 1
    SYSTEM = 2
    ROOT = 3


@dataclass(frozen=True)
class AuthToken:
    """Signed, time-limited authority token."""

    level: AuthorityLevel
    issued_to: str
    expires_at: float
    signature: str

    @staticmethod
    def issue(
        level: AuthorityLevel,
        issued_to: str,
        ttl_seconds: int,
        secret: bytes,
    ) -> "AuthToken":
        expires_at = time.time() + ttl_seconds
        payload = f"{level.value}|{issued_to}|{expires_at}".encode()
        sig = hmac.new(secret, payload, hashlib.sha256).hexdigest()
        return AuthToken(level, issued_to, expires_at, sig)

    def verify(self, secret: bytes) -> bool:
        if time.time() > self.expires_at:
            return False
        payload = f"{self.level.value}|{self.issued_to}|{self.expires_at}".encode()
        expected = hmac.new(secret, payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, self.signature)
