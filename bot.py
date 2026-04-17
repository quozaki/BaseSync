import discord
from discord.ext import commands
import os
import asyncio
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("TOKEN")

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=".", intents=intents)


# ─── Cog Loader ───────────────────────────────────────────────────────────────

async def load_cogs() -> None:
    for root, _, files in os.walk("cogs"):
        for file in files:
            if file.endswith(".py") and file != "__init__.py":
                rel_path   = os.path.relpath(root, ".")
                module_path = rel_path.replace(os.sep, ".") + "." + file[:-3]
                try:
                    await bot.load_extension(module_path)
                    print(f"[COG] Loaded: {module_path}")
                except Exception as e:
                    print(f"[COG] Failed to load {module_path}: {e}")


# ─── Events ───────────────────────────────────────────────────────────────────

@bot.event
async def on_ready() -> None:
    print(f"[BOT] Connected as {bot.user}")
    print(f"[BOT] BaseSync version: {os.getenv('BaseSync', 'unknown')}")


# ─── Global Error Handler ─────────────────────────────────────────────────────

@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError) -> None:
    # Let cog-level or command-level handlers take priority
    if hasattr(ctx.command, "on_error"):
        return
    if ctx.cog and ctx.cog.has_error_handler():
        return

    if isinstance(error, commands.MissingRequiredArgument):
        embed = discord.Embed(
            title="⛔ Missing Argument",
            description=(
                f"Required argument missing: `{error.param.name}`\n\n"
                f"**Usage:** `{ctx.prefix}{ctx.command.name} {ctx.command.signature}`"
            ),
            color=0xE74C3C,
        )
        await ctx.send(embed=embed)

    elif isinstance(error, commands.BadArgument):
        embed = discord.Embed(
            title="⛔ Invalid Argument",
            description=(
                f"One of your inputs has the wrong type.\n\n"
                f"**Usage:** `{ctx.prefix}{ctx.command.name} {ctx.command.signature}`"
            ),
            color=0xE74C3C,
        )
        await ctx.send(embed=embed)

    elif isinstance(error, commands.CommandNotFound):
        pass  # silently ignore unknown commands

    else:
        # Log anything else to terminal but don't crash
        print(f"[ERROR] Unhandled command error in '{ctx.command}': {error}")


# ─── Built-in commands ────────────────────────────────────────────────────────

@bot.command(brief="Check bot latency.")
async def ping(ctx: commands.Context) -> None:
    await ctx.send(f"Pong! `{bot.latency * 1000:.0f}ms`")


# ─── Entry point ──────────────────────────────────────────────────────────────

async def main() -> None:
    async with bot:
        await load_cogs()
        await bot.start(TOKEN)


asyncio.run(main())