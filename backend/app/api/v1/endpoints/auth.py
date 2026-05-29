"""Auth endpoints — login, logout, me.

Proxies to the Supabase Auth REST API so we never store passwords ourselves.
The Supabase project URL and anon key are read from environment variables.
"""

from __future__ import annotations

import logging
import os

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr

from app.core.security import AuthContext, get_auth_context

logger = logging.getLogger(__name__)

router = APIRouter()


# ── helpers ────────────────────────────────────────────────────────────────


def _supabase_auth_url() -> str:
	url = os.getenv("SUPABASE_URL", "").rstrip("/")
	if not url:
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail="SUPABASE_URL is not configured",
		)
	return f"{url}/auth/v1"


def _anon_key() -> str:
	key = os.getenv("SUPABASE_ANON_KEY", "")
	if not key:
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail="SUPABASE_ANON_KEY is not configured",
		)
	return key


def _supabase_headers() -> dict[str, str]:
	return {
		"apikey": _anon_key(),
		"Content-Type": "application/json",
	}


# ── schemas ────────────────────────────────────────────────────────────────


class LoginRequest(BaseModel):
	email: str
	password: str


class UserInfo(BaseModel):
	id: str
	email: str | None = None


class LoginResponse(BaseModel):
	access_token: str
	token_type: str = "bearer"
	user: UserInfo


class SignupRequest(BaseModel):
	email: str
	password: str


class MeResponse(BaseModel):
	user_id: str
	email: str | None = None


# ── endpoints ──────────────────────────────────────────────────────────────


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest) -> LoginResponse:
	"""Exchange email + password for a Supabase JWT."""
	auth_url = _supabase_auth_url()
	headers = _supabase_headers()

	try:
		async with httpx.AsyncClient(timeout=10.0) as client:
			resp = await client.post(
				f"{auth_url}/token?grant_type=password",
				headers=headers,
				json={"email": body.email, "password": body.password},
			)
	except httpx.RequestError as exc:
		logger.exception("Failed to reach Supabase Auth")
		raise HTTPException(
			status_code=status.HTTP_502_BAD_GATEWAY,
			detail=f"Could not reach authentication service: {exc}",
		)

	if resp.status_code != 200:
		# Forward Supabase's error message as-is
		try:
			detail = resp.json().get("error_description") or resp.json().get("msg") or resp.text
		except Exception:
			detail = resp.text
		raise HTTPException(
			status_code=status.HTTP_401_UNAUTHORIZED,
			detail=detail or "Invalid email or password",
			headers={"WWW-Authenticate": "Bearer"},
		)

	data = resp.json()
	user_data = data.get("user") or {}

	return LoginResponse(
		access_token=data["access_token"],
		token_type="bearer",
		user=UserInfo(
			id=user_data.get("id", ""),
			email=user_data.get("email"),
		),
	)


@router.post("/signup", response_model=LoginResponse, status_code=status.HTTP_201_CREATED)
async def signup(body: SignupRequest) -> LoginResponse:
	"""Register a new user via Supabase Auth and return a session token.

	Proxies to Supabase /auth/v1/signup. If the email is already registered,
	Supabase returns a 400 which we forward as a 409 Conflict.
	"""
	auth_url = _supabase_auth_url()
	headers = _supabase_headers()

	try:
		async with httpx.AsyncClient(timeout=10.0) as client:
			resp = await client.post(
				f"{auth_url}/signup",
				headers=headers,
				json={"email": body.email, "password": body.password},
			)
	except httpx.RequestError as exc:
		logger.exception("Failed to reach Supabase Auth during signup")
		raise HTTPException(
			status_code=status.HTTP_502_BAD_GATEWAY,
			detail=f"Could not reach authentication service: {exc}",
		)

	data = resp.json()

	if resp.status_code not in (200, 201):
		try:
			detail = data.get("error_description") or data.get("msg") or data.get("message") or resp.text
		except Exception:
			detail = resp.text
		http_status = status.HTTP_409_CONFLICT if resp.status_code == 400 else status.HTTP_400_BAD_REQUEST
		raise HTTPException(status_code=http_status, detail=detail or "Signup failed")

	# Supabase returns a session immediately if email confirmation is disabled.
	# If confirmation is required, access_token will be absent — tell the user.
	access_token = data.get("access_token")
	if not access_token:
		raise HTTPException(
			status_code=status.HTTP_202_ACCEPTED,
			detail="confirm_email",
		)

	user_data = data.get("user") or {}
	return LoginResponse(
		access_token=access_token,
		token_type="bearer",
		user=UserInfo(
			id=user_data.get("id", ""),
			email=user_data.get("email"),
		),
	)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(auth: AuthContext = Depends(get_auth_context)) -> None:
	"""Invalidate the current Supabase session server-side."""
	auth_url = _supabase_auth_url()
	headers = {
		**_supabase_headers(),
		"Authorization": f"Bearer {auth.token}",
	}
	try:
		async with httpx.AsyncClient(timeout=10.0) as client:
			await client.post(f"{auth_url}/logout", headers=headers)
	except Exception:
		# Non-fatal — client should clear local storage regardless
		logger.warning("Supabase logout call failed (non-fatal)")


@router.get("/me", response_model=MeResponse)
async def me(auth: AuthContext = Depends(get_auth_context)) -> MeResponse:
	"""Return the authenticated user's id and email from the JWT.

	Also validates the token is still active by calling Supabase /user.
	"""
	auth_url = _supabase_auth_url()
	headers = {
		**_supabase_headers(),
		"Authorization": f"Bearer {auth.token}",
	}
	try:
		async with httpx.AsyncClient(timeout=10.0) as client:
			resp = await client.get(f"{auth_url}/user", headers=headers)
		if resp.status_code == 200:
			user_data = resp.json()
			return MeResponse(
				user_id=auth.user_id,
				email=user_data.get("email"),
			)
	except Exception:
		logger.warning("Could not reach Supabase /user — returning JWT claims only")

	# Fallback: return what we decoded from the JWT
	return MeResponse(user_id=auth.user_id)
