"""Optional customer PINs (4-8 digits) for the kiosk tab.

A PIN has at most 10**8 values, so no hash alone protects it once the database
leaks. PINs are therefore stored as

    Argon2id( HMAC-SHA256(pepper, pin) )

- Argon2id (memory-hard: 64 MiB, 3 passes, 4 lanes, random 16-byte salt) makes
  every guess expensive on GPUs/ASICs.
- The pepper is a 256-bit secret kept OUTSIDE the database: the PIN_PEPPER env
  var, or else ``pin_pepper.key`` (mode 0600) created next to the database on
  first use. Database dumps and the app's own backups never contain it, so a
  copied database alone cannot be brute-forced. Back the key file up separately:
  without it every stored PIN stops matching and admins must reset them.
- Online guessing at the kiosk is stopped by a per-customer lockout
  (``MAX_FAILED_ATTEMPTS`` wrong PINs lock the account for ``LOCK_MINUTES``).

Nobody - admins included - can read a PIN back; admins can only remove it.
"""

import hashlib
import hmac
import os
import re
import secrets
from functools import lru_cache

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from config import settings

PIN_PATTERN = re.compile(r"^[0-9]{4,8}$")
MAX_FAILED_ATTEMPTS = 5
LOCK_MINUTES = 15
PEPPER_FILENAME = "pin_pepper.key"

# Explicit parameters (OWASP / RFC 9106 recommendations) so library default
# changes never silently weaken stored hashes.
_hasher = PasswordHasher(
    time_cost=3,
    memory_cost=64 * 1024,
    parallelism=4,
    hash_len=32,
    salt_len=16,
)


def is_valid_pin(pin: object) -> bool:
    return isinstance(pin, str) and bool(PIN_PATTERN.match(pin))


def pepper_path() -> str:
    directory = os.path.dirname(os.path.abspath(settings.database_path)) or "."
    return os.path.join(directory, PEPPER_FILENAME)


@lru_cache(maxsize=1)
def _pepper() -> bytes:
    from_env = os.environ.get("PIN_PEPPER", "")
    if from_env:
        if len(from_env) < 32:
            raise RuntimeError("PIN_PEPPER must be at least 32 characters")
        return from_env.encode("utf-8")
    path = pepper_path()
    if not os.path.exists(path):
        directory = os.path.dirname(path)
        os.makedirs(directory, exist_ok=True)
        # Write a complete key to a private temp file, then hard-link it into
        # place: the link fails if another process won the race, and nobody can
        # ever read a half-written key.
        tmp = os.path.join(directory, f".{PEPPER_FILENAME}.{secrets.token_hex(8)}")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, "w") as f:
                f.write(secrets.token_hex(32))
            try:
                os.link(tmp, path)
            except FileExistsError:
                pass
        finally:
            os.unlink(tmp)
    with open(path, encoding="utf-8") as f:
        key = f.read().strip()
    if len(key) < 32:
        raise RuntimeError(f"{path} does not contain a usable PIN pepper")
    return key.encode("utf-8")


def _peppered(pin: str) -> bytes:
    return hmac.new(_pepper(), pin.encode("utf-8"), hashlib.sha256).digest()


def hash_pin(pin: str) -> str:
    return _hasher.hash(_peppered(pin))


def verify_pin(stored: str | None, pin: str | None) -> bool:
    if not stored or not pin:
        return False
    try:
        return _hasher.verify(stored, _peppered(pin))
    except (VerificationError, InvalidHashError):
        return False
