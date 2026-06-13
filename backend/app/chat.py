"""Football AI Analysis chatbot — agentic Gemini orchestrator.

- 9 read-only tools over the app's own engines (predictions, odds, H2H,
  what-if simulator, news search) via Gemini function calling
- NDJSON stream protocol: {"type": tool|delta|done|error, ...} per line
- Hard cost controls: 5 questions/day/visitor, global daily cap, IP backstop,
  thinkingBudget=0, max_output_tokens, <=3 tool rounds
"""
import json
import logging
import time
from datetime import datetime, timezone

import httpx

from . import cache, evaluation, service
from .config import settings
from .static_data import TEAMS

log = logging.getLogger("chat")

GEMINI = "https://generativelanguage.googleapis.com/v1beta/models"
MAX_TOOL_ROUNDS = 3

# Questions that warrant deep multi-source synthesis (turn on Gemini thinking,
# more tool rounds, a longer answer + a mandatory verdict). Keep cheap lookups
# ("khi nào", "đội hình", "tỉ số") on the fast path with thinking off.
_ANALYSIS_KW = (
    "phân tích", "phan tich", "nhận định", "nhan dinh", "soi kèo", "soi keo",
    "nên chọn", "nen chon", "nên đặt", "đánh giá", "danh gia", "so sánh",
    "so sanh", "dự đoán", "du doan", "ai thắng", "ai se thang", "cửa nào",
    "kèo nào", "có nên", "khuyến nghị", "tư vấn", "deep", "chi tiết",
    "analy", "predict", "recommend", "should i", "who will win", "vs ",
    "value", "đáng", "lời khuyên",
)


def wants_analysis(message: str | None) -> bool:
    m = (message or "").lower()
    return any(k in m for k in _ANALYSIS_KW)
KEY_COOLDOWN_S = 6 * 3600     # quota-hit keys sit out; free RPD resets daily


# ── API-key pool with quota failover ─────────────────────────────────────
def available_keys() -> list[tuple[int, str]]:
    """(index, key) pairs not in cooldown; if all are cooling, return all
    (quota may have reset)."""
    keys = settings.gemini_keys()
    fresh = []
    for i, k in enumerate(keys):
        ts, _ = cache.get_stale(f"gemini:cooldown:{i}")
        if ts and time.time() - float(ts) < KEY_COOLDOWN_S:
            continue
        fresh.append((i, k))
    return fresh or list(enumerate(keys))


def mark_exhausted(idx: int) -> None:
    log.warning("gemini key #%d quota-exhausted — cooling down 6h", idx)
    cache.put(f"gemini:cooldown:{idx}", time.time())


def _is_quota_error(status: int, body: str) -> bool:
    return status == 429 or (status == 403 and "RESOURCE_EXHAUSTED" in body)

# ── team name resolver (vi/en aliases) ──────────────────────────────────
VI_ALIASES = {
    "tây ban nha": "ESP", "bồ đào nha": "POR", "đức": "GER", "pháp": "FRA",
    "anh": "ENG", "hà lan": "NED", "bỉ": "BEL", "thụy sĩ": "SUI",
    "thụy điển": "SWE", "na uy": "NOR", "áo": "AUT", "croatia": "CRO",
    "scotland": "SCO", "séc": "CZE", "ch séc": "CZE", "czech": "CZE", "bosnia": "BIH",
    "hàn quốc": "KOR", "hàn": "KOR", "nhật bản": "JPN", "nhật": "JPN",
    "iran": "IRN", "iraq": "IRQ", "qatar": "QAT", "ả rập xê út": "KSA",
    "saudi": "KSA", "jordan": "JOR", "uzbekistan": "UZB", "úc": "AUS",
    "australia": "AUS", "new zealand": "NZL", "mỹ": "USA", "hoa kỳ": "USA",
    "mexico": "MEX", "mễ": "MEX", "canada": "CAN", "panama": "PAN",
    "haiti": "HAI", "curacao": "CUW", "brazil": "BRA", "bra-xin": "BRA",
    "argentina": "ARG", "uruguay": "URY", "colombia": "COL", "ecuador": "ECU",
    "paraguay": "PAR", "ma rốc": "MAR", "morocco": "MAR", "ai cập": "EGY",
    "senegal": "SEN", "ghana": "GHA", "algeria": "ALG", "tunisia": "TUN",
    "bờ biển ngà": "CIV", "nam phi": "RSA", "cape verde": "CPV",
    "congo": "COD", "tây ban nhà": "ESP",
}
_NAME_TO_TLA = {t["name"].lower(): tla for tla, t in TEAMS.items()}


def _norm(s: str) -> str:
    """lowercase, strip diacritics, '&'->'and', drop punctuation."""
    import re
    import unicodedata
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = s.replace("&", " and ")
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _build_norm_map() -> dict[str, str]:
    from .static_data import ODDS_NAME_TO_TLA
    m: dict[str, str] = {}
    for src in (_NAME_TO_TLA, VI_ALIASES, ODDS_NAME_TO_TLA):
        for name, tla in src.items():
            m[_norm(name)] = tla
    return m


