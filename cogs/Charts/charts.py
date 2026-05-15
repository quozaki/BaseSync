"""
Charts Cog — Strategy Combat public chart commands.
Scrapes strategycombat.com using a shared authenticated session.

Commands:
  .ranks [page]       — Player rankings (25/page, up to page 40)
  .profile <player>   — Public player profile
  .allyrank [count]   — Top alliances by points
  .ally <name|id>     — Full alliance detail + member list
"""

import os
import asyncio
import re

import discord
from discord.ext import commands

from utils.scraper import (
    SCSession,
    fetch_players_page,
    fetch_alliances,
    fetch_alliance_detail,
    fetch_player_profile,
    format_number,
)

# ── Colours ─────────────────────────────────────────────────────────────────
GOLD   = 0xFFAA33
YELLOW = 0xFFFF99
CYAN   = 0x00CCFF
GREEN  = 0x55CC55
GREY   = 0xAAAAAA
COLOR_ERROR = 0xE74C3C

def _rank_color(rank: int) -> int:
    if rank == 1:    return GOLD
    if rank <= 10:   return YELLOW
    if rank <= 25:   return CYAN
    if rank <= 100:  return GREEN
    return GREY


# ── Cog ──────────────────────────────────────────────────────────────────────

class Charts(commands.Cog):
    """Live charts and player/alliance lookups from Strategy Combat."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.sc  = SCSession()   # one shared session per cog instance

    # Called automatically after the cog loads
    async def cog_load(self) -> None:
        username = os.getenv("SC_USERNAME", "")
        password = os.getenv("SC_PASSWORD", "")
        if not username or not password:
            print("[Charts] WARNING: SC_USERNAME / SC_PASSWORD not set in .env")
            return
        ok = await asyncio.to_thread(self.sc.login, username, password)
        if ok:
            print("[Charts] Strategy Combat login successful.")
        else:
            print("[Charts] WARNING: Strategy Combat login FAILED. Check credentials.")

    # ── Shared embed helpers ─────────────────────────────────────────────────

    @staticmethod
    def _error_embed(description: str) -> discord.Embed:
        return discord.Embed(title="❌ Error", description=description, color=COLOR_ERROR)

    # ── Commands ─────────────────────────────────────────────────────────────

    @commands.command(
        name="ranks",
        aliases=["top25"],
        brief="Show player rankings from the charts.",
        help=(
            "Shows 25 players from the selected chart page.\n\n"
            "**Usage**\n"
            "`.ranks [page]`\n\n"
            "**Examples**\n"
            "`.ranks`        — top 25 players (#1–#25)\n"
            "`.ranks 2`      — ranks #26–#50\n"
            "`.ranks 40`     — ranks #976–#1000"
        ),
    )
    async def ranks(self, ctx: commands.Context, page: int = 1) -> None:
        if not 1 <= page <= 40:
            await ctx.send(embed=self._error_embed("Page must be between **1** and **40**."))
            return

        msg   = await ctx.send(f"⏳ Fetching player ranks (page {page})…")
        start = (page - 1) * 25 + 1

        try:
            players = await asyncio.to_thread(fetch_players_page, self.sc, start)
        except Exception as e:
            await msg.edit(content=None, embed=self._error_embed(f"Failed to fetch data.\n\n**Error:** `{e}`"))
            return

        if not players:
            await msg.edit(content=None, embed=self._error_embed(
                "No data returned. The session may have expired — try `.reloadcog charts.charts`."
            ))
            return

        embed = discord.Embed(
            title=f"🏆 Player Rankings — Page {page}  (#{start}–#{start + 24})",
            color=_rank_color(start),
        )

        lines = []
        for p in players:
            medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(p["rank"], "")
            lines.append(
                f"`{p['rank']:>4}.` {medal} **{p['name']}**  "
                f"[{p['alliance']}]  "
                f"{format_number(p['points'])} pts · "
                f"{format_number(p['bases'])} bases"
            )

        # Split into two fields to stay under Discord's 1024-char field limit
        embed.add_field(name="\u200b", value="\n".join(lines[:13]), inline=False)
        if len(lines) > 13:
            embed.add_field(name="\u200b", value="\n".join(lines[13:]), inline=False)

        embed.set_footer(text="strategycombat.com  ·  .ranks <page> for other pages")
        await msg.edit(content=None, embed=embed)

    @ranks.error
    async def ranks_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        if isinstance(error, commands.BadArgument):
            await ctx.send(embed=self._error_embed(
                "Invalid page number.\n\n**Usage:** `.ranks [page]`  *(1–40)*"
            ))
        else:
            raise error

    # ────────────────────────────────────────────────────────────────────────

    @commands.command(
        name="profile",
        aliases=["p"],
        brief="Show a player's public profile.",
        help=(
            "Displays a player's rank, points, bases, alliance, and recent battles.\n\n"
            "**Usage**\n"
            "`.profile <player>`\n\n"
            "**Example**\n"
            "`.profile DITO`"
        ),
    )
    async def profile(self, ctx: commands.Context, *, player_name: str) -> None:
        msg = await ctx.send(f"⏳ Fetching profile for **{player_name.upper()}**…")
        try:
            data = await asyncio.to_thread(fetch_player_profile, self.sc, player_name.strip())
        except Exception as e:
            await msg.edit(content=None, embed=self._error_embed(f"Failed to fetch profile.\n\n**Error:** `{e}`"))
            return

        if not data["name"]:
            await msg.edit(content=None, embed=self._error_embed(
                f"Player `{player_name.upper()}` was not found."
            ))
            return

        embed = discord.Embed(
            title=f"👤 {data['name']}",
            color=_rank_color(data["rank"]),
        )
        embed.add_field(name="🏅 Rank",     value=f"#{data['rank']}",            inline=True)
        embed.add_field(name="⚔️ Points",   value=format_number(data["points"]), inline=True)
        embed.add_field(name="🏰 Bases",    value=format_number(data["bases"]),  inline=True)
        embed.add_field(name="🤝 Alliance", value=data["alliance"] or "—",       inline=True)

        if data["battles"]:
            lines = []
            for b in data["battles"][:8]:
                lines.append(
                    f"`{b['date']} {b['time']}` "
                    f"**{b['attacker']}** → **{b['defender']}**  on {b['map']}"
                )
            embed.add_field(name="⚔️ Recent Battles", value="\n".join(lines), inline=False)

        embed.set_footer(text="strategycombat.com")
        await msg.edit(content=None, embed=embed)

    @profile.error
    async def profile_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(embed=self._error_embed(
                f"Missing required argument: `{error.param.name}`\n\n**Usage:** `.profile <player>`"
            ))
        else:
            raise error

    # ────────────────────────────────────────────────────────────────────────

    @commands.command(
        name="allyrank",
        aliases=["topally", "allies"],
        brief="Show top alliances ranked by total points.",
        help=(
            "Displays the alliance rankings chart.\n\n"
            "**Usage**\n"
            "`.allyrank [count]`\n\n"
            "**Example**\n"
            "`.allyrank 10`   — show top 10 alliances"
        ),
    )
    async def allyrank(self, ctx: commands.Context, count: int = 20) -> None:
        count = max(5, min(count, 50))
        msg   = await ctx.send(f"⏳ Fetching top {count} alliances…")

        try:
            alliances = await asyncio.to_thread(fetch_alliances, self.sc)
        except Exception as e:
            await msg.edit(content=None, embed=self._error_embed(f"Failed to fetch alliances.\n\n**Error:** `{e}`"))
            return

        if not alliances:
            await msg.edit(content=None, embed=self._error_embed("No data returned."))
            return

        alliances = alliances[:count]
        embed     = discord.Embed(title=f"🏰 Top {count} Alliances", color=GOLD)

        lines = []
        for a in alliances:
            lines.append(
                f"`{a['rank']:>3}.` **{a['name']}**  "
                f"{format_number(a['points'])} pts · "
                f"{a['members']} mbrs · "
                f"🗺️ {a['maps']}"
            )

        embed.add_field(name="\u200b", value="\n".join(lines[:15]), inline=False)
        if len(lines) > 15:
            embed.add_field(name="\u200b", value="\n".join(lines[15:]), inline=False)

        embed.set_footer(text="strategycombat.com  ·  .ally <name or ID> for full detail")
        await msg.edit(content=None, embed=embed)

    @allyrank.error
    async def allyrank_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        if isinstance(error, commands.BadArgument):
            await ctx.send(embed=self._error_embed(
                "Invalid count.\n\n**Usage:** `.allyrank [count]`  *(5–50)*"
            ))
        else:
            raise error

    # ────────────────────────────────────────────────────────────────────────

    @commands.command(
        name="ally",
        aliases=["alliance"],
        brief="Show full info and member list for an alliance.",
        help=(
            "Fetches an alliance's full profile: stats, leader, co-leaders, and all members.\n\n"
            "**Usage**\n"
            "`.ally <name>`       — search by name\n"
            "`.ally <id>`         — look up by numeric alliance ID\n\n"
            "**Examples**\n"
            "`.ally DITO`\n"
            "`.ally 515`"
        ),
    )
    async def ally(self, ctx: commands.Context, *, query: str) -> None:
        msg     = await ctx.send(f"⏳ Looking up alliance **{query}**…")
        ally_id = None

        if query.strip().isdigit():
            ally_id = int(query.strip())
        else:
            try:
                alliances = await asyncio.to_thread(fetch_alliances, self.sc)
            except Exception as e:
                await msg.edit(content=None, embed=self._error_embed(f"Failed to fetch alliances.\n\n**Error:** `{e}`"))
                return

            name_upper = query.strip().upper()
            for a in alliances:
                if a["name"].upper() == name_upper:
                    ally_id = a["ally_id"]
                    break

            if ally_id is None:
                matches = [a for a in alliances if name_upper in a["name"].upper()]
                if len(matches) == 1:
                    ally_id = matches[0]["ally_id"]
                elif len(matches) > 1:
                    names = ", ".join(f"`{a['name']}`" for a in matches[:8])
                    await msg.edit(content=None, embed=self._error_embed(
                        f"Multiple matches found: {names}\n\nPlease be more specific or use the alliance ID."
                    ))
                    return
                else:
                    await msg.edit(content=None, embed=self._error_embed(
                        f"Alliance `{query}` not found in the rankings.\n\n"
                        "Try using the alliance ID (numeric) directly."
                    ))
                    return

        try:
            data = await asyncio.to_thread(fetch_alliance_detail, self.sc, ally_id)
        except Exception as e:
            await msg.edit(content=None, embed=self._error_embed(f"Failed to fetch alliance.\n\n**Error:** `{e}`"))
            return

        if not data["name"] and not data["members"]:
            await msg.edit(content=None, embed=self._error_embed(
                f"No data found for alliance ID `{ally_id}`."
            ))
            return

        embed = discord.Embed(
            title=f"🏰 {data['name'] or f'Alliance #{ally_id}'}",
            color=GOLD,
        )
        embed.add_field(name="⚔️ Points",   value=format_number(data["points"]),              inline=True)
        embed.add_field(name="🏰 Bases",    value=format_number(data["bases"]),               inline=True)
        embed.add_field(name="🗺️ Maps",     value=str(data["maps"]),                          inline=True)
        embed.add_field(name="👥 Members",  value=f"{data['member_count']}/{data['max_members']}", inline=True)
        embed.add_field(name="🌐 Language", value=data["language"] or "?",                    inline=True)
        embed.add_field(name="📋 Req.",     value=data["requirements"] or "?",                inline=True)
        embed.add_field(name="👑 Leader",   value=data["leader"] or "?",                      inline=True)
        if data["democracy"]:
            embed.add_field(name="🗳️ Gov.", value="Democracy",                                inline=True)
        if data["co_leaders"]:
            embed.add_field(
                name=f"⭐ Co-Leaders ({len(data['co_leaders'])})",
                value=", ".join(data["co_leaders"]),
                inline=False,
            )

        if data["members"]:
            member_lines = []
            for m in data["members"][:20]:
                role_icon = "👑" if m["role"] == "Leader" else ("⭐" if "Co" in m["role"] else "▫️")
                member_lines.append(
                    f"{role_icon} `#{m['rank']:>4}` **{m['name']}**  "
                    f"{format_number(m['points'])} pts · "
                    f"{format_number(m['bases'])} bases"
                )
            embed.add_field(
                name=f"👥 Members ({len(data['members'])} total)",
                value="\n".join(member_lines[:15]),
                inline=False,
            )
            if len(member_lines) > 15:
                embed.add_field(name="\u200b", value="\n".join(member_lines[15:20]), inline=False)

        footer = "strategycombat.com"
        if len(data["members"]) > 20:
            footer = f"Showing top 20 of {len(data['members'])} members  ·  {footer}"
        embed.set_footer(text=footer)
        await msg.edit(content=None, embed=embed)

    @ally.error
    async def ally_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(embed=self._error_embed(
                f"Missing required argument: `{error.param.name}`\n\n**Usage:** `.ally <name or ID>`"
            ))
        else:
            raise error


# ── Setup ────────────────────────────────────────────────────────────────────

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Charts(bot))
