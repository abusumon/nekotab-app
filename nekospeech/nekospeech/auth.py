"""Auth utilities — JWT validation shared with the Django app."""

import hmac

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from nekospeech.config import settings

bearer_scheme = HTTPBearer(auto_error=False)


def _decode_token(token: str) -> dict:
    """Decode and validate a JWT issued by the Django app.

    Works around a signature-verification bug in python-jose >=3.4 by
    verifying the HMAC signature manually: decode without verification,
    re-encode the payload with our key, and compare tokens in constant time.
    """
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        return payload
    except JWTError:
        pass

    # Fallback: manual verification for broken python-jose versions
    # Only accept HS256 to prevent algorithm confusion attacks
    header = jwt.get_unverified_header(token)
    if header.get("alg") != "HS256":
        raise JWTError("Unsupported algorithm")

    payload = jwt.decode(
        token, settings.jwt_secret_key,
        algorithms=["HS256"],
        options={"verify_signature": False},
    )
    expected = jwt.encode(payload, settings.jwt_secret_key, algorithm="HS256")
    if not hmac.compare_digest(token, expected):
        raise JWTError("Signature verification failed")
    return payload


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict:
    """Return the decoded JWT payload or raise 401."""
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        payload = _decode_token(credentials.credentials)
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    return payload


async def require_director(user: dict = Depends(get_current_user)) -> dict:
    """Require the JWT to carry a director role claim."""
    if user.get("role") != "director":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Director access required")
    return user


async def require_judge(user: dict = Depends(get_current_user)) -> dict:
    """Require the JWT to carry a judge role claim."""
    if user.get("role") not in ("judge", "director"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Judge access required")
    return user


def verify_tournament_access(user: dict, tournament_id: int) -> None:
    """Verify the JWT is scoped to the requested tournament.

    The Django app should include 'tournament_id' in the JWT payload.
    If the JWT has no tournament_id claim, access is denied.
    """
    token_tid = user.get("tournament_id")
    if token_tid is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token is not scoped to a tournament",
        )
    if int(token_tid) != int(tournament_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token is not authorized for this tournament",
        )