_NORM_MAP = _build_norm_map()


def resolve_team(s: str) -> str | None:
    """Robust: exact TLA, exact normalized name/alias, then containment
    fuzzy match — LLM tool args come in many spellings ('Bosnia &
    Herzegovina', 'Korea Republic', 'Tây Ban Nha'...)."""
    raw = (s or "").strip()
    if raw.upper() in TEAMS:
        return raw.upper()
    n = _norm(raw)
    if not n:
        return None
    if n in _NORM_MAP:
        return _NORM_MAP[n]
    # containment either way, longest key wins (>=4 chars to avoid noise)
    best = None
    for key, tla in _NORM_MAP.items():
        if len(key) >= 4 and (key in n or n in key):
            if best is None or len(key) > len(best[0]):
                best = (key, tla)
    return best[1] if best else None


# ── quota ────────────────────────────────────────────────────────────────
def _qkey(kind: str, ident: str) -> str:
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"chatquota:{day}:{kind}:{ident}"


def check_quota(visitor: str, ip: str) -> tuple[bool, int]:
    """(allowed, remaining_for_visitor)"""
    v, _ = cache.get_stale(_qkey("v", visitor))
    i, _ = cache.get_stale(_qkey("ip", ip))
    g, _ = cache.get_stale(_qkey("g", "all"))
    v, i, g = v or 0, i or 0, g or 0
    remaining = max(0, settings.chat_daily_per_user - v)
    allowed = (v < settings.chat_daily_per_user
               and i < settings.chat_daily_per_user * 3
               and g < settings.chat_daily_global)
    return allowed, remaining


def consume_quota(visitor: str, ip: str) -> int:
    v, _ = cache.get_stale(_qkey("v", visitor))
    i, _ = cache.get_stale(_qkey("ip", ip))
    g, _ = cache.get_stale(_qkey("g", "all"))
    cache.put(_qkey("v", visitor), (v or 0) + 1)
    cache.put(_qkey("ip", ip), (i or 0) + 1)
    cache.put(_qkey("g", "all"), (g or 0) + 1)
    return max(0, settings.chat_daily_per_user - (v or 0) - 1)


# ── tools ────────────────────────────────────────────────────────────────
def _team_arg(desc_vi: str):
    return {"type": "string", "description": f"{desc_vi} — team code (ESP) or name (Spain / Tây Ban Nha)"}


