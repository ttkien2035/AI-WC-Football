"""Static seeds for the 48 WC-2026 teams.

- elo: World Football Elo snapshot (eloratings.net, early June 2026 estimate).
  Used as fallback / blend basis; the live scraper refreshes when reachable.
- fifa: FIFA Men's World Ranking position (Dec 2025 snapshot, display + minor feature).
- elo_code: team code used by eloratings.net TSV datafiles.
Keys are football-data.org TLA codes.
"""

TEAMS = {
    # Group A
    "CZE": {"name": "Czechia",            "group": "A", "elo": 1745, "fifa": 41, "elo_code": "CZ"},
    "MEX": {"name": "Mexico",             "group": "A", "elo": 1845, "fifa": 15, "elo_code": "MX"},
    "RSA": {"name": "South Africa",       "group": "A", "elo": 1700, "fifa": 56, "elo_code": "ZA"},
    "KOR": {"name": "South Korea",        "group": "A", "elo": 1830, "fifa": 22, "elo_code": "KR"},
    # Group B
    "BIH": {"name": "Bosnia-Herzegovina", "group": "B", "elo": 1705, "fifa": 68, "elo_code": "BA"},
    "CAN": {"name": "Canada",             "group": "B", "elo": 1810, "fifa": 28, "elo_code": "CA"},
    "QAT": {"name": "Qatar",              "group": "B", "elo": 1680, "fifa": 51, "elo_code": "QA"},
    "SUI": {"name": "Switzerland",        "group": "B", "elo": 1855, "fifa": 17, "elo_code": "CH"},
    # Group C
    "BRA": {"name": "Brazil",             "group": "C", "elo": 2025, "fifa": 5,  "elo_code": "BR"},
    "MAR": {"name": "Morocco",            "group": "C", "elo": 1905, "fifa": 11, "elo_code": "MA"},
    "HAI": {"name": "Haiti",              "group": "C", "elo": 1560, "fifa": 84, "elo_code": "HT"},
    "SCO": {"name": "Scotland",           "group": "C", "elo": 1745, "fifa": 38, "elo_code": "SC"},
    # Group D
    "TUR": {"name": "Turkey",             "group": "D", "elo": 1850, "fifa": 25, "elo_code": "TR"},
    "USA": {"name": "United States",      "group": "D", "elo": 1835, "fifa": 14, "elo_code": "US"},
    "PAR": {"name": "Paraguay",           "group": "D", "elo": 1810, "fifa": 39, "elo_code": "PY"},
    "AUS": {"name": "Australia",          "group": "D", "elo": 1760, "fifa": 26, "elo_code": "AU"},
    # Group E
    "GER": {"name": "Germany",            "group": "E", "elo": 1960, "fifa": 9,  "elo_code": "DE"},
    "CUW": {"name": "Curacao",            "group": "E", "elo": 1565, "fifa": 82, "elo_code": "CW"},
    "CIV": {"name": "Ivory Coast",        "group": "E", "elo": 1765, "fifa": 42, "elo_code": "CI"},
    "ECU": {"name": "Ecuador",            "group": "E", "elo": 1880, "fifa": 23, "elo_code": "EC"},
    # Group F
    "SWE": {"name": "Sweden",             "group": "F", "elo": 1800, "fifa": 43, "elo_code": "SE"},
    "NED": {"name": "Netherlands",        "group": "F", "elo": 1990, "fifa": 7,  "elo_code": "NL"},
    "JPN": {"name": "Japan",              "group": "F", "elo": 1885, "fifa": 18, "elo_code": "JP"},
    "TUN": {"name": "Tunisia",            "group": "F", "elo": 1740, "fifa": 46, "elo_code": "TN"},
    # Group G
    "BEL": {"name": "Belgium",            "group": "G", "elo": 1925, "fifa": 8,  "elo_code": "BE"},
    "EGY": {"name": "Egypt",              "group": "G", "elo": 1760, "fifa": 34, "elo_code": "EG"},
    "IRN": {"name": "Iran",               "group": "G", "elo": 1800, "fifa": 20, "elo_code": "IR"},
    "NZL": {"name": "New Zealand",        "group": "G", "elo": 1590, "fifa": 86, "elo_code": "NZ"},
    # Group H
    "ESP": {"name": "Spain",              "group": "H", "elo": 2150, "fifa": 1,  "elo_code": "ES"},
    "CPV": {"name": "Cape Verde",         "group": "H", "elo": 1610, "fifa": 70, "elo_code": "CV"},
    "KSA": {"name": "Saudi Arabia",       "group": "H", "elo": 1680, "fifa": 60, "elo_code": "SA"},
    "URY": {"name": "Uruguay",            "group": "H", "elo": 1925, "fifa": 16, "elo_code": "UY"},
    # Group I
    "IRQ": {"name": "Iraq",               "group": "I", "elo": 1660, "fifa": 58, "elo_code": "IQ"},
    "FRA": {"name": "France",             "group": "I", "elo": 2055, "fifa": 3,  "elo_code": "FR"},
    "SEN": {"name": "Senegal",            "group": "I", "elo": 1820, "fifa": 19, "elo_code": "SN"},
    "NOR": {"name": "Norway",             "group": "I", "elo": 1885, "fifa": 29, "elo_code": "NO"},
    # Group J
    "ARG": {"name": "Argentina",          "group": "J", "elo": 2120, "fifa": 2,  "elo_code": "AR"},
    "ALG": {"name": "Algeria",            "group": "J", "elo": 1785, "fifa": 35, "elo_code": "DZ"},
    "AUT": {"name": "Austria",            "group": "J", "elo": 1860, "fifa": 24, "elo_code": "AT"},
    "JOR": {"name": "Jordan",             "group": "J", "elo": 1670, "fifa": 64, "elo_code": "JO"},
    # Group K
    "COD": {"name": "DR Congo",           "group": "K", "elo": 1690, "fifa": 57, "elo_code": "CD"},
    "POR": {"name": "Portugal",           "group": "K", "elo": 2010, "fifa": 6,  "elo_code": "PT"},
    "UZB": {"name": "Uzbekistan",         "group": "K", "elo": 1700, "fifa": 50, "elo_code": "UZ"},
    "COL": {"name": "Colombia",           "group": "K", "elo": 1930, "fifa": 13, "elo_code": "CO"},
    # Group L
    "ENG": {"name": "England",            "group": "L", "elo": 2040, "fifa": 4,  "elo_code": "EN"},
    "CRO": {"name": "Croatia",            "group": "L", "elo": 1930, "fifa": 10, "elo_code": "HR"},
    "GHA": {"name": "Ghana",              "group": "L", "elo": 1705, "fifa": 73, "elo_code": "GH"},
    "PAN": {"name": "Panama",             "group": "L", "elo": 1700, "fifa": 33, "elo_code": "PA"},
}

