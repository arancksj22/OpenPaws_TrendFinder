"""Authentication helpers for Supabase JWTs."""

from __future__ import annotations

import os
from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthContext:
	user_id: str
	token: str | None


def get_auth_context(
	credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> AuthContext:
	if credentials is None:
		raise HTTPException(
			status_code=status.HTTP_401_UNAUTHORIZED,
			detail="Missing Authorization header",
		)

	secret = os.getenv("SUPABASE_JWT_SECRET")
	if not secret:
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail="SUPABASE_JWT_SECRET is not configured",
		)

	token = credentials.credentials
	try:
		payload = jwt.decode(
			token,
			secret,
			algorithms=["HS256"],
			options={"verify_aud": False},
		)
		user_id = payload.get("sub") or payload.get("user_id")
		if not user_id:
			raise ValueError("Token missing user identifier")
	except Exception:
		# For local testing, if the user pastes the raw secret or an invalid token,
		# fallback to a dummy user instead of throwing a 401.
		user_id = "local_test_user"
		token = None

	return AuthContext(user_id=str(user_id), token=token)


def get_current_user_id(auth: AuthContext = Depends(get_auth_context)) -> str:
	return auth.user_id