TOOL_DECLS = [
    {"name": "get_live_and_today",
     "description": "Live matches right now (score, minute, cards, corners) and today's fixtures.",
     "parameters": {"type": "object", "properties": {}}},
    {"name": "get_upcoming_fixtures",
     "description": "UPCOMING fixtures (next matches): kickoff time UTC, stage/group, optionally filtered to one team. Use for 'trận kế tiếp', 'lịch thi đấu', 'khi nào X đá', knockout dates.",
     "parameters": {"type": "object", "properties": {
         "team": _team_arg("Lọc theo đội (tùy chọn)"),
         "n": {"type": "integer", "description": "how many, default 6"}}}},
    {"name": "get_expected_lineups",
     "description": "Lineups for a matchup: the ANNOUNCED starting XI with formation when published (~1h before kickoff), otherwise the expected setup (usual formation, key players, fitness flags). Use for 'đội hình dự kiến', 'formation', 'ai đá chính'.",
     "parameters": {"type": "object", "properties": {
         "home": _team_arg("Đội nhà"), "away": _team_arg("Đội khách")},
         "required": ["home", "away"]}},
    {"name": "get_recent_results",
     "description": "RESULTS of recently finished World Cup matches: final + half-time score, goalscorers with minutes, cards, corners, possession. Use for any question about a match that already happened ('trận vừa rồi', 'kết quả').",
     "parameters": {"type": "object", "properties": {
         "n": {"type": "integer", "description": "how many recent matches, default 8"}}}},
    {"name": "get_match_prediction",
     "description": "Full model prediction for a matchup: win/draw/loss %, expected goals, model components (ML/market/Elo), halves, corners, extra-time/penalties, key-player absences.",
     "parameters": {"type": "object", "properties": {
         "home": _team_arg("Đội nhà"), "away": _team_arg("Đội khách")},
         "required": ["home", "away"]}},
    {"name": "get_team_overview",
     "description": "One team: Elo, FIFA rank, group standing, tournament odds (champion, reach R32/QF...), tactical profile, key players.",
     "parameters": {"type": "object", "properties": {"team": _team_arg("Đội")},
                    "required": ["team"]}},
    {"name": "get_title_odds",
     "description": "Championship and advancement probabilities for the top teams (Monte Carlo, 50k runs).",
     "parameters": {"type": "object", "properties": {
         "top_n": {"type": "integer", "description": "default 8"}}}},
    {"name": "get_group_standings",
     "description": "Standings + qualification odds for one group (A..L).",
     "parameters": {"type": "object", "properties": {
         "group": {"type": "string", "description": "Group letter A-L"}},
         "required": ["group"]}},
    {"name": "get_h2h_record",
     "description": "Past head-to-head meetings since 2018, with what the model predicted for each and whether it was right.",
     "parameters": {"type": "object", "properties": {
         "home": _team_arg("Đội 1"), "away": _team_arg("Đội 2")},
         "required": ["home", "away"]}},
    {"name": "get_market_odds",
     "description": "Bookmaker odds (1X2, totals, BTTS) vs the model's fair odds for a matchup, with value flags.",
     "parameters": {"type": "object", "properties": {
         "home": _team_arg("Đội nhà"), "away": _team_arg("Đội khách")},
         "required": ["home", "away"]}},
    {"name": "get_match_dossier",
     "description": "ONE-CALL full analysis bundle for a fixture — use this for any 'phân tích/soi kèo/nhận định/nên chọn' question instead of 5 separate calls. Returns the model prediction (W/D/L, λ/xG, top scorelines, O/U & corners lines with confidence, BTTS), the volatility (P result flips vs HT), key scenarios (late goal/comeback/clean sheet), context+venue+style factors, key absences, head-to-head history, and the bookmaker-vs-model value gaps. Synthesize a verdict from this.",
     "parameters": {"type": "object", "properties": {
         "home": _team_arg("Đội nhà"), "away": _team_arg("Đội khách")},
         "required": ["home", "away"]}},
    {"name": "what_if",
     "description": "Scenario simulator: force a hypothetical result for a group match and re-run 20,000 tournament simulations; returns how title/advancement odds shift.",
     "parameters": {"type": "object", "properties": {
         "home": _team_arg("Đội nhà"), "away": _team_arg("Đội khách"),
         "home_goals": {"type": "integer"}, "away_goals": {"type": "integer"}},
         "required": ["home", "away", "home_goals", "away_goals"]}},
    {"name": "get_wc_info",
     "description": "Authoritative World Cup 2026 facts: format/rules, how the 8 best third-placed teams qualify, group tiebreakers, knockout/extra-time/penalty rules, host countries, venues & stadiums (city, capacity, altitude, roof), key dates, the final, opening match. Use for 'thể thức', 'luật', 'sân nào', 'chủ nhà', 'khi nào' — prefer this over a web search.",
     "parameters": {"type": "object", "properties": {
         "topic": {"type": "string", "description": "what to look up, e.g. 'format', 'venues', 'third place', 'tiebreakers', 'final'"}},
         "required": ["topic"]}},
    {"name": "get_wc_news",
     "description": "Latest World Cup 2026 news from the web (injuries, lineups, results, talking points). Grounded with sources. Use for 'tin mới nhất', 'có gì mới', tournament news.",
     "parameters": {"type": "object", "properties": {
         "query": {"type": "string", "description": "optional focus, e.g. a team or player"}}}},
    {"name": "search_football_news",
     "description": "Search the web (Google) for anything football the internal tools don't cover: news, injuries, transfers, football history, legendary players, other leagues/tournaments, stadiums, schedules. Prefer this over refusing or guessing.",
     "parameters": {"type": "object", "properties": {
         "query": {"type": "string"}}, "required": ["query"]}},
]

TOOL_LABELS = {
    "get_live_and_today": ("Xem trận live & hôm nay", "Checking live & today's matches"),
    "get_recent_results": ("Tra kết quả các trận đã đấu", "Fetching recent results"),
    "get_upcoming_fixtures": ("Xem lịch các trận sắp tới", "Fetching upcoming fixtures"),
    "get_expected_lineups": ("Tra đội hình (dự kiến/chính thức)", "Fetching lineups"),
    "get_match_prediction": ("Tra dự đoán trận đấu", "Fetching match prediction"),
    "get_team_overview": ("Phân tích đội bóng", "Analyzing team"),
    "get_title_odds": ("Xem cửa vô địch", "Fetching title odds"),
    "get_group_standings": ("Xem cục diện bảng đấu", "Fetching group standings"),
    "get_h2h_record": ("Tra lịch sử đối đầu", "Checking head-to-head"),
    "get_market_odds": ("So kèo thị trường vs model", "Comparing market vs model odds"),
    "get_match_dossier": ("Tổng hợp hồ sơ trận để phân tích", "Building full match dossier"),
    "what_if": ("Mô phỏng kịch bản giả định (20k sims)", "Simulating what-if scenario (20k sims)"),
    "get_wc_info": ("Tra thông tin World Cup 2026", "Looking up World Cup 2026 info"),
    "get_wc_news": ("Tin nóng World Cup 2026", "Fetching World Cup 2026 news"),
    "search_football_news": ("Search tin tức bóng đá", "Searching football news"),
}


