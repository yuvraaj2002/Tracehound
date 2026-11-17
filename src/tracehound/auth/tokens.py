"""Supabase access token verification against the project's public JWKS keys."""

import os
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

import jwt


class InvalidToken(Exception):
    """The bearer token is missing, malformed, expired or not issued by our Supabase project."""


@dataclass(frozen=True)
class User:
    """The signed-in user a request acts for. `user_id` is the Supabase auth user (`sub`)."""

    user_id: UUID
    email: str | None = None
    name: str | None = None
    avatar_url: str | None = None


class SigningKeySource(Protocol):
    def get_signing_key_from_jwt(self, token: str) -> jwt.PyJWK: ...


def supabase_url() -> str:
    """Return `SUPABASE_URL`, failing early with a clear message when it is unset."""
    url = os.environ.get("SUPABASE_URL")
    if not url:
        raise RuntimeError("SUPABASE_URL is not set. Add it to .env (see README).")
    return url.rstrip("/")


class TokenVerifier:
    """Checks signature, expiry, audience and issuer of Supabase access tokens."""

    ALGORITHMS = ("ES256", "RS256")
    AUDIENCE = "authenticated"

    def __init__(self, issuer: str, keys: SigningKeySource) -> None:
        self._issuer = issuer
        self._keys = keys

    @classmethod
    def for_project(cls, project_url: str) -> "TokenVerifier":
        """Build a verifier whose JWKS keys are fetched lazily and cached."""
        auth_url = f"{project_url}/auth/v1"
        return cls(auth_url, jwt.PyJWKClient(f"{auth_url}/.well-known/jwks.json"))

    def verify(self, token: str) -> User:
        try:
            signing_key = self._keys.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=list(self.ALGORITHMS),
                audience=self.AUDIENCE,
                issuer=self._issuer,
                options={"require": ["exp", "sub", "aud", "iss"]},
            )
            # Supabase copies the OAuth profile into `user_metadata`; GitHub may only give a login.
            metadata = claims.get("user_metadata") or {}
            name = metadata.get("full_name") or metadata.get("name") or metadata.get("user_name")
            return User(
                user_id=UUID(claims["sub"]),
                email=claims.get("email"),
                name=name if isinstance(name, str) else None,
                avatar_url=metadata.get("avatar_url") or None,
            )
        except (jwt.PyJWTError, ValueError) as exc:
            raise InvalidToken(str(exc)) from exc
