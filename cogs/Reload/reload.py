import discord
from discord.ext import commands

from utils.calc import reload_data

# ─── Constants ────────────────────────────────────────────────────────────────

COLOR_SUCCESS = 0x2ECC71
COLOR_ERROR   = 0xE74C3C
COLOR_WARNING = 0xF39C12


# ─── Cog ──────────────────────────────────────────────────────────────────────

class Reload(commands.Cog):
    """Admin-only hot-reload commands."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ── Embed builders ────────────────────────────────────────────────────────

    @staticmethod
    def _error_embed(description: str) -> discord.Embed:
        return discord.Embed(
            title="⛔ Error",
            description=description,
            color=COLOR_ERROR,
        )

    # ── Commands ──────────────────────────────────────────────────────────────

    @commands.command(
        name="reloadunits",
        aliases=["ru"],
        brief="[Admin] Reload unit and rate data from disk.",
        help=(
            "Reloads the unit and rate JSON data without restarting the bot.\n"
            "Requires administrator permission.\n\n"
            "**Usage**\n"
            "`.reloadunits` or `.ru`"
        ),
    )
    @commands.has_permissions(administrator=True)
    async def reloadunits(self, ctx: commands.Context) -> None:
        try:
            units, rates = reload_data()
            embed = discord.Embed(
                title="🔄 Data Reloaded",
                description=(
                    f"Successfully reloaded data from disk.\n\n"
                    f"**Units loaded:** `{len(units)}`\n"
                    f"**Rate entries:** `{len(rates)}`"
                ),
                color=COLOR_SUCCESS,
            )
            await ctx.send(embed=embed)
        except Exception as e:
            await ctx.send(embed=self._error_embed(
                f"Failed to reload data.\n\n**Error:** `{e}`"
            ))

    @reloadunits.error
    async def reloadunits_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        if isinstance(error, commands.MissingPermissions):
            await ctx.send(embed=self._error_embed(
                "You need **Administrator** permission to use this command."
            ))
        else:
            raise error

    # ── ──────────────────────────────────────────────────────────────────────

    @commands.command(
        name="reloadcog",
        aliases=["rc"],
        brief="[Admin] Reload a specific cog by name.",
        help=(
            "Reloads a cog module without restarting the bot.\n"
            "Requires administrator permission.\n\n"
            "**Usage**\n"
            "`.reloadcog <cog_name>` or `.rc <cog_name>`\n\n"
            "**Examples**\n"
            "`.reloadcog sync`\n"
            "`.reloadcog maxbases`"
        ),
    )
    @commands.has_permissions(administrator=True)
    async def reloadcog(self, ctx: commands.Context, cog_name: str) -> None:
        # Strip 'cogs.' prefix if the user included it, and normalise
        cog_name    = cog_name.lower().strip().removeprefix("cogs.")
        module_path = f"cogs.{cog_name}"

        # Build a readable list of currently loaded cog modules for error messages
        def _loaded_cogs() -> str:
            loaded = sorted(
                ext.removeprefix("cogs.")
                for ext in self.bot.extensions
                if ext.startswith("cogs.")
            )
            return "\n".join(f"• `{name}`" for name in loaded) or "None"

        try:
            await self.bot.reload_extension(module_path)
            embed = discord.Embed(
                title="🔄 Cog Reloaded",
                description=f"Successfully reloaded `{cog_name}`.",
                color=COLOR_SUCCESS,
            )
            await ctx.send(embed=embed)

        except commands.ExtensionNotLoaded:
            await ctx.send(embed=self._error_embed(
                f"`{cog_name}` is not currently loaded.\n\n"
                f"**Loaded cogs:**\n{_loaded_cogs()}"
            ))
        except commands.ExtensionNotFound:
            await ctx.send(embed=self._error_embed(
                f"`{cog_name}` could not be found in your `cogs/` folder.\n\n"
                f"**Loaded cogs:**\n{_loaded_cogs()}"
            ))
        except Exception as e:
            await ctx.send(embed=self._error_embed(
                f"Failed to reload `{cog_name}`.\n\n**Error:** `{e}`"
            ))

    @reloadcog.error
    async def reloadcog_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        if isinstance(error, commands.MissingPermissions):
            await ctx.send(embed=self._error_embed(
                "You need **Administrator** permission to use this command."
            ))
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(embed=self._error_embed(
                f"Missing required argument: `{error.param.name}`\n\n"
                f"**Usage:** `.reloadcog <cog_name>`"
            ))
        else:
            raise error


# ─── Setup ────────────────────────────────────────────────────────────────────

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Reload(bot))