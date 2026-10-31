"""Password hashing with no extra dependency.

Uses the standard library's ``hashlib.scrypt`` (a memory-hard KDF implemented in
OpenSSL) rather than adding ``argon2-cffi``. The security property that matters -
a slow, salted, memory-hard hash - is preserved, while the service keeps its
"no new service, no new download, works offline" property like every other
subsystem here.

Encoded form: ``scrypt$<n>$<r>$<p>$<salt_b64>$<hash_b64>``. The parameters are
stored with the hash so they can be raised later without invalidating existing
passwords.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

_ALGORITHM = "scrypt"
# ~16 MiB of memory per hash (128 * n * r bytes). Deliberately slow enough to
# make offline guessing expensive, fast enough for an interactive login.
_N = 2**14
_R = 8
_P = 1
_DKLEN = 32
_SALT_BYTES = 16


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def hash_password(password: str) -> str:
    """Hash a plaintext password. The plaintext is never logged or persisted."""
    salt = secrets.token_bytes(_SALT_BYTES)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=_N, r=_R, p=_P, dklen=_DKLEN)
    return f"{_ALGORITHM}${_N}${_R}${_P}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, encoded: str | None) -> bool:
    """Constant-time verification. Returns False (never raises) on a malformed
    stored hash, so a corrupt row cannot turn into a 500 at login."""
    if not encoded:
        return False
    try:
        algorithm, n, r, p, salt_b64, hash_b64 = encoded.split("$")
        if algorithm != _ALGORITHM:
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
        candidate = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(expected),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(candidate, expected)