ELO_CODE_TO_TLA = {v["elo_code"]: k for k, v in TEAMS.items()}

# Official R32 routing (FIFA / Wikipedia knockout-stage page).
# "1A" = winner of group A, "2A" = runner-up, "3:ABCDF" = a best-third from those groups.
R32 = {
    73: ("2A", "2B"),
    74: ("1E", "3:ABCDF"),
    75: ("1F", "2C"),
    76: ("1C", "2F"),
    77: ("1I", "3:CDFGH"),
    78: ("2E", "2I"),
    79: ("1A", "3:CEFHI"),
    80: ("1L", "3:EHIJK"),
    81: ("1D", "3:BEFIJ"),
    82: ("1G", "3:AEHIJ"),
    83: ("2K", "2L"),
    84: ("1H", "2J"),
    85: ("1B", "3:EFGIJ"),
    86: ("1J", "2H"),
    87: ("1K", "3:DEIJL"),
    88: ("2D", "2G"),
}
R16 = {89: (74, 77), 90: (73, 75), 91: (76, 78), 92: (79, 80),
       93: (83, 84), 94: (81, 82), 95: (86, 88), 96: (85, 87)}
QF = {97: (89, 90), 98: (93, 94), 99: (91, 92), 100: (95, 96)}
SF = {101: (97, 98), 102: (99, 100)}
FINAL = {104: (101, 102)}

# Official knockout schedule (FIFA / Wikipedia knockout-stage page).
# City = host-city branding (stadium towns mapped: Inglewood->Los Angeles,
# Foxborough->Boston, Guadalupe->Monterrey, East Rutherford->New York NJ,
# Arlington->Dallas, Santa Clara->San Francisco, Miami Gardens->Miami).
MATCH_SCHEDULE = {
    73: ("2026-06-28", "Los Angeles"),   74: ("2026-06-29", "Boston"),
    75: ("2026-06-29", "Monterrey"),     76: ("2026-06-29", "Houston"),
    77: ("2026-06-30", "New York NJ"),   78: ("2026-06-30", "Dallas"),
    79: ("2026-06-30", "Mexico City"),   80: ("2026-07-01", "Atlanta"),
    81: ("2026-07-01", "San Francisco"), 82: ("2026-07-01", "Seattle"),
    83: ("2026-07-02", "Toronto"),       84: ("2026-07-02", "Los Angeles"),
    85: ("2026-07-02", "Vancouver"),     86: ("2026-07-03", "Miami"),
    87: ("2026-07-03", "Kansas City"),   88: ("2026-07-03", "Dallas"),
    89: ("2026-07-04", "Philadelphia"),  90: ("2026-07-04", "Houston"),
    91: ("2026-07-05", "New York NJ"),   92: ("2026-07-05", "Mexico City"),
    93: ("2026-07-06", "Dallas"),        94: ("2026-07-06", "Seattle"),
    95: ("2026-07-07", "Atlanta"),       96: ("2026-07-07", "Vancouver"),
    97: ("2026-07-09", "Boston"),        98: ("2026-07-10", "Los Angeles"),
    99: ("2026-07-11", "Miami"),         100: ("2026-07-11", "Kansas City"),
    101: ("2026-07-14", "Dallas"),       102: ("2026-07-15", "Atlanta"),
    103: ("2026-07-18", "Miami"),        104: ("2026-07-19", "New York NJ"),
}

# The Odds API team names that differ from football-data.org names
ODDS_NAME_TO_TLA = {
    "south korea": "KOR", "republic of korea": "KOR", "korea republic": "KOR",
    "usa": "USA", "united states": "USA",
    "ir iran": "IRN", "iran": "IRN",
    "cote d'ivoire": "CIV", "ivory coast": "CIV",
    "czech republic": "CZE", "czechia": "CZE",
    "bosnia and herzegovina": "BIH", "bosnia-herzegovina": "BIH",
    "cape verde islands": "CPV", "cape verde": "CPV",
    "dr congo": "COD", "congo dr": "COD", "democratic republic of the congo": "COD",
    "curacao": "CUW", "uruguay": "URY", "turkiye": "TUR", "turkey": "TUR",
}
