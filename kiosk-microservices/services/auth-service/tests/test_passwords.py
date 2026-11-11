from auth_service.security import get_password_hash, verify_password
from auth_service.seed import initial_admin_password


def test_bcrypt_roundtrip():
    hashed = get_password_hash("correct horse")
    assert verify_password("correct horse", hashed)
    assert not verify_password("wrong", hashed)
    assert not verify_password("x", "not-a-hash")


def test_short_admin_password_is_replaced_by_a_random_one(capsys):
    generated = initial_admin_password("short")
    assert len(generated) >= 16 and generated != "short"
    assert "ignoring it" in capsys.readouterr().out
    assert initial_admin_password("long-enough-password") == "long-enough-password"
