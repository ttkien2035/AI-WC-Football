"""Squad-strength index: where do each squad's 26 players play their club ball?

Offline batch (run manually or from the nightly retrain hook):
    python -m ml.squad_strength

Sources
- Wikipedia "2026 FIFA World Cup squads" wikitext (player -> club), one page.
- ClubElo one-day full ranking CSV (club -> Elo), one call. Attribution:
  clubelo.com / api.clubelo.com.

ClubElo only rates EUROPEAN clubs, so each team gets a coverage fraction
(matched players / squad). The serving prior blends the squad signal by
coverage: an all-domestic squad (e.g. Qatar) simply keeps its rank-tier
baseline — no signal is invented. Output artifact:

    app/data/squad_strength.json
    {tla: {index, z, coverage, n, top_clubs}, "_meta": {...}}

`z` is the index z-scored across covered teams; engine/strength_prior.py
turns it into a bounded Elo offset on the national scale.
"""
from __future__ import annotations

import json
import re
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.static_data import TEAMS  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "app" / "data" / "squad_strength.json"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}

# Wikipedia section title -> TLA (where it differs from TEAMS name)
WIKI_ALIASES = {
    "czech republic": "CZE", "bosnia and herzegovina": "BIH",
    "south korea": "KOR", "united states": "USA", "ivory coast": "CIV",
    "cape verde": "CPV", "dr congo": "COD", "curaçao": "CUW", "curacao": "CUW",
    "turkey": "TUR", "türkiye": "TUR", "saudi arabia": "KSA",
    "new zealand": "NZL", "south africa": "RSA",
}
NAME_TO_TLA = {v["name"].lower(): k for k, v in TEAMS.items()} | WIKI_ALIASES

_STOP = re.compile(
    r"\b(fc|cf|afc|sc|ac|as|ssc|fk|jk|krc|rc|ogc|"
    r"sk|sl|sv|vfb|vfl|tsg|rb|bsc|sociedade|esportiva|club|clube|de|futebol|"
    r"futbol|cd|ca|cr|aj|og|1899|1900|1904|1907|1909|04|05|96)\b")


def _norm(club: str) -> str:
    """Normalize a club name for fuzzy matching across the two sources."""
    import unicodedata
    s = club.lower().strip()
    s = re.sub(r"\(.*?\)", " ", s)
    s = re.sub(r"[.'’]", "", s)                   # F.C. -> FC (not "f c")
    s = s.replace("&", " and ").replace("ø", "o").replace("ß", "ss").replace("ı", "i")
    s = unicodedata.normalize("NFKD", s)          # é->e´, ş->s¸ ...
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    s = _STOP.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


# manual bridges where normalization can't close the gap (Wikipedia -> ClubElo)
CLUB_ALIASES = {
    "internazionale milano": "inter",
    "inter milan": "inter",
    "bayern munich": "bayern",
    "bayern münchen": "bayern",
    "borussia mönchengladbach": "gladbach",
    "paris saint germain": "paris sg",
    "manchester united": "man united",
    "manchester city": "man city",
    "newcastle united": "newcastle",
    "tottenham hotspur": "tottenham",
    "wolverhampton wanderers": "wolves",
    "west ham united": "west ham",
    "brighton and hove albion": "brighton",
    "nottingham forest": "forest",
    "sporting cp": "sporting",
    "sporting lisbon": "sporting",
    "atletico madrid": "atletico",
    "atlético madrid": "atletico",
    "athletic bilbao": "bilbao",
    "real sociedad": "sociedad",
    "real betis": "betis",
    "slavia prague": "slavia praha",
    "sparta prague": "sparta praha",
    "viktoria plzen": "plzen",
    "viktoria plzeň": "plzen",
    "red bull salzburg": "salzburg",
    "crvena zvezda": "red star",
    "red star belgrade": "red star",
    "psv eindhoven": "psv",
    "az alkmaar": "az",
    "bayer leverkusen": "leverkusen",
    "eintracht frankfurt": "frankfurt",
    "borussia dortmund": "dortmund",
    "viktoria plzen": "viktoria plzen",
    "copenhagen": "kobenhavn",
    "kobenhavn": "kobenhavn",
    "bodo glimt": "bodoe glimt",
    "malmo ff": "malmoe",
    "malmo": "malmoe",
    "aik fotboll": "aik",
    "heart of midlothian": "hearts",
    "saint etienne": "saint etienne",
    "fortuna dusseldorf": "dusseldorf",
    "stade rennais": "rennes",
    "olympique lyonnais": "lyon",
    "olympique marseille": "marseille",
    "como 1907": "como",
    "hull city": "hull",
    "mjallby aif": "mjaellby",
    "psv eindhoven": "psv",
}


