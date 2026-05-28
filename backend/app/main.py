"""FastAPI application entrypoint."""

from __future__ import annotations

import os
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router


def _load_cors_origins() -> list[str]:
	raw = os.getenv("CORS_ALLOW_ORIGINS", "http://localhost:3000,http://localhost:5173,http://localhost:5174")
	return [origin.strip() for origin in raw.split(",") if origin.strip()]


from contextlib import asynccontextmanager
import asyncio
import logging

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
	# Start Discord Bot
	token = os.getenv("DISCORD_BOT_TOKEN")
	bot_task = None
	if token:
		try:
			# Import here to avoid circular imports or early init issues
			import sys
			from pathlib import Path
			# Add backend root to path to ensure discord_bot can be found
			backend_root = Path(__file__).resolve().parent.parent
			if str(backend_root) not in sys.path:
				sys.path.insert(0, str(backend_root))
			
			from discord_bot import bot
			bot_task = asyncio.create_task(bot.start(token))
			logger.info("Discord Bot task scheduled to start.")
		except Exception as e:
			logger.exception(f"Failed to start Discord Bot: {e}")
	
	yield
	
	# Stop Discord Bot
	if bot_task and not bot_task.done():
		from discord_bot import bot
		logger.info("Closing Discord Bot connection...")
		await bot.close()

app = FastAPI(title="OpenPaws TrendFinder", version="0.1.0", lifespan=lifespan)
app.add_middleware(
	CORSMiddleware,
	allow_origins=_load_cors_origins(),
	allow_credentials=True,
	allow_methods=["*"],
	allow_headers=["*"],
)
app.include_router(api_router, prefix="/api/v1")


@app.get("/health")
def health_check() -> dict[str, str]:
	return {"status": "ok"}

import traceback
from fastapi import Request
from fastapi.responses import JSONResponse
from supabase import create_client

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
	"""Catch-all net for any unhandled exceptions in the FastAPI app."""
	error_message = str(exc)
	stack_trace = traceback.format_exc()
	
	logger.error(f"Global Exception Caught: {error_message}")
	logger.error(stack_trace)
	
	# Write failure data directly to Supabase api_error_logs table
	try:
		url = os.getenv("SUPABASE_URL")
		key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
		if url and key:
			supabase = create_client(url, key)
			supabase.table("api_error_logs").insert({
				"endpoint": str(request.url),
				"method": request.method,
				"error_message": error_message,
				"stack_trace": stack_trace
			}).execute()
	except Exception as db_err:
		logger.error(f"Failed to log error to Supabase api_error_logs: {db_err}")
		
	# Return a graceful 500 error instead of a hard crash
	return JSONResponse(
		status_code=500,
		content={"detail": "Internal Server Error. The failure has been logged."}
	)
