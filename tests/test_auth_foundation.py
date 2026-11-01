"""Offline lifecycle tests for the isolated authentication foundation."""

from sqlalchemy import create_engine, select

from site_directedideation_com.auth.schema import accounts, tokens, upgrade
from site_directedideation_com.auth.service import AuthService


def test_lifecycle(tmp_path):
    """Exercise verification, activation, expiry and recovery."""
    engine = create_engine(f"sqlite:///{tmp_path / 'auth.db'}")
    upgrade(engine)
    sent = []
    now = [1000]
    auth = AuthService(engine, lambda *args: sent.append(args), lambda: now[0])
    assert auth.register(" User@Example.com ") is None
    verify = sent[-1][2]
    assert not auth.authenticate("user@example.com", "correct horse battery")
    assert auth.verify_email(verify)
    assert not auth.verify_email(verify)
    password_token = sent[-1][2]
    assert not auth.set_password(password_token, "short")
    assert auth.set_password(password_token, "correct horse battery")
    assert not auth.set_password(password_token, "another good password")
    assert auth.authenticate("USER@example.com", "correct horse battery")
    assert not auth.authenticate("missing@example.com", "correct horse battery")
    assert auth.request_reset("user@example.com") is None
    reset = sent[-1][2]
    now[0] += 1800
    assert not auth.set_password(reset, "another good password")
    auth.request_reset("user@example.com")
    assert auth.set_password(sent[-1][2], "another good password")
    assert not auth.authenticate("user@example.com", "correct horse battery")
    with engine.connect() as conn:
        row = conn.execute(select(accounts)).one()
        assert row.password_hash.startswith("$argon2id$")
        assert all(
            verify != item.digest and reset != item.digest
            for item in conn.execute(select(tokens))
        )
    count = len(sent)
    assert auth.register("user@example.com") is None
    assert auth.request_reset("unknown@example.com") is None
    assert len(sent) == count


def test_nonprintable_email_rejected(tmp_path):
    """Control characters never become account identities."""
    engine = create_engine(f"sqlite:///{tmp_path / 'auth.db'}")
    upgrade(engine)
    sent = []
    auth = AuthService(engine, lambda *args: sent.append(args))
    for email in ("user\x00@example.com", "user\x7f@example.com", "user@example.com\n"):
        auth.register(email)
        auth.request_reset(email)
    with engine.connect() as conn:
        assert conn.execute(select(accounts)).all() == []
    assert not sent


def test_password_token_precheck_and_atomic_revalidation(tmp_path, monkeypatch):
    """Reject bad tokens cheaply and recheck after hashing."""
    engine = create_engine(f"sqlite:///{tmp_path / 'auth.db'}")
    upgrade(engine)
    sent = []
    now = [1000]
    auth = AuthService(engine, lambda *args: sent.append(args), lambda: now[0])
    auth.register("user@example.com")
    verify = sent[-1][2]
    assert auth.verify_email(verify)
    secret = sent[-1][2]
    original_hash = auth.hasher.hash
    calls = []

    def hash_and_expire(password):
        calls.append(password)
        now[0] += 1800
        return original_hash(password)

    monkeypatch.setattr(
        auth, "hasher", type("Hasher", (), {"hash": staticmethod(hash_and_expire)})()
    )
    assert not auth.set_password("invalid", "a sufficiently long password")
    assert not auth.set_password(verify, "a sufficiently long password")
    assert calls == []
    assert not auth.set_password(secret, "a sufficiently long password")
    assert len(calls) == 1  # Expired after precheck, before atomic consume.
    with engine.connect() as conn:
        assert conn.execute(select(accounts.c.password_hash)).scalar_one() is None

    monkeypatch.setattr(
        auth, "hasher", type("Hasher", (), {"hash": staticmethod(original_hash)})()
    )
    auth.request_reset("user@example.com")
    secret = sent[-1][2]
    assert auth.set_password(secret, "a sufficiently long password")
    monkeypatch.setattr(
        auth, "hasher", type("Hasher", (), {"hash": staticmethod(hash_and_expire)})()
    )
    assert not auth.set_password(secret, "another sufficiently long password")
    assert len(calls) == 1  # Replay rejected without a second KDF.
