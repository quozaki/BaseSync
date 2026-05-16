"""
Strategy Combat Scraper
Handles login (session cookie) and scraping of all public chart pages.
"""

import re
import math
import time
import hashlib
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.strategycombat.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": BASE_URL + "/",
}


# ─────────────────────────────────────────────
#  Fingerprint helper (mirrors gmnf() in JS)
# ─────────────────────────────────────────────

def _mdjs3(a: int, b: int) -> int:
    """Mirrors the JS: (a << 5) - a + b  (32-bit signed)"""
    val = ((a << 5) - a + b) & 0xFFFFFFFF
    # Sign-extend to 32-bit signed
    if val >= 0x80000000:
        val -= 0x100000000
    return val


def make_gmnf(tz_offset: int = 0, width: int = 1920, height: int = 1080, dpr: float = 1.0) -> int:
    """
    Recreates the browser fingerprint the game expects.
    Values don't have to be exact – the server just uses this as a soft
    anti-bot check; a stable value is enough.
    """
    canvas_stub = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAoAAAA"
    s = canvas_stub
    s += "Mozilla/5.0"           # navigator.userAgent
    s += str(tz_offset)          # new Date().getTimezoneOffset()
    s += str(int(width * dpr))   # clientWidth * devicePixelRatio
    s += str(int(height * dpr))  # clientHeight * devicePixelRatio
    # hardwareConcurrency / deviceMemory / plugins are optional (try/catch in JS)

    h = 0
    for ch in s:
        h = _mdjs3(h, ord(ch))
    return h


# ─────────────────────────────────────────────
#  Session / Login
# ─────────────────────────────────────────────

