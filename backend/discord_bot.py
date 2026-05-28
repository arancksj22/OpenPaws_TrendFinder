import os
import sys
import logging
import asyncio
from datetime import datetime, timezone, timedelta

import discord
from discord.ext import commands
from dotenv import load_dotenv
from supabase import create_client, Client

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("discord_bot")

# Load environment variables
load_dotenv()
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

if not TOKEN or not SUPABASE_URL or not SUPABASE_KEY:
    logger.error("Missing DISCORD_BOT_TOKEN, SUPABASE_URL, or SUPABASE_SERVICE_ROLE_KEY in .env")
    sys.exit(1)

# Initialize Supabase client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Initialize Discord bot
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Import OpenPaws logic (we do this after dotenv is loaded)
try:
    from app.pipeline.humanintheloop import generate_explainer
except ImportError as e:
    logger.error(f"Failed to import OpenPaws logic. Are you running from the backend directory? Error: {e}")
    sys.exit(1)


@bot.event
async def on_ready():
    logger.info(f"Logged in as {bot.user} (ID: {bot.user.id})")
    logger.info("OpenPaws TrendFinder Discord Bot is now running! 🐾")
    logger.info("------")


@bot.command(name="trends", help="Fetch the top 5 animal advocacy trends from the last 24 hours.")
async def fetch_trends(ctx: commands.Context):
    """Query Supabase for top 5 recent trends and display them nicely."""
    try:
        await ctx.send("🔍 Fetching top trends from the database...")
        
        # Calculate timestamp for 24 hours ago
        twenty_four_hours_ago = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        
        # Fetch top 5 trends by representative_count
        response = supabase.table("trends") \
            .select("*, trend_examples(post_id)") \
            .gte("created_at", twenty_four_hours_ago) \
            .order("representative_count", desc=True) \
            .limit(5) \
            .execute()
            
        trends = response.data
        
        if not trends:
            await ctx.send("No trends found in the last 24 hours. 🐾")
            return
            
        message_lines = ["**🚀 Top 5 Trending Animal Advocacy Topics (Last 24h)**", ""]
        
        for idx, trend in enumerate(trends, 1):
            trend_id = trend["id"]
            count = trend.get("representative_count", 0)
            explainer = trend.get("explainer")
            status = trend.get("status", "pending")
            
            # Extract source platform and title from the first example post
            source = "Unknown"
            title = "Trending Topic"
            
            examples = trend.get("trend_examples", [])
            if examples and len(examples) > 0:
                first_post_id = examples[0].get("post_id")
                if first_post_id:
                    post_res = supabase.table("posts").select("source, title, text").eq("id", first_post_id).execute()
                    if post_res.data:
                        post = post_res.data[0]
                        source = str(post.get("source")).capitalize()
                        
                        # Use title if available, otherwise truncate the body text
                        title = post.get("title")
                        if not title:
                            title = post.get("text", "")[:60] + "..."
                        title = title.replace("\n", " ").strip()
            
            # Format the output
            status_emoji = "⏳" if status == "pending_review" else "✅"
            message_lines.append(f"**{idx}. {title}**")
            message_lines.append(f"🌐 **Source:** {source} | 📊 **Volume:** {count} posts | {status_emoji} **Status:** {status}")
            
            if explainer:
                message_lines.append(f"💡 **AI Explainer:** _{explainer}_")
            else:
                message_lines.append(f"💡 **AI Explainer:** _Not generated yet. Run `!explain {trend_id}`_")
                
            message_lines.append("") # Spacing
            
        # Discord limits messages to 2000 chars
        final_message = "\n".join(message_lines)
        if len(final_message) > 1990:
            final_message = final_message[:1990] + "..."
            
        await ctx.send(final_message)
        
    except Exception as e:
        logger.exception("Error fetching trends")
        await ctx.send("❌ An error occurred while fetching trends from the database.")


@bot.command(name="explain", help="Generate an AI explanation for a specific trend ID.")
async def explain_trend(ctx: commands.Context, trend_id: str):
    """Trigger the generate_explainer function for a specific trend ID."""
    try:
        # Check if trend exists
        response = supabase.table("trends").select("id, explainer").eq("id", trend_id).execute()
        if not response.data:
            await ctx.send(f"❌ Trend ID `{trend_id}` not found in the database.")
            return
            
        trend = response.data[0]
        if trend.get("explainer"):
            await ctx.send(f"⚠️ Trend already has an explainer:\n\n💡 _{trend['explainer']}_")
            return
            
        await ctx.send(f"🤖 Beep boop... firing up the AI supercomputer to analyze trend `{trend_id}`! Hang tight! 🐾✨")
        
        # Run the synchronous generate_explainer in a separate thread so we don't block the async bot loop
        loop = asyncio.get_running_loop()
        
        def run_explainer():
            # This calls Gemini, updates Supabase, and returns the dict
            return generate_explainer(trend_id=trend_id)
            
        result = await loop.run_in_executor(None, run_explainer)
        explainer_text = result.get("explainer", "Failed to generate text.")
        
        await ctx.send(f"✅ **Explainer Generated Successfully!**\n\n💡 _{explainer_text}_")
        
    except Exception as e:
        logger.exception(f"Error generating explainer for trend {trend_id}")
        await ctx.send("❌ An error occurred while generating the explainer.")


if __name__ == "__main__":
    bot.run(TOKEN)
