import discord
from discord.ext import commands

from utils.calc import get_units

# ─── Constants ────────────────────────────────────────────────────────────────

COLOR_SUCCESS = 0x2ECC71
COLOR_ERROR   = 0xE74C3C
COLOR_INFO    = 0x3498DB


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _fmt_duration(seconds: float) -> str:
    """Convert seconds to a human-readable duration string."""
    if seconds < 60:
        return f"{seconds:.0f}s"
    m, s = divmod(int(seconds), 60)
    return f"{m}:{s:02d}"


# ─── Cog ──────────────────────────────────────────────────────────────────────

class UnitInfo(commands.Cog):
    """Look up raw stats for any unit."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._units: dict | None = None

    @property
    def units(self) -> dict:
        if self._units is None:
            self._units = get_units()
        return self._units

    # ── Embed builders ────────────────────────────────────────────────────────

    @staticmethod
    def _error_embed(description: str) -> discord.Embed:
        return discord.Embed(
            title="⛔ Error",
            description=description,
            color=COLOR_ERROR,
        )

    def _unit_embed(self, unit: str) -> discord.Embed:
        record     = self.units[unit]
        steel      = record["steel"]
        alum       = record["aluminium"]
        build_time = record["time"]

        embed = discord.Embed(
            title=f"🔍 Unit Info — `{unit}`",
            color=COLOR_INFO,
        )
        embed.add_field(name="Build Time",      value=f"`{_fmt_duration(build_time)}`", inline=True)
        embed.add_field(name="Steel Cost",      value=f"`{steel:,}`",                  inline=True)
        embed.add_field(name="Aluminium Cost",  value=f"`{alum:,}`",                   inline=True)
        embed.set_footer(text="Use .mb <unit> <bases> to calculate max sustainable units")
        return embed

    # ── Command ───────────────────────────────────────────────────────────────

    @commands.command(
        name="unitinfo",
        aliases=["ui"],
        brief="Show raw stats for a unit.",
        help=(
            "Displays the build time, steel cost, and aluminium cost for a unit.\n\n"
            "**Usage**\n"
            "`.unitinfo <unit>` or `.ui <unit>`\n\n"
            "**Examples**\n"
            "`.unitinfo tank`\n"
            "`.ui artillery`"
        ),
    )
    async def unitinfo(self, ctx: commands.Context, unit: str) -> None:
        unit = unit.lower().strip()

        if unit not in self.units:
            available = ", ".join(f"`{u}`" for u in sorted(self.units))
            await ctx.send(embed=self._error_embed(
                f"`{unit}` is not a valid unit.\n\n**Available units:** {available}"
            ))
            return

        await ctx.send(embed=self._unit_embed(unit))

    @unitinfo.error
    async def unitinfo_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(embed=self._error_embed(
                f"Missing required argument: `{error.param.name}`\n\n"
                f"**Usage:** `.unitinfo <unit>`"
            ))
        else:
            raise error


# ─── Setup ────────────────────────────────────────────────────────────────────

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(UnitInfo(bot))