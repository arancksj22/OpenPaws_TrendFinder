"""Authentication helpers for Supabase JWTs."""

from __future__ import annotations

import os
from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

import time
import httpx

_bearer = HTTPBearer(auto_error=False)

# In-memory cache to prevent hitting Supabase on every request
# Maps token -> expiration timestamp
_token_cache: dict[str, float] = {}

@dataclass(frozen=True)
class AuthContext:
	user_id: str
	token: str | None


async def get_auth_context(
	credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> AuthContext:
	if credentials is None:
		raise HTTPException(
			status_code=status.HTTP_401_UNAUTHORIZED,
			detail="Missing Authorization header",
			headers={"WWW-Authenticate": "Bearer"},
		)

	token = credentials.credentials
	try:
		# We don't verify the signature cryptographically here because Supabase uses various
		# algorithms (HS256, ES256) and the JWKS endpoint is sometimes disabled (404).
		# Instead, we extract the claims and ask Supabase to verify the token for us.
		payload = jwt.decode(token, options={"verify_signature": False, "verify_aud": False})
		user_id = payload.get("sub") or payload.get("user_id")
		exp = payload.get("exp", 0)
	except Exception as exc:
		raise HTTPException(
			status_code=status.HTTP_401_UNAUTHORIZED,
			detail=f"Invalid token format: {exc}",
			headers={"WWW-Authenticate": "Bearer"},
		)

	if not user_id:
		raise HTTPException(
			status_code=status.HTTP_401_UNAUTHORIZED,
			detail="Token missing user identifier (sub claim)",
			headers={"WWW-Authenticate": "Bearer"},
		)

	now = time.time()
	if exp and exp < now:
		raise HTTPException(
			status_code=status.HTTP_401_UNAUTHORIZED,
			detail="Token has expired",
			headers={"WWW-Authenticate": "Bearer"},
		)

	# 1. Check local cache
	if _token_cache.get(token, 0) > now:
		return AuthContext(user_id=str(user_id), token=token)

	# 2. Validate token against Supabase Auth API
	supabase_url = os.getenv("SUPABASE_URL", "").rstrip("/")
	anon_key = os.getenv("SUPABASE_ANON_KEY", "")
	if not supabase_url or not anon_key:
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail="SUPABASE_URL or SUPABASE_ANON_KEY is not configured",
		)

	try:
		async with httpx.AsyncClient(timeout=5.0) as client:
			resp = await client.get(
				f"{supabase_url}/auth/v1/user",
				headers={
					"apikey": anon_key,
					"Authorization": f"Bearer {token}",
					"Content-Type": "application/json",
				}
			)
	except httpx.RequestError as exc:
		raise HTTPException(
			status_code=status.HTTP_502_BAD_GATEWAY,
			detail=f"Could not reach authentication service: {exc}",
		)

	if resp.status_code != 200:
		raise HTTPException(
			status_code=status.HTTP_401_UNAUTHORIZED,
			detail="Invalid or revoked token (rejected by Supabase)",
			headers={"WWW-Authenticate": "Bearer"},
		)

	# 3. Cache the valid token
	# Cache until token expiration or 1 hour (whichever is sooner)
	cache_until = min(exp, now + 3600) if exp else now + 3600
	_token_cache[token] = cache_until

	# Prevent memory leaks by pruning expired tokens if cache gets large
	if len(_token_cache) > 1000:
		expired = [k for k, v in _token_cache.items() if v < now]
		for k in expired:
			_token_cache.pop(k, None)

	return AuthContext(user_id=str(user_id), token=token)


def get_current_user_id(auth: AuthContext = Depends(get_auth_context)) -> str:
	return auth.user_id
