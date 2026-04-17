import discord
from discord.ext import commands
from typing import Optional

# ─── Constants ────────────────────────────────────────────────────────────────

COLOR_INFO    = 0x3498DB
COLOR_ERROR   = 0xE74C3C

# Commands to exclude from help (internal/noise)
HIDDEN_COMMANDS = {"help"}


# ─── Custom Help Command ──────────────────────────────────────────────────────

class CustomHelp(commands.HelpCommand):
    """
    Clean paginated help command.

    .help               → lists all cogs and their commands
    .help <command>     → detailed view of a single command
    .help <cog>         → lists all commands in a cog
    """

    # ── Shared ────────────────────────────────────────────────────────────────

    def _base_embed(self, title: str, description: str = "") -> discord.Embed:
        embed = discord.Embed(title=title, description=description, color=COLOR_INFO)
        embed.set_footer(text=f"Prefix: {self.context.prefix}  •  .help <command> for details")
        return embed

    @staticmethod
    def _error_embed(description: str) -> discord.Embed:
        return discord.Embed(title="⛔ Error", description=description, color=COLOR_ERROR)

    def _fmt_command(self, cmd: commands.Command) -> str:
        """One-line summary for a command."""
        brief = cmd.brief or "No description."
        return f"`{self.context.prefix}{cmd.name}` — {brief}"

    # ── Overall help (.help) ──────────────────────────────────────────────────

    async def send_bot_help(self, mapping: dict) -> None:
        embed = self._base_embed(
            title="📖 BaseSync Help",
            description="Here's everything available. Use `.help <command>` for full details.",
        )

        for cog, cmds in mapping.items():
            # Filter hidden and commands the user can't run
            visible = [
                c for c in cmds
                if c.name not in HIDDEN_COMMANDS and not c.hidden
            ]
            if not visible:
                continue

            cog_name = cog.qualified_name if cog else "General"
            lines = [self._fmt_command(c) for c in sorted(visible, key=lambda c: c.name)]
            embed.add_field(name=f"📂 {cog_name}", value="\n".join(lines), inline=False)

        await self.get_destination().send(embed=embed)

    # ── Cog help (.help <CogName>) ────────────────────────────────────────────

    async def send_cog_help(self, cog: commands.Cog) -> None:
        visible = [
            c for c in cog.get_commands()
            if c.name not in HIDDEN_COMMANDS and not c.hidden
        ]
        if not visible:
            await self.get_destination().send(embed=self._error_embed(
                f"No visible commands in `{cog.qualified_name}`."
            ))
            return

        embed = self._base_embed(title=f"📂 {cog.qualified_name}")
        if cog.description:
            embed.description = cog.description

        for cmd in sorted(visible, key=lambda c: c.name):
            embed.add_field(
                name=f"`{self.context.prefix}{cmd.name}`",
                value=cmd.brief or "No description.",
                inline=False,
            )

        await self.get_destination().send(embed=embed)

    # ── Command help (.help <command>) ────────────────────────────────────────

    async def send_command_help(self, command: commands.Command) -> None:
        embed = self._base_embed(title=f"📋 Command — `{self.context.prefix}{command.name}`")

        # Description / help text
        if command.help:
            embed.description = command.help
        elif command.brief:
            embed.description = command.brief

        # Aliases
        if command.aliases:
            aliases = ", ".join(f"`{self.context.prefix}{a}`" for a in command.aliases)
            embed.add_field(name="Aliases", value=aliases, inline=False)

        # Usage
        usage = f"`{self.context.prefix}{command.name} {command.signature}`".strip()
        embed.add_field(name="Usage", value=usage, inline=False)

        await self.get_destination().send(embed=embed)

    # ── Not found ─────────────────────────────────────────────────────────────

    async def command_not_found(self, string: str) -> str:
        return f"`{string}` is not a valid command or category."

    async def send_error_message(self, error: str) -> None:
        await self.get_destination().send(embed=self._error_embed(error))


# ─── Cog wrapper ──────────────────────────────────────────────────────────────

class Help(commands.Cog, name="Help"):
    """Help and command reference."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._original_help = bot.help_command
        bot.help_command = CustomHelp()
        bot.help_command.cog = self

    def cog_unload(self) -> None:
        # Restore original help command if cog is unloaded
        self.bot.help_command = self._original_help


# ─── Setup ────────────────────────────────────────────────────────────────────

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Help(bot))