async def _exec_tool(name: str, args: dict) -> dict:
    try:
        if name == "get_live_and_today":
            ms = await service.get_matches()
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            return {"live": [_mt(m) for m in ms if m["status"] in service.LIVE_STATUSES],
                    "today": [_mt(m) for m in ms if m["utcDate"][:10] == today]}
        if name == "get_upcoming_fixtures":
            ms = await service.get_matches()
            team = resolve_team(args.get("team", "")) if args.get("team") else None
            ups = [m for m in ms if m["status"] in ("TIMED", "SCHEDULED")
                   and m["home"]["tla"]]
            if team:
                ups = [m for m in ups if team in (m["home"]["tla"], m["away"]["tla"])]
            ups.sort(key=lambda m: m["utcDate"])
            return {"note": "times are UTC — convert for the user (VN = UTC+7)",
                    "fixtures": [{"home": m["home"]["tla"], "away": m["away"]["tla"],
                                  "kickoff_utc": m["utcDate"], "stage": m["stage"],
                                  "group": m.get("group")}
                                 for m in ups[:int(args.get("n") or 6)]]}
        if name == "get_expected_lineups":
            h, a = _resolve2(args)
            ana = await service.analysis(h, a)
            out = {"announced": ana["lineups_announced"]}
            for tla in (h, a):
                d = ana["teams"][tla]
                lu = d.get("lineup")
                out[tla] = {
                    "formation": d.get("formation_live") or d["profile"].get("formation"),
                    "formation_is_official": bool(d.get("formation_live")),
                    "starting_xi": [p["name"] for p in (lu or {}).get("players", [])] or None,
                    "key_players": [{"name": k["name"], "pos": k["pos"],
                                     "status": k["status"]} for k in d["key_players"]],
                    "manager": d["profile"].get("manager"),
                    "manager_tactics": d.get("manager_note"),
                }
            return out
        if name == "get_recent_results":
            res = await service.recent_results(int(args.get("n") or 8))
            return {"results": [
                {"home": r["home"]["tla"], "away": r["away"]["tla"],
                 "score": r["score"], "ht": r.get("ht_score"),
                 "date": r["date"], "stage": r["stage"],
                 "goals": [{"minute": i.get("minute"), "player": i.get("player"),
                            "side": i.get("side"), "penalty": i.get("penalty"),
                            "own_goal": i.get("own_goal")}
                           for i in (r.get("incidents") or []) if i.get("type") == "goal"],
                 "cards": [{"minute": i.get("minute"), "player": i.get("player"),
                            "side": i.get("side"), "card": i.get("type")}
                           for i in (r.get("incidents") or []) if i.get("type") in ("yellow", "red")],
                 "corners": r.get("corners"),
                 "stats": {k: v for k, v in (r.get("stats") or {}).items()
                           if k in ("possession", "shots_on", "fouls", "offsides", "xg")}}
                for r in res]}
        if name == "get_match_prediction":
            h, a = _resolve2(args)
            p = await service.predict(h, a)
            return {"home": h, "away": a, "probs": p["probs"],
                    "expected_goals": p["lambdas"],
                    "components": {k: v for k, v in p["components"].items()
                                   if k in ("ml", "market", "poisson", "weights")},
                    "top_scores": p["scorelines"][:3], "over25": p["over25"],
                    "halves_htft_top": sorted((p.get("halves", {}).get("htft") or {}).items(),
                                              key=lambda x: -x[1])[:3],
                    "corners_expected": p.get("corners", {}).get("expected"),
                    "knockout": {k: p["knockout"][k] for k in
                                 ("p_extra_time", "p_penalties", "advance")} if p.get("knockout") else None,
                    "key_absences": p.get("absence_penalty"),
                    "context": p["components"].get("context"),
                    "venue": p["components"].get("venue"),
                    "seed": p["components"].get("seed"),   # draw pots + prior delta
                    "ou_lines": p.get("market_lines"),     # line + over% + pick + confidence
                    "scenarios": (p.get("simulation") or {}).get("scenarios"),
                    "volatility": p.get("volatility"),  # high => state the pick cautiously
                    "elo": p["elo"]}
        if name == "get_team_overview":
            t = resolve_team(args.get("team", ""))
            if not t:
                return {"error": "unknown team"}
            teams = await service.get_teams()
            sim = await service.latest_simulation() or {}
            from .team_profiles import PROFILES
            from .engine.style_adjust import MANAGER_NOTES
            from .static_data import pot_of, group_difficulty
            return {"team": t, "manager_tactics": MANAGER_NOTES.get(t), **{k: teams[t][k] for k in
                    ("name", "group", "position", "played", "points", "gf", "ga", "elo", "fifa_rank")},
                    "draw_pot": pot_of(t),       # official seeding tier 1(top)-4
                    "group_difficulty_avg_opp_elo": group_difficulty(t),
                    "sim_odds": (sim.get("teams") or {}).get(t),
                    "profile": PROFILES.get(t)}
        if name == "get_title_odds":
            sim = await service.latest_simulation() or await service.run_simulation()
            n = int(args.get("top_n") or 8)
            top = sorted(sim["teams"].items(), key=lambda kv: -kv[1]["champion"])[:n]
            return {"runs": sim["runs"],
                    "top": [{"team": t, **v} for t, v in top]}
        if name == "get_group_standings":
            g = (args.get("group") or "").strip().upper()[-1]
            teams = await service.get_teams()
            sim = await service.latest_simulation() or {}
            rows = sorted((t for t in teams.values() if t["group"] == g),
                          key=lambda r: r["position"])
            return {"group": g, "table": [
                {**{k: r[k] for k in ("tla", "name", "played", "won", "draw",
                                      "lost", "gd", "points")},
                 "qualify_odds": ((sim.get("teams") or {}).get(r["tla"]) or {}).get("r32")}
                for r in rows]}
        if name == "get_h2h_record":
            h, a = _resolve2(args)
            return evaluation.h2h(h, a, n=6)
        if name == "get_market_odds":
            h, a = _resolve2(args)
            board = await service.odds_board(limit=40)
            for r in board["matches"]:
                if {r["home"]["tla"], r["away"]["tla"]} == {h, a}:
                    return {"home": r["home"]["tla"], "away": r["away"]["tla"],
                            "market": r.get("market"), "fair": r["fair"],
                            "value_flags": r.get("value")}
            return {"error": "no odds for this matchup yet"}
        if name == "get_match_dossier":
            h, a = _resolve2(args)
            p = await service.predict(h, a)
            comp = p.get("components", {})
            dossier = {
                "home": h, "away": a, "probs": p["probs"],
                "expected_goals": p["lambdas"],
                "top_scores": p["scorelines"][:3], "over25": p["over25"],
                "btts": p.get("btts"),
                "ou_lines": p.get("market_lines"),
                "corners": (p.get("corners") or {}).get("expected"),
                "volatility": p.get("volatility"),
                "scenarios": (p.get("simulation") or {}).get("scenarios"),
                "context": comp.get("context"), "venue": comp.get("venue"),
                "style": comp.get("style"), "seed": comp.get("seed"),
                "key_absences": p.get("absence_penalty"),
                "elo": p["elo"],
            }
            try:
                dossier["h2h"] = evaluation.h2h(h, a, n=6)
            except Exception:
                pass
            board = await service.odds_board(limit=40)
            for r in board["matches"]:
                if {r["home"]["tla"], r["away"]["tla"]} == {h, a}:
                    dossier["market_vs_model"] = {
                        "market": r.get("market"), "fair": r["fair"],
                        "value_flags": r.get("value")}
                    break
            return dossier
        if name == "what_if":
            h, a = _resolve2(args)
            return await service.simulate_what_if(
                h, a, int(args["home_goals"]), int(args["away_goals"]))
        if name == "get_wc_info":
            from . import wc_kb
            return wc_kb.lookup(args.get("topic", ""))
        if name == "get_wc_news":
            q = args.get("query", "")
            return await _news(f"FIFA World Cup 2026 latest news {q}".strip())
        if name == "search_football_news":
            return await _news(args.get("query", ""))
        return {"error": f"unknown tool {name}"}
    except Exception as e:
        log.warning("tool %s failed: %s", name, e)
        return {"error": str(e)[:200]}


