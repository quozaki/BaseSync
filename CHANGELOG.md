# Changelog

All notable changes to ORACLE Bot will be documented here.

---

## [v2.1.0] — 2026/05/16

### ✨ New Features
- `.ranks` — Added ◀ ▶ pagination buttons to browse all 40 pages live without retyping the command. Buttons disable at page boundaries and expire after 2 minutes
- `.ally` — Member list now paginated (15 per page) with ◀ ▶ buttons and a center label showing current page. Alliances with ≤15 members skip pagination
- `.profile` — Embed title is now a clickable hyperlink linking directly to the player's in-game profile page

### 🐛 Bug Fixes
- Fixed co-leaders not showing fully in `.ally` — each co-leader now correctly extracted from their own row in the members table
- Fixed ghost row (`▫️ # 0  0 pts · 0 bases`) appearing at the bottom of every `.ally` — member rows with rank 0 are now skipped
- Fixed `.allyrank <count>` hanging when count exceeds available alliances — now caps to actual results returned

---

## [v2.0.0] — 2026/05/15

### ✨ New Features
- `.ranks [page]` — Player rankings pulled live from the game, 25 players per page, up to top 1000 (40 pages)
- `.profile <player>` — Full public player profile including rank, points, bases, alliance and recent battles
- `.allyrank [count]` — Top alliances ranked by total points, configurable count
- `.ally <name|id>` — Full alliance detail: stats, language, requirements, leader, co-leaders and complete member list

### 🏗️ Architecture
- Merged **BaseSync** and **SC Charts** into a single unified bot under the ORACLE name
- Charts scraper isolated in `utils/scraper.py` — clean separation from bot logic
- Charts commands live in `cogs/Charts/charts.py` — fully integrated into the existing cog system
- Single `.env` file manages both Discord token and SC credentials
- All existing BaseSync cogs untouched and fully compatible

### 🔐 Authentication
- Auto-login to Strategy Combat on bot startup via session cookie
- Session is shared across all chart commands — no repeated logins per command
- Credentials stored securely via `.env` — never hardcoded

### 📦 Dependencies Added
- `requests` — HTTP session management for scraping
- `beautifulsoup4` — HTML parsing for all chart pages

---

## [v1.0.0] — BaseSync Initial Release

- `.ping` — Latency check
- `.mb` — Max bases calculator
- `.sync` — Sync system command
- `.unitinfo` — Unit info lookup
- Cog auto-loader on startup
- Custom help command
- Hot reload via `.reloadcog`