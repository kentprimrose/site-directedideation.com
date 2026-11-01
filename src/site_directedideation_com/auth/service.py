"""Transport-independent account lifecycle, with no logging or delivery backend."""

import hashlib
import secrets
import time
from collections.abc import Callable

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from sqlalchemy import insert, select, update
from sqlalchemy.exc import IntegrityError

from .schema import accounts, tokens

# Delivery receives (recipient, purpose, secret). Implementations must not log secrets.
Delivery = Callable[[str, str, str], None]


def _email(value: str) -> str | None:
    if not isinstance(value, str) or not value.isprintable():
        return None
    value = value.strip().lower()
    if len(value) > 254 or value.count("@") != 1 or any(c.isspace() for c in value):
        return None
    local, domain = value.split("@")
    if not local or not domain or len(local) > 64 or not value.isascii():
        return None
    return value


def _digest(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


class AuthService:
    """Account lifecycle with no account status in public request results."""

    def __init__(
        self, engine, deliver: Delivery, clock: Callable[[], float] = time.time
    ):
        """Configure persistence, secret delivery, and an injectable clock."""
        self.engine = engine
        self.deliver = deliver
        self.clock = clock
        self.hasher = PasswordHasher()
        self._dummy_hash = self.hasher.hash(secrets.token_urlsafe(32))

    def _issue(self, conn, account_id: int, purpose: str, now: int) -> str:
        """Issue under the caller's transaction and account-row write lock.

        A newly inserted account is already exclusively owned by its transaction.
        SQLite ignores FOR UPDATE and is only supported for offline tests.
        """
        secret = secrets.token_urlsafe(32)
        # Only the newest token for this purpose remains usable.
        conn.execute(
            update(tokens)
            .where(
                tokens.c.account_id == account_id,
                tokens.c.purpose == purpose,
                tokens.c.consumed_at.is_(None),
            )
            .values(consumed_at=now)
        )
        conn.execute(
            insert(tokens).values(
                digest=_digest(secret),
                account_id=account_id,
                purpose=purpose,
                expires_at=now + 1800,
            )
        )
        return secret

    def _send(self, email: str, purpose: str, secret: str) -> None:
        try:
            self.deliver(email, purpose, secret)
        except Exception:
            # Delivery errors are not surfaced to the public caller or logged here.
            pass

    def register(self, email: str) -> None:
        """Request verification without revealing whether an account exists."""
        normalized_email = _email(email)
        if not normalized_email:
            return
        now = int(self.clock())
        try:
            with self.engine.begin() as conn:
                row = conn.execute(
                    select(accounts)
                    .where(accounts.c.email == normalized_email)
                    .with_for_update()
                ).first()
                if row and row.verified:
                    return
                account_id = (
                    row.id
                    if row
                    else conn.execute(
                        insert(accounts).values(email=normalized_email, verified=False)
                    ).inserted_primary_key[0]
                )
                secret = self._issue(conn, account_id, "verify", now)
        except IntegrityError:
            # Concurrent first requests can race on the unique email constraint.
            return
        self._send(normalized_email, "verify", secret)

    def request_reset(self, email: str) -> None:
        """Request a reset for a verified account, with a uniform public result."""
        normalized_email = _email(email)
        if not normalized_email:
            return
        now = int(self.clock())
        with self.engine.begin() as conn:
            row = conn.execute(
                select(accounts)
                .where(accounts.c.email == normalized_email)
                .with_for_update()
            ).first()
            if not row or not row.verified:
                return
            secret = self._issue(conn, row.id, "password", now)
        self._send(normalized_email, "password", secret)

    def _consume(self, conn, secret: str, purpose: str, now: int):
        if not isinstance(secret, str) or len(secret) > 256:
            return None
        digest = _digest(secret)
        result = conn.execute(
            update(tokens)
            .where(
                tokens.c.digest == digest,
                tokens.c.purpose == purpose,
                tokens.c.consumed_at.is_(None),
                tokens.c.expires_at > now,
            )
            .values(consumed_at=now)
        )
        if result.rowcount != 1:
            return None
        return conn.execute(
            select(tokens.c.account_id).where(tokens.c.digest == digest)
        ).scalar_one()

    def verify_email(self, secret: str) -> bool:
        """Consume verification, then deliver a separate password-setting token."""
        now = int(self.clock())
        with self.engine.begin() as conn:
            account_id = self._consume(conn, secret, "verify", now)
            if account_id is None:
                return False
            conn.execute(
                update(accounts)
                .where(accounts.c.id == account_id)
                .values(verified=True)
            )
            email = conn.execute(
                select(accounts.c.email).where(accounts.c.id == account_id)
            ).scalar_one()
            password_token = self._issue(conn, account_id, "password", now)
        self._send(email, "password", password_token)
        return True

    def set_password(self, secret: str, password: str) -> bool:
        """Consume a password token atomically with its password update."""
        if not isinstance(password, str) or not 12 <= len(password) <= 1024:
            return False
        if not isinstance(secret, str) or len(secret) > 256:
            return False
        # This is only a cheap rejection filter, not authorization: the token can
        # expire, be replaced, or be consumed while the password is being hashed.
        with self.engine.connect() as conn:
            eligible = conn.execute(
                select(tokens.c.digest).where(
                    tokens.c.digest == _digest(secret),
                    tokens.c.purpose == "password",
                    tokens.c.consumed_at.is_(None),
                    tokens.c.expires_at > int(self.clock()),
                )
            ).first()
        if not eligible:
            return False
        hashed = self.hasher.hash(password)
        now = int(self.clock())
        with self.engine.begin() as conn:
            account_id = self._consume(conn, secret, "password", now)
            if account_id is None:
                return False
            result = conn.execute(
                update(accounts)
                .where(accounts.c.id == account_id, accounts.c.verified.is_(True))
                .values(password_hash=hashed)
            )
            return result.rowcount == 1

    def authenticate(self, email: str, password: str) -> bool:
        """Check credentials without disclosing which part failed."""
        normalized_email = _email(email)
        with self.engine.connect() as conn:
            row = (
                conn.execute(
                    select(accounts).where(accounts.c.email == normalized_email)
                ).first()
                if normalized_email
                else None
            )
        hashed = (
            row.password_hash
            if row and row.verified and row.password_hash
            else self._dummy_hash
        )
        if not isinstance(password, str) or len(password) > 1024:
            password = ""
        try:
            valid = self.hasher.verify(hashed, password)
        except (VerificationError, InvalidHashError):
            valid = False
        return bool(valid and row and row.verified and row.password_hash)