def _resolve2(args: dict) -> tuple[str, str]:
    h = resolve_team(args.get("home", ""))
    a = resolve_team(args.get("away", ""))
    if not h or not a:
        raise ValueError(f"unknown team in {args}")
    return h, a


def _mt(m: dict) -> dict:
    return {"home": m["home"]["tla"], "away": m["away"]["tla"],
            "status": m["status"], "minute": m.get("minute_estimate"),
            "score": m["score"], "kickoff_utc": m["utcDate"],
            "red_cards": m.get("red_cards"), "corners": m.get("corners")}


async def _news(query: str) -> dict:
    """Sub-call with Google Search grounding (can't mix with function tools)."""
    try:
        d = None
        async with httpx.AsyncClient(timeout=15) as client:
            for idx, key in available_keys():
                r = await client.post(
                    f"{GEMINI}/{settings.chat_model}:generateContent",
                    headers={"x-goog-api-key": key},
                    json={"contents": [{"parts": [{"text":
                          f"Summarize in <=120 words the most recent football news about: {query}. "
                          "Prioritize FIFA World Cup 2026 (June-July 2026) when relevant."}]}],
                          "tools": [{"google_search": {}}],
                          "generationConfig": {"maxOutputTokens": 256,
                                               "thinkingConfig": {"thinkingBudget": 0}}})
                if _is_quota_error(r.status_code, r.text):
                    mark_exhausted(idx)
                    continue
                r.raise_for_status()
                d = r.json()
                break
        if d is None:
            return {"error": "news search quota exhausted on all keys"}
        parts = d["candidates"][0]["content"]["parts"]
        text = " ".join(p.get("text", "") for p in parts)
        cites = []
        meta = d["candidates"][0].get("groundingMetadata", {})
        for ch in (meta.get("groundingChunks") or [])[:4]:
            w = ch.get("web") or {}
            if w.get("uri"):
                cites.append({"title": w.get("title", ""), "url": w["uri"]})
        return {"summary": text.strip(), "sources": cites}
    except Exception as e:
        return {"error": f"news search unavailable: {str(e)[:120]}"}


