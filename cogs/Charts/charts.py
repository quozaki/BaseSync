"""
Charts Cog — Strategy Combat public chart commands.
Scrapes strategycombat.com using a shared authenticated session.

Commands:
  .ranks [page]       — Player rankings (25/page, up to page 40) with pagination buttons
  .profile <player>   — Public player profile with link to game
  .allyrank [count]   — Top alliances by points
  .ally <name|id>     — Full alliance detail + paginated member list
"""

import os
import asyncio

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

BASE_URL    = "https://www.strategycombat.com"
TIMEOUT     = 120   # seconds before pagination buttons expire

# ── Colours ──────────────────────────────────────────────────────────────────
GOLD        = 0xFFAA33
YELLOW      = 0xFFFF99
CYAN        = 0x00CCFF
GREEN       = 0x55CC55
GREY        = 0xAAAAAA
COLOR_ERROR = 0xE74C3C

def _rank_color(rank: int) -> int:
    if rank == 1:    return GOLD
    if rank <= 10:   return YELLOW
    if rank <= 25:   return CYAN
    if rank <= 100:  return GREEN
    return GREY


# ── Pagination Views ─────────────────────────────────────────────────────────

class RanksPaginator(discord.ui.View):
    """Prev / Next buttons for .ranks — fetches each page on demand."""

    def __init__(self, sc: SCSession, page: int, author_id: int) -> None:
        super().__init__(timeout=TIMEOUT)
        self.sc        = sc
        self.page      = page
        self.author_id = author_id
        self._update_buttons()

    def _update_buttons(self) -> None:
        self.prev_btn.disabled = self.page <= 1
        self.next_btn.disabled = self.page >= 40
        self.prev_btn.label    = f"◀  Page {self.page - 1}" if self.page > 1  else "◀"
        self.next_btn.label    = f"Page {self.page + 1}  ▶" if self.page < 40 else "▶"

    def _build_embed(self, players: list) -> discord.Embed:
        start = (self.page - 1) * 25 + 1
        embed = discord.Embed(
            title=f"🏆 Player Rankings — Page {self.page}  (#{start}–#{start + 24})",
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
        embed.add_field(name="\u200b", value="\n".join(lines[:13]), inline=False)
        if len(lines) > 13:
            embed.add_field(name="\u200b", value="\n".join(lines[13:]), inline=False)
        embed.set_footer(text=f"Page {self.page} / 40  ·  strategycombat.com")
        return embed

    async def _go_to(self, interaction: discord.Interaction, new_page: int) -> None:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("These buttons aren't yours!", ephemeral=True)
            return
        self.page = new_page
        self._update_buttons()
        start   = (self.page - 1) * 25 + 1
        players = await asyncio.to_thread(fetch_players_page, self.sc, start)
        embed   = self._build_embed(players)
        await interaction.response.edit_message(embed=embed, view=self)

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary)
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._go_to(interaction, self.page - 1)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary)
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._go_to(interaction, self.page + 1)


class AllyMembersPaginator(discord.ui.View):
    """Page 1 / Page 2 buttons for .ally member list."""

    def __init__(self, info_embed: discord.Embed, pages: list,
                 ally_name: str, author_id: int) -> None:
        super().__init__(timeout=TIMEOUT)
        self.info_embed = info_embed
        self.pages      = pages
        self.ally_name  = ally_name
        self.author_id  = author_id
        self.current    = 0
        self._update_buttons()

    def _update_buttons(self) -> None:
        self.prev_btn.disabled = self.current == 0
        self.next_btn.disabled = self.current >= len(self.pages) - 1
        self.page_btn.label    = f"Members  {self.current + 1}/{len(self.pages)}"

    def _build_embed(self) -> discord.Embed:
        embed = self.info_embed.copy()
        embed.add_field(
            name=f"👥 Members — Page {self.current + 1}/{len(self.pages)}",
            value="\n".join(self.pages[self.current]),
            inline=False,
        )
        return embed

    async def _go_to(self, interaction: discord.Interaction, idx: int) -> None:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("These buttons aren't yours!", ephemeral=True)
            return
        self.current = idx
        self._update_buttons()
        await interaction.response.edit_message(embed=self._build_embed(), view=self)

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary)
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._go_to(interaction, self.current - 1)

    @discord.ui.button(label="Members  1/1", style=discord.ButtonStyle.primary, disabled=True)
    async def page_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        pass  # Label-only indicator

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary)
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._go_to(interaction, self.current + 1)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _chunk_lines(lines: list, per_page: int = 15) -> list:
    """Split a flat list of lines into pages of `per_page` items."""
    return [lines[i:i + per_page] for i in range(0, len(lines), per_page)] if lines else [[]]

