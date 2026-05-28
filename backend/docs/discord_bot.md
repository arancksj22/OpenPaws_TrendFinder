# OpenPaws Discord Bot Integration

OpenPaws TrendFinder includes an interactive Discord Bot that allows you to query trending animal advocacy topics and generate AI explainers directly from a Discord server.

## Features

- **`!trends`**: Queries the Supabase database to fetch the top 5 highest-volume trending topics from the last 24 hours. Formats them into a highly readable Markdown response.
- **`!explain <trend_id>`**: Generates a 2-3 sentence AI explainer for a specific trend using Google Gemini, saves it to the database, and displays it in chat.

## Setup Instructions

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications).
2. Click **New Application** and give your bot a name.
3. Navigate to the **Bot** tab on the left menu.
4. **Important:** Scroll down to **Privileged Gateway Intents** and enable the **Message Content Intent**. This is required for the bot to read commands like `!trends`.
5. Click **Reset Token** to generate your Bot Token.
6. Copy this token and add it to your `backend/.env` file:
   ```env
   DISCORD_BOT_TOKEN=your_token_here
   ```
7. Go to the **OAuth2 > URL Generator** tab.
8. Check `bot` under Scopes, and check `Send Messages` and `Read Message History` under Bot Permissions.
9. Copy the generated URL and paste it into your browser to invite the bot to your Discord server.

## How it Runs

The Discord bot is natively integrated into the FastAPI application lifecycle. 

When you start your FastAPI server (e.g., via Render, or locally using `npm run start:backend` or `uvicorn app.main:app`), the backend will automatically spawn a background asynchronous task that connects the Discord bot to the server.

You **do not** need to run `python discord_bot.py` manually if your FastAPI server is running. It will start and stop alongside the main web service.