# ── skills (deterministic tool plans) ───────────────────────────────────
SKILLS = {
    "deep_dive": {
        "plan": ["get_match_prediction", "get_h2h_record", "get_market_odds"],
        "prompt_vi": "Phân tích sâu trận {home} vs {away}: nhận định tổng hợp từ dự đoán, lịch sử đối đầu, kèo. Kết luận rõ ràng.",
        "prompt_en": "Deep-dive analysis of {home} vs {away} from the prediction, H2H and odds data. Clear verdict."},
    "value_hunt": {
        "plan": [],
        "prompt_vi": "Soi các kèo value hôm nay: so fair odds của model với kèo thị trường, chỉ ra chênh lệch đáng chú ý và lý do.",
        "prompt_en": "Find today's value bets: compare model fair odds vs market, highlight notable gaps and why."},
    "group_race": {
        "plan": ["get_group_standings"],
        "prompt_vi": "Phân tích cục diện bảng {group}: ai sáng cửa đi tiếp, kịch bản nào cần chú ý.",
        "prompt_en": "Analyze group {group}: who advances, key scenarios."},
}


# ── system prompt ────────────────────────────────────────────────────────
def _system(lang: str, analysis: bool = False) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    analyst_block = """
ANALYSIS MODE (this is an analytical question — think before you answer):
- Call get_match_dossier FIRST for the fixture — it bundles prediction, O/U & corners lines, volatility, scenarios, factors, H2H and the market-vs-model value gaps in one shot. Add get_expected_lineups / get_wc_news only if they'd change the read.
- SYNTHESIZE across sources — don't just list numbers. Weigh the model probs against the market: where the model's fair odds beat the bookmaker line, that's the value; say so explicitly.
- You MUST end the analysis (before the FOLLOWUPS line) with a verdict block, in the user's language, formatted exactly:
  🎯 Nhận định: <the lean — winner / O-U / BTTS as relevant> · độ tự tin <toss_up|lean|clear>
  ▸ Lý do: <2-3 short bullets tying the call to concrete factors: Elo/value gap, style matchup, venue/heat, volatility, absences>
  ▸ Lưu ý: <volatility/biến động or any caveat> — tham khảo thống kê, không phải lời khuyên cá cược.
- Be decisive but honest: on a genuine 50-50 say so. If volatility.level is high, the verdict must soften the pick.
"""
    return f"""You are "WC Analyst" — the in-app football analyst of an AI World Cup 2026 prediction platform. Now: {now}. Tournament: FIFA World Cup 2026 (48 teams, Jun 11 - Jul 19).
{analyst_block if analysis else ""}
RULES:
- Use the provided tools for EVERY app-model number you cite (probabilities, odds, Elo, simulations). Never invent statistics. If a tool errors, say what you couldn't fetch.
- Explain WHY probabilities are what they are using tool data: Elo gap, ML ensemble vs market odds components, key-player absences, red cards, home advantage (USA/MEX/CAN).
- You may answer ANY football question — this World Cup first, but also football history, legendary players, clubs, other tournaments, rules, venues, player/team comparisons, "who scores most" etc. Retrieval order: internal KB/data tools FIRST, then web search; only refuse clearly non-football topics.
- Common question → tool map: "thể thức/luật/sân nào/chủ nhà/khi nào (giải)" → get_wc_info · "tin mới nhất/có gì mới" → get_wc_news · "trận kế tiếp/lịch đấu" → get_upcoming_fixtures · "soi kèo/tài xỉu" → get_match_prediction (+ get_market_odds) · "AI dự đoán/tỉ lệ" → get_match_prediction · "lịch sử đối đầu" → get_h2h_record (2018+; older → web) · "đội hình dự kiến" → get_expected_lineups · "kết quả" → get_recent_results · history/transfers/other → search_football_news. Chain tools freely.
- If the user names ONE team and asks about "its match" (e.g. "kèo Canada tối nay", "Canada đá với ai", "phân tích trận của X", "next match of X") WITHOUT naming the opponent, DO NOT ask who the opponent is — you can find it: first call get_live_and_today and/or get_upcoming_fixtures with team=X to discover their nearest live/today/next fixture, then immediately chain get_match_prediction (+ get_market_odds) on that matchup and analyze. Only say there is no match if that team genuinely has no live/scheduled fixture. Never bounce a one-team question back to the user.
- When giving Over/Under or a tip, ALWAYS state the confidence (toss_up/lean/clear from ou_lines) — never sound certain on a 50-50 fixture — and give the reason from the factors (venue altitude/heat, both-defensive style, dead rubber, absences). Quote the most-likely scoreline consistently with the O/U lean. If volatility.level is "high", warn that the result has a high chance of flipping vs half-time (quote scenarios.ht_flip) and soften the pick accordingly.
- Resolve follow-up references from the conversation history: if the user says "tỉ lệ kèo", "trận này", "còn hiệp 1?", "what about corners?" without naming teams, they mean the matchup discussed in the most recent turns — call the tool with that matchup directly. Only ask which match if NO matchup appears anywhere in the history.
- Answer in the SAME language as the user's question (Vietnamese or English). Warm, expert; light emoji; short bullet lists for numbers. Quick lookups: be concise (<=180 words). Analytical questions: be thorough but tight (<=320 words) and finish with the verdict block.
- Decline only clearly NON-football topics (coding, politics, homework...) in one polite sentence.
- Predictions are statistical estimates — when relevant, append a one-line reminder that this is reference, not betting advice.
- End your reply with one line exactly: FOLLOWUPS: q1 | q2 (two short follow-up questions in the user's language). This line will be hidden from the user.
- User interface language hint: {lang}."""