class SCSession:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self._logged_in = False

    def _get_login_token(self) -> str:
        """Fetch the login page and extract the hidden `dnh` token."""
        r = self.session.get(BASE_URL + "/", timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        dnh_input = soup.find("input", {"id": "dnh"})
        if dnh_input:
            return dnh_input.get("value", "")
        return ""

    def login(self, username: str, password: str) -> bool:
        """
        Log in with username / password.
        Returns True on success, False on failure.
        """
        dnh = self._get_login_token()
        gmnf = make_gmnf()
        # CET offset: we pass 50 + getCETHourOffset(); 50+1=51 for CET+1
        myzz = 51

        payload = {
            "loginname": username,
            "loginpass": password,
            "gmnf": gmnf,
            "myzz": myzz,
            "logincap": "",
            "dnh": dnh,
            "logince": "",
            "logincc": "",
        }

        r = self.session.post(
            BASE_URL + "/?sh=Y",
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=15,
        )
        r.raise_for_status()

        resp = r.text
        # Server responds "N@<code>" on failure or starts with "F@" / HTML on success
        if resp.startswith("N@"):
            return False

        self._logged_in = True
        return True

    def get(self, url: str, **kwargs) -> requests.Response:
        if not self._logged_in:
            raise RuntimeError("Not logged in.")
        return self.session.get(url, timeout=15, **kwargs)


# ─────────────────────────────────────────────
#  Parsers
# ─────────────────────────────────────────────

def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


def parse_players_chart(html: str) -> list[dict]:
    """
    Parse charts.php?s=N
    Returns list of:
      { rank, points, bases, name, alliance }
    """
    soup = _soup(html)
    table = soup.find("table", class_="allyprofil")
    if not table:
        return []

    players = []
    for row in table.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 7:
            continue
        # Skip header row (contains text "Rank")
        if cells[0].get_text(strip=True) == "Rank":
            continue
        try:
            rank    = int(cells[0].get_text(strip=True))
            points  = cells[2].get_text(strip=True).replace("'", "").replace(".", "")
            bases   = cells[4].get_text(strip=True).replace("'", "").replace(".", "")
            name    = cells[6].get_text(strip=True)
            alliance = cells[8].get_text(strip=True) if len(cells) > 8 else ""
            players.append({
                "rank": rank,
                "points": int(points) if points.isdigit() else 0,
                "bases": int(bases) if bases.isdigit() else 0,
                "name": name,
                "alliance": alliance,
            })
        except (ValueError, IndexError):
            continue
    return players


def parse_alliances_chart(html: str) -> list[dict]:
    """
    Parse ally.php?a=2
    Returns list of:
      { rank, name, ally_id, points, bases, members, language, maps, requirements }
    """
    soup = _soup(html)
    table = soup.find("table", class_="allyprofil")
    if not table:
        return []

    alliances = []
    for row in table.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 5:
            continue
        # First cell is flag/link, second is rank number
        try:
            rank_text = cells[1].get_text(strip=True)
            rank = int(rank_text)
        except (ValueError, IndexError):
            continue

        try:
            # Name cell (cells[2]) contains <a href="ally.php?b=ID"><b>NAME</b></a>
            name_tag = cells[2].find("a")
            name = name_tag.get_text(strip=True) if name_tag else cells[2].get_text(strip=True)
            href = name_tag.get("href", "") if name_tag else ""
            ally_id_match = re.search(r"\?b=(\d+)", href)
            ally_id = int(ally_id_match.group(1)) if ally_id_match else None

            # Points / Bases / Members
            points = cells[3].get_text(strip=True).replace(".", "").replace("'", "")
            bases  = cells[4].get_text(strip=True).replace(".", "").replace("'", "")
            members = cells[5].get_text(strip=True).replace(".", "") if len(cells) > 5 else "?"

            # Details cell (cells[6]) contains language, maps, requirements
            details_text = cells[6].get_text(" ", strip=True) if len(cells) > 6 else ""
            lang_match = re.search(r"Alliance language:\s*\S+\s+(\w+)", details_text)
            lang = lang_match.group(1) if lang_match else "?"
            maps_match = re.search(r"Conquered Maps:\s*(\d+)", details_text)
            maps = int(maps_match.group(1)) if maps_match else 0
            req_match = re.search(r"Requirements:\s*([\d.,]+)", details_text)
            requirements = req_match.group(1) if req_match else "?"

            alliances.append({
                "rank": rank,
                "name": name,
                "ally_id": ally_id,
                "points": int(points) if points.isdigit() else 0,
                "bases": int(bases) if bases.isdigit() else 0,
                "members": int(members) if members.isdigit() else 0,
                "language": lang,
                "maps": maps,
                "requirements": requirements,
            })
        except (ValueError, IndexError, AttributeError):
            continue

    return alliances


def parse_alliance_detail(html: str) -> dict:
    """
    Parse ally.php?b=ID
    Returns:
      {
        name, language, points, bases, maps, member_count, max_members,
        requirements, democracy, leader, co_leaders,
        members: [ {name, points, bases, rank, role} ]
      }
    """
    soup = _soup(html)
    tables = soup.find_all("table", class_="allyprofil")

    result = {
        "name": "", "language": "", "points": 0, "bases": 0,
        "maps": 0, "member_count": 0, "max_members": 30,
        "requirements": "", "democracy": False,
        "leader": "", "co_leaders": [], "members": []
    }

    # The page has two tables side by side inside a <td>
    # Left table: member list | Right table: alliance info
    # We'll parse all allyprofil tables

    for table in tables:
        rows = table.find_all("tr")
        if not rows:
            continue

        # Detect if this is the info table (has "Name of Alliance:" in first row)
        first_row_text = rows[0].get_text(" ", strip=True) if rows else ""
        if "Name of Alliance" in first_row_text or any("Name of Alliance" in r.get_text() for r in rows):
            # Info table
            for row in rows:
                cells = row.find_all("td")
                if len(cells) < 2:
                    continue
                key = cells[0].get_text(strip=True).lower().rstrip(":")
                val = cells[1].get_text(strip=True)

                if "name of alliance" in key:
                    result["name"] = val
                elif "language" in key:
                    result["language"] = val
                elif key == "points":
                    result["points"] = int(val.replace(".", "").replace("'", "")) if re.search(r"\d", val) else 0
                elif key == "bases":
                    result["bases"] = int(val.replace(".", "").replace("'", "")) if re.search(r"\d", val) else 0
                elif "conquered maps" in key:
                    result["maps"] = int(val) if val.isdigit() else 0
                elif "memb" in key and "newcomer" not in key:
                    m = re.search(r"(\d+)", val)
                    result["member_count"] = int(m.group(1)) if m else 0
                elif "minimum" in key or "requirement" in key:
                    result["requirements"] = val
                elif "democracy" in key:
                    result["democracy"] = val.upper() == "YES"
                elif "leader" in key and "co-leader" not in key:
                    result["leader"] = val
                elif "co-leader" in key or "co-lead" in key:
                    # Each co-leader has its own <tr> — just append the cell value
                    if val:
                        result["co_leaders"].append(val)
        else:
            # Member list table
            # Header row has: (empty), Name, Points, Bases, Rank, (empty), (empty), Role
            for row in rows:
                cells = row.find_all("td")
                if len(cells) < 5:
                    continue
                name_tag = cells[1].find("a")
                if not name_tag:
                    continue
                name = name_tag.get_text(strip=True)
                if not name:
                    continue
                points_text = cells[2].get_text(strip=True).replace(".", "").replace("'", "")
                bases_text  = cells[3].get_text(strip=True).replace(".", "").replace("'", "")
                rank_text   = cells[4].get_text(strip=True).replace(".", "").replace("'", "")
                role        = cells[7].get_text(strip=True) if len(cells) > 7 else ""

                rank = int(rank_text) if rank_text.isdigit() else 0
                if rank == 0:
                    continue  # skip ghost/header rows
                result["members"].append({
                    "name": name,
                    "points": int(points_text) if points_text.isdigit() else 0,
                    "bases": int(bases_text) if bases_text.isdigit() else 0,
                    "rank": rank,
                    "role": role,
                })

    # Sort members by rank
    result["members"].sort(key=lambda m: m["rank"] if m["rank"] > 0 else 99999)

    # Extract leader and co-leaders from the members list (more reliable than info table)
    result["co_leaders"] = [
        m["name"] for m in result["members"] if "co" in m["role"].lower()
    ]
    if not result["leader"]:
        leaders = [m["name"] for m in result["members"] if m["role"].lower() == "leader"]
        if leaders:
            result["leader"] = leaders[0]

    return result


def parse_player_profile(html: str) -> dict:
    """
    Parse charts.php?a=PLAYERNAME
    Returns:
      { name, alliance, ally_id, points, bases, rank, battles: [...] }
    """
    soup = _soup(html)
    result = {
        "name": "", "alliance": "", "ally_id": None,
        "points": 0, "bases": 0, "rank": 0, "battles": []
    }

    profile_table = soup.find("table", class_="allyprofil")
    if profile_table:
        for row in profile_table.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) < 2:
                continue
            key = cells[0].get_text(strip=True).lower().rstrip(":")
            val_cell = cells[1]
            val = val_cell.get_text(strip=True)

            if key == "name":
                result["name"] = val
            elif key == "alliance":
                result["alliance"] = val
                link = val_cell.find("a")
                if link:
                    m = re.search(r"\?b=(\d+)", link.get("href", ""))
                    if m:
                        result["ally_id"] = int(m.group(1))
            elif key == "points":
                result["points"] = int(val.replace("'", "").replace(".", "")) if re.search(r"\d", val) else 0
            elif key == "bases":
                result["bases"] = int(val.replace("'", "").replace(".", "")) if re.search(r"\d", val) else 0
            elif "rank" in key:
                result["rank"] = int(val) if val.isdigit() else 0

    # Battles table
    battles_div = soup.find("div", style=lambda s: s and "background-color" in s)
    if battles_div:
        for row in battles_div.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) < 6:
                continue
            date     = cells[0].get_text(strip=True)
            time_str = cells[1].get_text(strip=True)
            map_name = cells[2].get_text(strip=True)
            attacker = cells[3].get_text(strip=True)
            action   = cells[4].get_text(strip=True)
            defender = cells[5].get_text(strip=True)
            if date and map_name:
                result["battles"].append({
                    "date": date, "time": time_str, "map": map_name,
                    "attacker": attacker, "action": action, "defender": defender,
                })

    return result


