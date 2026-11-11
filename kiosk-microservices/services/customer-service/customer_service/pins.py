"""Optional customer PINs (4-8 digits) for the kiosk tab.

PINs are stored as ``Argon2id( HMAC-SHA256(pepper, pin) )``. The pepper is a
secret kept outside the database: ``PIN_PEPPER`` (the ``kiosk-secrets`` Secret in
Kubernetes) or else ``pin_pepper.key`` created in the data directory. Without it
every stored PIN stops matching and admins must reset them.
"""

import hashlib
import hmac
import os
import re
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

PIN_PATTERN = re.compile(r"^[0-9]{4,8}$")
MAX_FAILED_ATTEMPTS = 5
LOCK_MINUTES = 15
PEPPER_FILENAME = "pin_pepper.key"

_hasher = PasswordHasher(time_cost=3, memory_cost=64 * 1024, parallelism=4, hash_len=32, salt_len=16)


def is_valid_pin(pin: object) -> bool:
    return isinstance(pin, str) and bool(PIN_PATTERN.match(pin))


class PinHasher:
    def __init__(self, pepper: str, data_dir: str):
        self._pepper_value = pepper
        self._data_dir = data_dir
        self._cached: bytes | None = None

    def pepper(self) -> bytes:
        if self._cached is not None:
            return self._cached
        if self._pepper_value:
            if len(self._pepper_value) < 32:
                raise RuntimeError("PIN_PEPPER must be at least 32 characters")
            self._cached = self._pepper_value.encode("utf-8")
            return self._cached
        path = os.path.join(self._data_dir, PEPPER_FILENAME)
        if not os.path.exists(path):
            os.makedirs(self._data_dir, exist_ok=True)
            tmp = os.path.join(self._data_dir, f".{PEPPER_FILENAME}.{secrets.token_hex(8)}")
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
        self._cached = key.encode("utf-8")
        return self._cached

    def _peppered(self, pin: str) -> bytes:
        return hmac.new(self.pepper(), pin.encode("utf-8"), hashlib.sha256).digest()

    def hash_pin(self, pin: str) -> str:
        return _hasher.hash(self._peppered(pin))

    def verify_pin(self, stored: str | None, pin: str | None) -> bool:
        if not stored or not pin:
            return False
        try:
            return _hasher.verify(stored, self._peppered(pin))
        except (VerificationError, InvalidHashError):
            return False
