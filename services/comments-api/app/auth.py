from dataclasses import dataclass
from functools import lru_cache

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import Settings, get_settings

_bearer = HTTPBearer(auto_error=True)


@dataclass(frozen=True)
class Principal:
    sub: str
    name: str
    groups: frozenset[str]
    email: str | None = None

    def is_moderator(self, group: str) -> bool:
        return group in self.groups


@lru_cache
def _jwks_client(url: str) -> jwt.PyJWKClient:
    # Cached so JWKS keys aren't refetched on every request.
    return jwt.PyJWKClient(url)


def _decode(token: str, settings: Settings) -> dict:
    """Verify signature and standard claims.

    Two modes, chosen by config and nothing else in the app:
      - jwks_url set  -> RS256, keys fetched from the JWKS endpoint (Cognito).
      - otherwise     -> HS256 with the shared secret (local / first commit).
    """
    options = {"require": ["exp", "sub"]}
    kwargs = {
        "algorithms": ["RS256"] if settings.jwks_url else [settings.jwt_algorithm],
        "options": options,
    }
    if settings.jwt_audience:
        kwargs["audience"] = settings.jwt_audience
    else:
        options["verify_aud"] = False
    if settings.jwt_issuer:
        kwargs["issuer"] = settings.jwt_issuer

    if settings.jwks_url:
        key = _jwks_client(settings.jwks_url).get_signing_key_from_jwt(token).key
    else:
        key = settings.jwt_secret

    return jwt.decode(token, key, **kwargs)


def _groups(claims: dict) -> frozenset[str]:
    # Cognito puts group membership in cognito:groups; also accept a plain
    # "groups" list or an OAuth "scope" string.
    raw = claims.get("cognito:groups") or claims.get("groups") or []
    if isinstance(raw, str):
        raw = raw.split()
    scope = claims.get("scope", "")
    if isinstance(scope, str) and scope:
        raw = list(raw) + scope.split()
    return frozenset(raw)


def current_user(
    creds: HTTPAuthorizationCredentials = Depends(_bearer),
    settings: Settings = Depends(get_settings),
) -> Principal:
    try:
        claims = _decode(creds.credentials, settings)
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"invalid token: {exc}") from exc

    name = claims.get("name") or claims.get("cognito:username") or claims.get("email") or claims["sub"]
    return Principal(sub=claims["sub"], name=str(name), groups=_groups(claims), email=claims.get("email"))


def require_moderator(
    user: Principal = Depends(current_user),
    settings: Settings = Depends(get_settings),
) -> Principal:
    if not user.is_moderator(settings.moderator_group):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "moderator role required")
    return user