# ─────────────────────────────────────────────
#  High-level fetch helpers (used by the bot)
# ─────────────────────────────────────────────

def fetch_players_page(session: SCSession, start: int) -> list[dict]:
    """Fetch one page of the player chart (start = 1, 26, 51, ...)."""
    url = f"{BASE_URL}/charts.php?s={start}"
    r = session.get(url)
    r.raise_for_status()
    return parse_players_chart(r.text)


def fetch_all_players(session: SCSession, max_pages: int = 40) -> list[dict]:
    """Fetch all 40 pages (1000 players). Warning: takes ~40 HTTP requests."""
    all_players = []
    for i in range(max_pages):
        start = i * 25 + 1
        try:
            page_players = fetch_players_page(session, start)
            all_players.extend(page_players)
            time.sleep(0.3)  # Be polite
        except Exception:
            break
    return all_players


def fetch_alliances(session: SCSession) -> list[dict]:
    """Fetch the alliances ranking chart."""
    r = session.get(f"{BASE_URL}/ally.php?a=2")
    r.raise_for_status()
    return parse_alliances_chart(r.text)


def fetch_alliance_detail(session: SCSession, ally_id: int) -> dict:
    """Fetch a single alliance's detail page."""
    r = session.get(f"{BASE_URL}/ally.php?b={ally_id}")
    r.raise_for_status()
    return parse_alliance_detail(r.text)


def fetch_player_profile(session: SCSession, name: str) -> dict:
    """Fetch a player's public profile."""
    r = session.get(f"{BASE_URL}/charts.php?a={name.upper()}")
    r.raise_for_status()
    return parse_player_profile(r.text)


def format_number(n: int) -> str:
    """Format large numbers with commas: 21147808 → 21,147,808"""
    return f"{n:,}"