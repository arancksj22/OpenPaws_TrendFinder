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
