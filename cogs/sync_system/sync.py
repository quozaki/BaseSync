import discord
from discord.ext import commands

from utils.calc import simulate_sync, get_units

# ─── Constants ────────────────────────────────────────────────────────────────

COLOR_SUCCESS = 0x2ECC71
COLOR_WARNING = 0xF39C12
COLOR_ERROR   = 0xE74C3C
COLOR_INFO    = 0x3498DB

SAFE_THRESHOLD     = 0.85   # start time < 85% of session = safe
RISKY_THRESHOLD    = 0.95   # start time >= 95% of session = risky
SCHEDULE_PAGE_SIZE = 15     # units per schedule embed page
TIMELINE_WIDTH     = 32     # characters wide for the ASCII bar


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _fmt_duration(seconds: float) -> str:
    """Convert seconds to a human-readable duration string."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    m, s = divmod(int(seconds), 60)
    return f"{m}:{s:02d}"


def _fmt_minutes(minutes: float) -> str:
    return _fmt_duration(minutes * 60)


def _classify_schedule(start_times: list[float], session_min: float) -> dict:
    safe = moderate = risky = 0
    for t in start_times:
        ratio = t / session_min if session_min > 0 else 0
        if ratio < SAFE_THRESHOLD:
            safe += 1
        elif ratio < RISKY_THRESHOLD:
            moderate += 1
        else:
            risky += 1
    return {"safe": safe, "moderate": moderate, "risky": risky}



def _offline_safety_window(
    start_times: list[float],
    session_min: float,
    pps: float,
    steel_cost: float,
    alum_cost: float,
    steel_storage: float | None,
    alum_storage: float | None,
) -> str:
    """
    Calculate how long a player can be offline after this session ends before
    the next session is delayed (i.e. resources won't be ready at session start).

    Logic:
      - After the session ends, resources regenerate at pps.
      - The next session needs steel_cost + alum_cost to start unit 1 immediately.
      - We calculate how much regen is needed and how long that takes.
      - If storage is provided, regen is capped at storage ceiling.

    Returns a formatted string describing the buffer, or a warning if none.
    """
    if not start_times:
        return "N/A"

    # Resource state at end of session (after last unit starts + remaining regen)
    # We approximate: at session end, the resource state is unknown precisely
    # without re-running the sim, so we use a conservative estimate:
    # assume 0 resources at session end (worst case), then compute time to refill.
    needed_steel = steel_cost
    needed_alum  = alum_cost

    if pps <= 0:
        return "N/A"

    # Time to regenerate enough for the first unit of the next session
    time_for_steel = needed_steel / pps
    time_for_alum  = needed_alum  / pps
    refill_seconds = max(time_for_steel, time_for_alum)

    # If storage is provided, cap refill at what storage allows
    if steel_storage is not None and alum_storage is not None:
        if steel_storage < steel_cost or alum_storage < alum_cost:
            return "⚠️ Storage too low to start next session"

    if refill_seconds <= 0:
        return "✅ Start next session immediately"

    buffer_str = _fmt_duration(refill_seconds)

    if refill_seconds <= 60:
        icon = "🟢"
    elif refill_seconds <= 300:
        icon = "🟡"
    else:
        icon = "🔴"

    return f"{icon} `{buffer_str}` offline buffer before next session is delayed"


def _build_schedule_lines(start_times: list[float]) -> list[str]:
    lines = []
    for i, minutes in enumerate(start_times):
        unit_num = f"Unit {i + 1:>2}"
        if i == 0:
            lines.append(f"`{unit_num}` │ **now**")
        else:
            elapsed  = _fmt_minutes(minutes)
            interval = _fmt_minutes(minutes - start_times[i - 1])
            lines.append(f"`{unit_num}` │ `{elapsed}` *(+{interval} from last)*")
    return lines


def _paginate(items: list[str], page_size: int) -> list[list[str]]:
    return [items[i : i + page_size] for i in range(0, len(items), page_size)]


# ─── Cog ──────────────────────────────────────────────────────────────────────

class SyncSystem(commands.Cog):
    """Production sync calculator for Strategy Combat."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._units: dict | None = None

    @property
    def units(self) -> dict:
        if self._units is None:
            self._units = get_units()
        return self._units

    # ── Input validation ──────────────────────────────────────────────────────

    def _validate_inputs(
        self,
        unit: str,
        bases: int,
        steel_storage: float | None,
        alum_storage: float | None,
    ) -> str | None:
        if unit not in self.units:
            available = ", ".join(f"`{u}`" for u in sorted(self.units))
            return f"`{unit}` is not a valid unit.\n\n**Available units:** {available}"
        if bases <= 0:
            return "Bases must be a positive integer greater than `0`."
        if (steel_storage is None) != (alum_storage is None):
            return (
                "Storage values must be provided **together**.\n"
                "Supply both `steel_storage` and `alum_storage` or neither."
            )
        if steel_storage is not None and steel_storage < 0:
            return "Steel storage cannot be negative."
        if alum_storage is not None and alum_storage < 0:
            return "Aluminium storage cannot be negative."
        return None

    # ── Embed builders ────────────────────────────────────────────────────────

    @staticmethod
    def _error_embed(description: str) -> discord.Embed:
        return discord.Embed(title="⛔ Error", description=description, color=COLOR_ERROR)

    def _summary_embed(
        self,
        unit: str,
        bases: int,
        steel_storage: float | None,
        alum_storage: float | None,
        result: dict,
        session_min: float,
        pps: float,
    ) -> discord.Embed:
        produced    = result["produced"]
        start_times = result["start_times"]
        removed     = result["removed_units"]

        unit_record = self.units[unit]
        session_sec = unit_record["time"]
        steel_cost  = unit_record["steel"]
        alum_cost   = unit_record["aluminium"]

        risk  = _classify_schedule(start_times, session_min)
        color = COLOR_SUCCESS if risk["risky"] == 0 else COLOR_WARNING

        desc_lines = [
            f"Queue once → **{produced} unit{'s' if produced != 1 else ''}** produced this session.",
        ]
        if removed > 0:
            desc_lines.append(
                f"\n⚠️ **{removed} unit{'s' if removed != 1 else ''} trimmed** to guarantee "
                f"the next session can start immediately."
            )

        embed = discord.Embed(
            title="📊 Sync Production",
            description="\n".join(desc_lines),
            color=color,
        )

        # Parameters
        param_value = f"**Unit:** `{unit}`\n**Bases:** `{bases}`"
        if steel_storage is not None:
            param_value += f"\n**Steel storage:** `{steel_storage:,.0f}`"
            param_value += f"\n**Alum storage:** `{alum_storage:,.0f}`"
        embed.add_field(name="Parameters", value=param_value, inline=True)

        # Unit stats
        if session_sec < 60:
            time_display = f"{session_sec:.0f}s"
        else:
            m, s = divmod(int(session_sec), 60)
            time_display = f"{m}:{s:02d}"

        embed.add_field(
            name="Unit Stats",
            value=(
                f"**Duration:** `{time_display}`\n"
                f"**Steel/unit:** `{steel_cost:,}`\n"
                f"**Alum/unit:** `{alum_cost:,}`"
            ),
            inline=True,
        )

        embed.add_field(name="\u200b", value="\u200b", inline=True)  # spacer

       
        

        # Start times summary
        if start_times:
            times_str = "  ".join(f"`{_fmt_minutes(t)}`" for t in start_times)
            embed.add_field(name="Start Times", value=times_str, inline=False)

        # Risk breakdown
        risk_parts = []
        if risk["safe"]     > 0: risk_parts.append(f"🟢 **{risk['safe']}** safe")
        if risk["moderate"] > 0: risk_parts.append(f"🟡 **{risk['moderate']}** moderate")
        if risk["risky"]    > 0: risk_parts.append(f"🔴 **{risk['risky']}** risky")
        if risk_parts:
            embed.add_field(name="Risk Breakdown", value="  •  ".join(risk_parts), inline=False)

        # ── Offline safety window ─────────────────────────────────────────────
        offline_msg = _offline_safety_window(
            start_times, session_min, pps,
            steel_cost, alum_cost,
            steel_storage, alum_storage,
        )
        embed.add_field(name="🕒 Offline Buffer", value=offline_msg, inline=False)

        embed.set_footer(text=".sync <unit> <bases> [steel] [alum]  •  Detailed schedule below")
        return embed

    @staticmethod
    def _schedule_embeds(schedule_lines: list[str], total_units: int) -> list[discord.Embed]:
        pages  = _paginate(schedule_lines, SCHEDULE_PAGE_SIZE)
        embeds = []
        for i, page in enumerate(pages):
            title = "📋 Production Schedule"
            if len(pages) > 1:
                title += f"  —  Page {i + 1}/{len(pages)}"
            embed = discord.Embed(
                title=title,
                description="\n".join(page),
                color=COLOR_INFO,
            )
            embed.set_footer(text=f"Total: {total_units} unit{'s' if total_units != 1 else ''}")
            embeds.append(embed)
        return embeds

    # ── Command ───────────────────────────────────────────────────────────────

    @commands.command(
        name="sync",
        brief="Calculate sync production for a unit.",
        help=(
            "Simulates a production session and shows how many units you can queue.\n"
            "Includes a session timeline, risk breakdown, and offline safety buffer.\n\n"
            "**Usage**\n"
            "`.sync <unit> <bases>` — no storage cap\n"
            "`.sync <unit> <bases> <steel> <alum>` — with storage cap\n\n"
            "**Examples**\n"
            "`.sync tank 50`\n"
            "`.sync tank 50 50000 50000`"
        ),
    )
    async def sync(
        self,
        ctx: commands.Context,
        unit: str,
        bases: int,
        steel_storage: float = None,
        alum_storage: float  = None,
    ) -> None:
        unit = unit.lower().strip()

        error = self._validate_inputs(unit, bases, steel_storage, alum_storage)
        if error:
            await ctx.send(embed=self._error_embed(error))
            return

        result = simulate_sync(unit, bases, steel_storage, alum_storage)
        if isinstance(result, str):
            await ctx.send(embed=self._error_embed(result))
            return

        unit_record = self.units[unit]
        session_min = unit_record["time"] / 60.0
        produced    = result["produced"]
        start_times = result["start_times"]

        # Derive pps the same way calc.py does
        try:
            from utils.calc import calc_w
            w   = calc_w(bases)
            pps = w * 1000.0 / 3600.0
        except Exception:
            pps = 0.0

        summary = self._summary_embed(
            unit, bases, steel_storage, alum_storage,
            result, session_min, pps,
        )
        await ctx.send(embed=summary)

        if produced > 1:
            schedule_lines = _build_schedule_lines(start_times)
            for page_embed in self._schedule_embeds(schedule_lines, produced):
                await ctx.send(embed=page_embed)

    @sync.error
    async def sync_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(embed=self._error_embed(
                f"Missing required argument: `{error.param.name}`\n\n"
                f"**Usage:** `.sync <unit> <bases> [steel] [alum]`"
            ))
        elif isinstance(error, commands.BadArgument):
            await ctx.send(embed=self._error_embed(
                f"Invalid value — `bases` must be a whole number.\n\n"
                f"**Usage:** `.sync <unit> <bases> [steel] [alum]`"
            ))
        else:
            raise error


# ─── Setup ────────────────────────────────────────────────────────────────────

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SyncSystem(bot))