def fetch_squads() -> dict[str, list[str]]:
    """{TLA: [club, ...]} from the Wikipedia squads page wikitext.

    Wikipedia 403s httpx regardless of User-Agent (TLS fingerprinting), so
    this offline batch shells out to curl, which passes.
    """
    import subprocess
    url = ("https://en.wikipedia.org/w/api.php?action=parse"
           "&page=2026%20FIFA%20World%20Cup%20squads"
           "&prop=wikitext&format=json&formatversion=2")
    raw = subprocess.run(
        ["curl", "-s", "--max-time", "60", "-H", f"User-Agent: {UA['User-Agent']}", url],
        capture_output=True, text=True, check=True).stdout
    txt = json.loads(raw)["parse"]["wikitext"]

    out: dict[str, list[str]] = {}
    cur: str | None = None
    for line in txt.splitlines():
        m = re.match(r"^===\s*(.+?)\s*===\s*$", line)
        if m:
            name = re.sub(r"[\[\]{}]", "", m.group(1)).strip().lower()
            cur = NAME_TO_TLA.get(name)
            continue
        if cur:
            cm = re.search(r"club=\s*\[*([^|\]}\n]+)", line)
            if cm:
                out.setdefault(cur, []).append(cm.group(1).strip())
    return out


def fetch_clubelo() -> dict[str, float]:
    """{normalized club name: elo} from the one-day full-ranking CSV."""
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    r = httpx.get(f"http://api.clubelo.com/{day}", headers=UA,
                  timeout=60, follow_redirects=True)
    r.raise_for_status()
    out = {}
    for ln in r.text.splitlines()[1:]:
        f = ln.split(",")
        if len(f) >= 5 and f[1]:
            out[_norm(f[1])] = float(f[4])
    return out


def club_elo_of(club: str, table: dict[str, float]) -> float | None:
    n = _norm(club)
    n = CLUB_ALIASES.get(n, n)
    if n in table:
        return table[n]
    # containment fallback (e.g. "borussia dortmund ii" ~ "dortmund")
    for k, v in table.items():
        if k and (k in n or n in k) and min(len(k), len(n)) >= 5:
            return v
    return None


def main() -> None:
    squads = fetch_squads()
    table = fetch_clubelo()
    print(f"squads: {len(squads)} teams | clubelo clubs: {len(table)}")

    rows = {}
    for tla, clubs in sorted(squads.items()):
        elos = [(c, club_elo_of(c, table)) for c in clubs]
        hit = [(c, e) for c, e in elos if e is not None]
        cov = len(hit) / len(clubs) if clubs else 0.0
        idx = statistics.fmean(e for _, e in hit) if hit else None
        top = sorted({c: e for c, e in hit}.items(), key=lambda kv: -kv[1])[:3]
        rows[tla] = {"index": round(idx, 1) if idx else None,
                     "coverage": round(cov, 2), "n": len(clubs),
                     "top_clubs": [c for c, _ in top]}
        miss = sorted({c for c, e in elos if e is None})
        print(f"{tla}: n={len(clubs)} cov={cov:.0%} idx={idx and round(idx)}"
              f" | missing e.g. {miss[:3]}")

    covered = [v["index"] for v in rows.values()
               if v["index"] and v["coverage"] >= 0.3]
    mu, sd = statistics.fmean(covered), statistics.pstdev(covered)
    for v in rows.values():
        v["z"] = round((v["index"] - mu) / sd, 2) \
            if v["index"] and v["coverage"] >= 0.3 else None

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        **rows,
        "_meta": {"computed_at": datetime.now(timezone.utc).isoformat(),
                  "source": "Wikipedia squads + clubelo.com",
                  "mu": round(mu, 1), "sd": round(sd, 1)},
    }, indent=1))
    print(f"\nwrote {OUT} | mu={mu:.0f} sd={sd:.0f} | "
          f"z-covered: {sum(1 for v in rows.values() if v['z'] is not None)}/48")


if __name__ == "__main__":
    main()