def _error_embed(description: str) -> discord.Embed:
    return discord.Embed(title="❌ Error", description=description, color=COLOR_ERROR)


# ── Cog ───────────────────────────────────────────────────────────────────────

class Charts(commands.Cog):
    """Live charts and player/alliance lookups from Strategy Combat."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.sc  = SCSession()

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

    # ── .ranks ───────────────────────────────────────────────────────────────

    @commands.command(
        name="ranks",
        aliases=["top25"],
        brief="Show player rankings with navigation buttons.",
        help=(
            "Shows 25 players per page with ◀ ▶ buttons to browse all 40 pages.\n\n"
            "**Usage**\n"
            "`.ranks [page]`\n\n"
            "**Examples**\n"
            "`.ranks`      — start at page 1 (#1–#25)\n"
            "`.ranks 5`    — start at page 5 (#101–#125)"
        ),
    )
    async def ranks(self, ctx: commands.Context, page: int = 1) -> None:
        if not 1 <= page <= 40:
            await ctx.send(embed=_error_embed("Page must be between **1** and **40**."))
            return

        msg   = await ctx.send(f"⏳ Fetching player ranks (page {page})…")
        start = (page - 1) * 25 + 1

        try:
            players = await asyncio.to_thread(fetch_players_page, self.sc, start)
        except Exception as e:
            await msg.edit(content=None, embed=_error_embed(f"Failed to fetch data.\n\n**Error:** `{e}`"))
            return

        if not players:
            await msg.edit(content=None, embed=_error_embed(
                "No data returned. The session may have expired — try `.reloadcog charts.charts`."
            ))
            return

        view  = RanksPaginator(self.sc, page, ctx.author.id)
        embed = view._build_embed(players)
        await msg.edit(content=None, embed=embed, view=view)

    @ranks.error
    async def ranks_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        if isinstance(error, commands.BadArgument):
            await ctx.send(embed=_error_embed("Invalid page number.\n\n**Usage:** `.ranks [page]`  *(1–40)*"))
        else:
            raise error

    # ── .profile ─────────────────────────────────────────────────────────────

    @commands.command(
        name="profile",
        aliases=["p"],
        brief="Show a player's public profile.",
        help=(
            "Displays a player's rank, points, bases, alliance, and recent battles.\n"
            "The player name in the embed is a clickable link to their in-game profile.\n\n"
            "**Usage**\n"
            "`.profile <player>`\n\n"
            "**Example**\n"
            "`.profile DITO`"
        ),
    )
    async def profile(self, ctx: commands.Context, *, player_name: str) -> None:
        name_upper = player_name.strip().upper()
        msg = await ctx.send(f"⏳ Fetching profile for **{name_upper}**…")
        try:
            data = await asyncio.to_thread(fetch_player_profile, self.sc, player_name.strip())
        except Exception as e:
            await msg.edit(content=None, embed=_error_embed(f"Failed to fetch profile.\n\n**Error:** `{e}`"))
            return

        if not data["name"]:
            await msg.edit(content=None, embed=_error_embed(f"Player `{name_upper}` was not found."))
            return

        profile_url = f"{BASE_URL}/charts.php?a={data['name']}"
        embed = discord.Embed(
            title=f"👤 {data['name']}",
            url=profile_url,
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

        embed.set_footer(text="Click the title to open in-game profile  ·  strategycombat.com")
        await msg.edit(content=None, embed=embed)

    @profile.error
    async def profile_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(embed=_error_embed(
                f"Missing required argument: `{error.param.name}`\n\n**Usage:** `.profile <player>`"
            ))
        else:
            raise error

    # ── .allyrank ─────────────────────────────────────────────────────────────

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
            await msg.edit(content=None, embed=_error_embed(f"Failed to fetch alliances.\n\n**Error:** `{e}`"))
            return

        if not alliances:
            await msg.edit(content=None, embed=_error_embed("No data returned."))
            return

        actual    = min(count, len(alliances))
        alliances = alliances[:actual]
        embed     = discord.Embed(title=f"🏰 Top {actual} Alliances", color=GOLD)

        lines = [
            f"`{a['rank']:>3}.` **{a['name']}**  "
            f"{format_number(a['points'])} pts · "
            f"{a['members']} mbrs · "
            f"🗺️ {a['maps']}"
            for a in alliances
        ]

        embed.add_field(name="\u200b", value="\n".join(lines[:15]), inline=False)
        if len(lines) > 15:
            embed.add_field(name="\u200b", value="\n".join(lines[15:]), inline=False)

        embed.set_footer(text="strategycombat.com  ·  .ally <name or ID> for full detail")
        await msg.edit(content=None, embed=embed)

    @allyrank.error
    async def allyrank_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        if isinstance(error, commands.BadArgument):
            await ctx.send(embed=_error_embed("Invalid count.\n\n**Usage:** `.allyrank [count]`  *(5–50)*"))
        else:
            raise error

    # ── .ally ─────────────────────────────────────────────────────────────────

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
                await msg.edit(content=None, embed=_error_embed(f"Failed to fetch alliances.\n\n**Error:** `{e}`"))
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
                    await msg.edit(content=None, embed=_error_embed(
                        f"Multiple matches found: {names}\n\nPlease be more specific or use the alliance ID."
                    ))
                    return
                else:
                    await msg.edit(content=None, embed=_error_embed(
                        f"Alliance `{query}` not found in the rankings.\n\n"
                        "Try using the alliance ID (numeric) directly."
                    ))
                    return

        try:
            data = await asyncio.to_thread(fetch_alliance_detail, self.sc, ally_id)
        except Exception as e:
            await msg.edit(content=None, embed=_error_embed(f"Failed to fetch alliance.\n\n**Error:** `{e}`"))
            return

        if not data["name"] and not data["members"]:
            await msg.edit(content=None, embed=_error_embed(f"No data found for alliance ID `{ally_id}`."))
            return

        # ── Info embed (no members yet) ──────────────────────────────────────
        info_embed = discord.Embed(
            title=f"🏰 {data['name'] or f'Alliance #{ally_id}'}",
            color=GOLD,
        )
        info_embed.add_field(name="⚔️ Points",   value=format_number(data["points"]),                   inline=True)
        info_embed.add_field(name="🏰 Bases",    value=format_number(data["bases"]),                    inline=True)
        info_embed.add_field(name="🗺️ Maps",     value=str(data["maps"]),                               inline=True)
        info_embed.add_field(name="👥 Members",  value=f"{data['member_count']}/{data['max_members']}", inline=True)
        info_embed.add_field(name="🌐 Language", value=data["language"] or "?",                         inline=True)
        info_embed.add_field(name="📋 Req.",     value=data["requirements"] or "?",                     inline=True)
        info_embed.add_field(name="👑 Leader",   value=data["leader"] or "?",                           inline=True)
        if data["democracy"]:
            info_embed.add_field(name="🗳️ Gov.", value="Democracy", inline=True)
        if data["co_leaders"]:
            info_embed.add_field(
                name=f"⭐ Co-Leaders ({len(data['co_leaders'])})",
                value=", ".join(data["co_leaders"]),
                inline=False,
            )
        info_embed.set_footer(text="strategycombat.com")

        # ── Member lines ─────────────────────────────────────────────────────
        member_lines = []
        for m in data["members"]:
            role_icon = "👑" if m["role"] == "Leader" else ("⭐" if "Co" in m["role"] else "▫️")
            member_lines.append(
                f"{role_icon} `#{m['rank']:>4}` **{m['name']}**  "
                f"{format_number(m['points'])} pts · "
                f"{format_number(m['bases'])} bases"
            )

        pages = _chunk_lines(member_lines, per_page=15)

        if len(pages) <= 1:
            # No pagination needed
            embed = info_embed.copy()
            if member_lines:
                embed.add_field(
                    name=f"👥 Members ({len(data['members'])} total)",
                    value="\n".join(member_lines),
                    inline=False,
                )
            await msg.edit(content=None, embed=embed)
        else:
            # Paginated
            view  = AllyMembersPaginator(info_embed, pages, data["name"], ctx.author.id)
            embed = view._build_embed()
            await msg.edit(content=None, embed=embed, view=view)

    @ally.error
    async def ally_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(embed=_error_embed(
                f"Missing required argument: `{error.param.name}`\n\n**Usage:** `.ally <name or ID>`"
            ))
        else:
            raise error


# ── Setup ─────────────────────────────────────────────────────────────────────

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Charts(bot))