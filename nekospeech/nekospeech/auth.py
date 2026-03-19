"""Auth utilities — JWT validation shared with the Django app."""

import logging

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from nekospeech.config import settings

logger = logging.getLogger(__name__)

bearer_scheme = HTTPBearer(auto_error=False)


def _decode_token(token: str) -> dict:
    """Decode and validate a JWT issued by the Django app."""
    return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict:
    """Return the decoded JWT payload or raise 401."""
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        payload = _decode_token(credentials.credentials)
    except JWTError as exc:
        import sys, hashlib
        token = credentials.credentials
        key = settings.jwt_secret_key
        # Decode WITHOUT verification to get payload
        try:
            unverified = jwt.decode(token, key, algorithms=["HS256"], options={"verify_signature": False})
            # Re-encode the payload with our key
            re_encoded = jwt.encode(unverified, key, algorithm="HS256")
            # Compare the original token with re-encoded
            orig_parts = token.split(".")
            re_parts = re_encoded.split(".")
            print(f"JWT_DEBUG: orig_sig={orig_parts[2][:20]} re_sig={re_parts[2][:20]} header_match={orig_parts[0]==re_parts[0]} payload_match={orig_parts[1]==re_parts[1]} sig_match={orig_parts[2]==re_parts[2]}", file=sys.stderr, flush=True)
            print(f"JWT_DEBUG: unverified_payload={unverified}", file=sys.stderr, flush=True)
        except Exception as e2:
            print(f"JWT_DEBUG: unverified decode also failed: {e2}", file=sys.stderr, flush=True)
        key_hash = hashlib.sha256(key.encode()).hexdigest()[:16]
        print(f"JWT_DEBUG: original error: {exc} | secret_sha={key_hash} | secret_len={len(key)}", file=sys.stderr, flush=True)
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