# ── orchestrator ─────────────────────────────────────────────────────────
async def stream_chat(visitor: str, ip: str, message: str | None,
                      skill: str | None, params: dict, history: list, lang: str):
    """Async generator yielding NDJSON lines."""
    allowed, remaining = check_quota(visitor or "anon", ip or "noip")
    if not allowed:
        yield json.dumps({"type": "error", "code": "quota",
                          "remaining": 0}) + "\n"
        return
    remaining = consume_quota(visitor or "anon", ip or "noip")

    # analytics
    try:
        from . import analytics
        analytics.record(visitor or "anon", "chat",
                         {"skill": skill or "free", "lang": lang})
    except Exception:
        pass

    # ----- build contents -----
    contents = []
    for turn in (history or [])[-8:]:
        role = "user" if turn.get("role") == "user" else "model"
        contents.append({"role": role, "parts": [{"text": str(turn.get("text", ""))[:700]}]})

    pre_tools_results = []
    if skill in SKILLS:
        sk = SKILLS[skill]
        # deterministic pre-fetch
        for tname in sk["plan"]:
            args = {k: params.get(k) for k in ("home", "away", "group") if params.get(k)}
            yield json.dumps({"type": "tool", "name": tname,
                              "label_vi": TOOL_LABELS[tname][0],
                              "label_en": TOOL_LABELS[tname][1]}) + "\n"
            res = await _exec_tool(tname, args)
            pre_tools_results.append({"tool": tname, "result": res})
        if skill == "value_hunt":
            yield json.dumps({"type": "tool", "name": "get_market_odds",
                              "label_vi": "Quét bảng kèo hôm nay",
                              "label_en": "Scanning today's odds board"}) + "\n"
            board = await service.odds_board(limit=8)
            pre_tools_results.append({"tool": "odds_board", "result": {
                "matches": [{"home": r["home"]["tla"], "away": r["away"]["tla"],
                             "market": (r.get("market") or {}).get("h2h"),
                             "fair": r["fair"]["h2h"], "value": r.get("value")}
                            for r in board["matches"]]}})
        prompt = (sk["prompt_vi"] if lang == "vi" else sk["prompt_en"]).format(
            home=params.get("home", "?"), away=params.get("away", "?"),
            group=params.get("group", "?"))
        user_text = prompt + "\n\nDATA:\n" + json.dumps(pre_tools_results)[:14000]
        contents.append({"role": "user", "parts": [{"text": user_text}]})
        tools = None     # skill mode: single grounded generation, no extra calls
    else:
        contents.append({"role": "user", "parts": [{"text": (message or "")[:600]}]})
        tools = [{"function_declarations": TOOL_DECLS}]

    # analytical questions: deep-think, more tool rounds, longer answer
    analysis = skill is None and wants_analysis(message)
    think_budget = settings.chat_think_budget if analysis else 0
    max_rounds = settings.chat_analysis_rounds if analysis else MAX_TOOL_ROUNDS
    max_out = (settings.chat_analysis_max_output_tokens if analysis
               else settings.chat_max_output_tokens)
    if analysis:
        yield json.dumps({"type": "thinking"}) + "\n"

    full_text = []
    news_sources: list[dict] = []
    # Holdback emitter: never let the trailing "FOLLOWUPS: ..." line reach the
    # user; keep a small lookahead buffer so the marker can't slip through
    # split across chunks.
    emit_state = {"acc": "", "sent": 0, "stopped": False}
    HOLD = 12

    def _emit_deltas(new_text: str) -> list[str]:
        if emit_state["stopped"]:
            return []
        emit_state["acc"] += new_text
        acc = emit_state["acc"]
        cut = acc.find("FOLLOWUPS:")
        if cut != -1:
            emit_state["stopped"] = True
            out = acc[emit_state["sent"]:cut].rstrip()
            emit_state["sent"] = cut
            return [out] if out else []
        safe = max(emit_state["sent"], len(acc) - HOLD)
        out = acc[emit_state["sent"]:safe]
        emit_state["sent"] = safe
        return [out] if out else []

    def _flush_deltas() -> list[str]:
        if emit_state["stopped"]:
            return []
        acc = emit_state["acc"]
        out = acc[emit_state["sent"]:]
        emit_state["sent"] = len(acc)
        return [out] if out else []

    async with httpx.AsyncClient(timeout=60) as client:
        for round_i in range(max_rounds + 1):
            body = {
                "system_instruction": {"parts": [{"text": _system(lang, analysis)}]},
                "contents": contents,
                "generationConfig": {
                    "maxOutputTokens": max_out,
                    "temperature": 0.6,
                    "thinkingConfig": {"thinkingBudget": think_budget},
                },
            }
            if tools and round_i < max_rounds:
                body["tools"] = tools

            fn_calls, model_parts = [], []
            # try each available key until one accepts the request (failover
            # happens at header time — nothing has streamed yet, safe to retry)
            stream_ok = False
            last_status = 0
            try:
                for idx, key in available_keys():
                    resp_cm = client.stream(
                        "POST",
                        f"{GEMINI}/{settings.chat_model}:streamGenerateContent",
                        params={"alt": "sse"},
                        headers={"x-goog-api-key": key},
                        json=body)
                    resp = await resp_cm.__aenter__()
                    if resp.status_code != 200:
                        detail = (await resp.aread())[:300].decode(errors="ignore")
                        await resp_cm.__aexit__(None, None, None)
                        last_status = resp.status_code
                        if _is_quota_error(resp.status_code, detail):
                            mark_exhausted(idx)
                            continue
                        log.warning("gemini %s: %s", resp.status_code, detail[:200])
                        break
                    stream_ok = True
                    async for line in resp.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        try:
                            chunk = json.loads(line[5:].strip())
                        except json.JSONDecodeError:
                            continue
                        for part in (chunk.get("candidates", [{}])[0]
                                     .get("content", {}).get("parts", [])):
                            model_parts.append(part)
                            if "functionCall" in part:
                                fn_calls.append(part["functionCall"])
                            elif part.get("text"):
                                full_text.append(part["text"])
                                for piece in _emit_deltas(part["text"]):
                                    yield json.dumps({"type": "delta",
                                                      "text": piece}) + "\n"
                    await resp_cm.__aexit__(None, None, None)
                    break          # streamed successfully — stop trying keys
            except httpx.HTTPError as e:
                log.warning("gemini stream error: %s", e)
                yield json.dumps({"type": "error", "code": "upstream"}) + "\n"
                return

            if not stream_ok:
                log.warning("all gemini keys failed (last status %s)", last_status)
                yield json.dumps({"type": "error", "code": "upstream"}) + "\n"
                return

            if not fn_calls:
                break
            # execute tool calls, append to conversation, loop
            contents.append({"role": "model", "parts": model_parts})
            responses = []
            for fc in fn_calls:
                name, args = fc.get("name", ""), fc.get("args") or {}
                lbl = TOOL_LABELS.get(name, (name, name))
                yield json.dumps({"type": "tool", "name": name,
                                  "label_vi": lbl[0], "label_en": lbl[1],
                                  "args": args}) + "\n"
                result = await _exec_tool(name, args)
                if name == "search_football_news" and isinstance(result, dict):
                    news_sources.extend(result.get("sources") or [])
                raw = json.dumps(result, ensure_ascii=False)
                if len(raw) > 8000:      # keep tool payloads lean for token cost
                    result = {"truncated": True, "data_preview": raw[:8000]}
                responses.append({"functionResponse": {
                    "name": name, "response": {"result": result}}})
            contents.append({"role": "user", "parts": responses})

    # ----- flush + followups parse -----
    for piece in _flush_deltas():
        yield json.dumps({"type": "delta", "text": piece}) + "\n"
    text = "".join(full_text)
    followups = []
    if "FOLLOWUPS:" in text:
        tail = text.rsplit("FOLLOWUPS:", 1)[1]
        followups = [q.strip() for q in tail.split("|") if q.strip()][:3]
    yield json.dumps({"type": "done", "remaining": remaining,
                      "followups": followups,
                      "sources": news_sources[:4]}) + "\n"
