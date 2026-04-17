import discord
from discord.ext import commands

from utils.calc import calc_max_bases_supported, get_units

# ─── Constants ────────────────────────────────────────────────────────────────

COLOR_SUCCESS = 0x2ECC71
COLOR_ERROR   = 0xE74C3C
COLOR_INFO    = 0x3498DB

# How many extra base counts to scan when looking for the next upgrade threshold
NEXT_THRESHOLD_SCAN = 200


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _efficiency_rating(bases: int, result: int, unit_record: dict) -> tuple[str, str]:
    """
    Rate how efficiently the player's bases support the unit.

    Derives the float result from calc logic, then expresses
    result / float_max as a percentage — how close to the next
    whole unit are they?

    Returns (percentage_str, label_with_emoji)
    """
    steel      = unit_record["steel"]
    alum       = unit_record["aluminium"]
    build_time = unit_record["time"]
    efficiency = 0.0

    try:
        from utils.calc import calc_w, get_rates
        rates = get_rates()
        if bases in rates:
            w   = calc_w(bases)
            p   = (w * build_time) / 3600.0
            sc  = p * 1000.0 / steel
            ac  = p * 1000.0 / alum
            flt = min(sc, ac)
            efficiency = min(100.0, (result / flt) * 100) if flt > 0 else 100.0
    except Exception:
        # Fallback approximation if calc internals are unavailable
        efficiency = min(100.0, (result / (result + 1)) * 100)

    if efficiency >= 95:
        label = "🟢 Optimal"
    elif efficiency >= 80:
        label = "🟡 Good"
    elif efficiency >= 60:
        label = "🟠 Moderate"
    else:
        label = "🔴 Low"

    return f"{efficiency:.1f}%", label


def _next_upgrade_threshold(unit: str, bases: int, current_result: int) -> tuple[int, int] | None:
    """
    Scan forward to find the minimum base count that yields (current_result + 1) units.

    Returns (bases_needed, bases_to_add) or None if not found within scan range.
    """
    target = current_result + 1
    for extra in range(1, NEXT_THRESHOLD_SCAN + 1):
        try:
            if calc_max_bases_supported(unit, bases + extra) >= target:
                return bases + extra, extra
        except Exception:
            continue
    return None


# ─── Cog ──────────────────────────────────────────────────────────────────────

class MaxBases(commands.Cog):
    """Max sustainable unit calculator for Strategy Combat."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._units: dict | None = None

    @property
    def units(self) -> dict:
        if self._units is None:
            self._units = get_units()
        return self._units

    # ── Input validation ──────────────────────────────────────────────────────

    def _validate_inputs(self, unit: str, bases: int) -> str | None:
        if unit not in self.units:
            available = ", ".join(f"`{u}`" for u in sorted(self.units))
            return f"`{unit}` is not a valid unit.\n\n**Available units:** {available}"
        if bases <= 0:
            return "Bases must be a positive integer greater than `0`."
        return None

    # ── Embed builders ────────────────────────────────────────────────────────

    @staticmethod
    def _error_embed(description: str) -> discord.Embed:
        return discord.Embed(title="⛔ Error", description=description, color=COLOR_ERROR)

    def _result_embed(self, unit: str, bases: int, result: int) -> discord.Embed:
        unit_record = self.units[unit]
        steel_cost  = unit_record["steel"]
        alum_cost   = unit_record["aluminium"]
        build_time  = unit_record["time"]

        if build_time < 60:
            time_display = f"{build_time:.0f}s"
        else:
            m, s = divmod(int(build_time), 60)
            time_display = f"{m}:{s:02d}"

        eff_pct, eff_label = _efficiency_rating(bases, result, unit_record)

        threshold = _next_upgrade_threshold(unit, bases, result)
        if threshold:
            next_bases, bases_to_add = threshold
            upgrade_value = (
                f"**+{bases_to_add}** bases → `{next_bases}` total\n"
                f"unlocks **{result + 1}** units/session"
            )
        else:
            upgrade_value = "Max reached within scan range"

        embed = discord.Embed(
            title="📊 Max Bases Supported",
            description=(
                f"With **{bases}** bases, you can sustain up to "
                f"**{result}** `{unit}` unit{'s' if result != 1 else ''} per session."
            ),
            color=COLOR_SUCCESS,
        )

        embed.add_field(name="Unit",   value=f"`{unit}`",           inline=True)
        embed.add_field(name="Bases",  value=f"`{bases}`",          inline=True)
        embed.add_field(name="Result", value=f"**{result}** units", inline=True)

        embed.add_field(
            name="Unit Stats",
            value=(
                f"**Build time:** `{time_display}`\n"
                f"**Steel/unit:** `{steel_cost:,}`\n"
                f"**Alum/unit:** `{alum_cost:,}`"
            ),
            inline=True,
        )
        embed.add_field(
            name="⚡ Efficiency",
            value=f"{eff_label}\n`{eff_pct}` throughput",
            inline=True,
        )
        embed.add_field(
            name="📈 Next Upgrade",
            value=upgrade_value,
            inline=True,
        )

        embed.set_footer(text=".mb <unit> <bases>  •  For full schedule use .sync")
        return embed

    # ── Command ───────────────────────────────────────────────────────────────

    @commands.command(
        name="mb",
        brief="Calculate max sustainable units for a base count.",
        help=(
            "Calculates how many units you can sustain per session given your base count.\n"
            "Also shows efficiency rating and how many bases you need for the next unit.\n\n"
            "**Usage**\n"
            "`.mb <unit> <bases>`\n\n"
            "**Examples**\n"
            "`.mb tank 50`\n"
            "`.mb artillery 120`"
        ),
    )
    async def mb(self, ctx: commands.Context, unit: str, bases: int) -> None:
        unit = unit.lower().strip()

        error = self._validate_inputs(unit, bases)
        if error:
            await ctx.send(embed=self._error_embed(error))
            return

        try:
            result = calc_max_bases_supported(unit, bases)
        except ValueError as e:
            await ctx.send(embed=self._error_embed(str(e)))
            return
        except Exception:
            await ctx.send(embed=self._error_embed("An unexpected error occurred. Please try again."))
            return

        await ctx.send(embed=self._result_embed(unit, bases, result))

    @mb.error
    async def mb_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(embed=self._error_embed(
                f"Missing required argument: `{error.param.name}`\n\n"
                f"**Usage:** `.mb <unit> <bases>`"
            ))
        elif isinstance(error, commands.BadArgument):
            await ctx.send(embed=self._error_embed(
                f"Invalid value — `bases` must be a whole number.\n\n"
                f"**Usage:** `.mb <unit> <bases>`"
            ))
        else:
            raise error


# ─── Setup ────────────────────────────────────────────────────────────────────

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MaxBases(bot))