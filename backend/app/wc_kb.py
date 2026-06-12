"""WC-2026 knowledge base — authoritative facts the chatbot can answer
without spending a web search: format/rules, venues, schedule, hosts.
Keyword-matched topics keep it cheap and grounded.
"""
from .venue_data import VENUES

FACTS = {
    "format": (
        "World Cup 2026: 48 teams, 12 groups (A–L) of 4. Top 2 of each group + "
        "the 8 best third-placed teams = 32 → Round of 32 → R16 → Quarter-finals "
        "→ Semi-finals → Final. 104 matches total, 11 Jun – 19 Jul 2026."),
    "thirds": (
        "8 of the 12 third-placed teams advance. They are ranked across groups by "
        "points, then goal difference, goals scored, then disciplinary/draw of lots; "
        "the qualifying combination is mapped to fixed Round-of-32 slots by an "
        "official FIFA table."),
    "tiebreakers": (
        "Group tiebreakers in order: points → goal difference → goals scored → "
        "head-to-head (points, GD, goals) → fair-play → drawing of lots."),
    "knockout_rules": (
        "Knockouts are single-elimination; a tie after 90' goes to 30' extra time, "
        "then a penalty shootout. No away-goals rule."),
    "hosts": (
        "Hosted by the USA (11 venues), Mexico (3: Mexico City, Guadalajara, "
        "Monterrey) and Canada (2: Toronto, Vancouver) — 16 stadiums."),
    "final": "The Final is on 19 July 2026 at MetLife Stadium, New York/New Jersey.",
    "opening": "The opening match was 11 June 2026 at Estadio Azteca, Mexico City (Mexico vs South Africa).",
    "dates": "Group stage 11–27 Jun; Round of 32 28 Jun–3 Jul; R16 4–7 Jul; QF 9–11 Jul; SF 14–15 Jul; Final 19 Jul.",
}


def _venues_summary() -> str:
    by_alt = sorted(VENUES.values(), key=lambda v: -v["alt"])
    seen, lines = set(), []
    for v in by_alt:
        if v["stadium"] in seen:
            continue
        seen.add(v["stadium"])
        roof = "roof/AC" if v["roof"] else "open-air"
        lines.append(f"{v['city']} — {v['stadium']} (cap {v['cap']:,}, "
                     f"{v['alt']}m, {roof})")
    return "16 venues (highest altitude first): " + "; ".join(lines)


def lookup(topic: str) -> dict:
    """Return KB facts relevant to a topic keyword."""
    t = (topic or "").lower()
    hits = {}
    kmap = {
        "format": ["format", "thể thức", "how many", "groups", "bảng", "structure"],
        "thirds": ["third", "đội ba", "best third", "8 đội"],
        "tiebreakers": ["tiebreak", "xếp hạng", "bằng điểm", "tie"],
        "knockout_rules": ["knockout", "extra time", "hiệp phụ", "luân lưu", "penalt", "loại trực tiếp"],
        "hosts": ["host", "chủ nhà", "country", "quốc gia", "where"],
        "final": ["final", "chung kết"],
        "opening": ["opening", "khai mạc", "first match"],
        "dates": ["date", "ngày", "schedule", "lịch", "when", "khi nào"],
    }
    for key, kws in kmap.items():
        if any(k in t for k in kws):
            hits[key] = FACTS[key]
    if any(k in t for k in ["venue", "stadium", "sân", "altitude", "độ cao", "city", "thành phố"]):
        hits["venues"] = _venues_summary()
    if not hits:        # no keyword matched → give the essentials
        hits = {"format": FACTS["format"], "dates": FACTS["dates"],
                "hosts": FACTS["hosts"]}
    return hits
