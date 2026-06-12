"""WC-2026 host venues — shared by the venue O/U factor and the chatbot KB.

Each of the 16 stadiums with: city, stadium name, capacity, altitude (m),
roof/AC (negates heat), local UTC offset, and a climate flag (hot summer
afternoons). Altitude → ball flies faster + faster fatigue → historically
MORE goals; open-roof hot-city afternoon kickoffs → lower tempo, fewer late
goals → FEWER. Roofed/air-conditioned stadiums neutralize heat.
"""

VENUES = {
    # key: lowercase stadium-name keywords for matching fd.org venue strings
    "azteca": {"city": "Mexico City", "stadium": "Estadio Azteca", "cap": 87523,
               "alt": 2240, "roof": False, "tz": -6, "hot": False},
    "akron": {"city": "Guadalajara", "stadium": "Estadio Akron", "cap": 48071,
              "alt": 1560, "roof": False, "tz": -6, "hot": True},
    "bbva": {"city": "Monterrey", "stadium": "Estadio BBVA", "cap": 53500,
             "alt": 540, "roof": False, "tz": -6, "hot": True},
    "at&t": {"city": "Dallas", "stadium": "AT&T Stadium", "cap": 80000,
             "alt": 180, "roof": True, "tz": -5, "hot": True},
    "arlington": {"city": "Dallas", "stadium": "AT&T Stadium", "cap": 80000,
                  "alt": 180, "roof": True, "tz": -5, "hot": True},
    "nrg": {"city": "Houston", "stadium": "NRG Stadium", "cap": 72220,
            "alt": 15, "roof": True, "tz": -5, "hot": True},
    "mercedes": {"city": "Atlanta", "stadium": "Mercedes-Benz Stadium", "cap": 71000,
                 "alt": 320, "roof": True, "tz": -4, "hot": True},
    "sofi": {"city": "Los Angeles", "stadium": "SoFi Stadium", "cap": 70240,
             "alt": 30, "roof": True, "tz": -7, "hot": True},
    "inglewood": {"city": "Los Angeles", "stadium": "SoFi Stadium", "cap": 70240,
                  "alt": 30, "roof": True, "tz": -7, "hot": True},
    "metlife": {"city": "New York NJ", "stadium": "MetLife Stadium", "cap": 82500,
                "alt": 5, "roof": False, "tz": -4, "hot": True},
    "rutherford": {"city": "New York NJ", "stadium": "MetLife Stadium", "cap": 82500,
                   "alt": 5, "roof": False, "tz": -4, "hot": True},
    "gillette": {"city": "Boston", "stadium": "Gillette Stadium", "cap": 65878,
                 "alt": 90, "roof": False, "tz": -4, "hot": False},
    "foxborough": {"city": "Boston", "stadium": "Gillette Stadium", "cap": 65878,
                   "alt": 90, "roof": False, "tz": -4, "hot": False},
    "lincoln": {"city": "Philadelphia", "stadium": "Lincoln Financial Field",
                "cap": 69596, "alt": 12, "roof": False, "tz": -4, "hot": True},
    "hard rock": {"city": "Miami", "stadium": "Hard Rock Stadium", "cap": 65326,
                  "alt": 3, "roof": False, "tz": -4, "hot": True},
    "miami gardens": {"city": "Miami", "stadium": "Hard Rock Stadium", "cap": 65326,
                      "alt": 3, "roof": False, "tz": -4, "hot": True},
    "arrowhead": {"city": "Kansas City", "stadium": "Arrowhead Stadium", "cap": 76416,
                  "alt": 270, "roof": False, "tz": -5, "hot": True},
    "lumen": {"city": "Seattle", "stadium": "Lumen Field", "cap": 68740,
              "alt": 30, "roof": False, "tz": -7, "hot": False},
    "levi": {"city": "San Francisco", "stadium": "Levi's Stadium", "cap": 68500,
             "alt": 5, "roof": False, "tz": -7, "hot": True},
    "santa clara": {"city": "San Francisco", "stadium": "Levi's Stadium", "cap": 68500,
                    "alt": 5, "roof": False, "tz": -7, "hot": True},
    "bmo": {"city": "Toronto", "stadium": "BMO Field", "cap": 45500,
            "alt": 80, "roof": False, "tz": -4, "hot": False},
    "bc place": {"city": "Vancouver", "stadium": "BC Place", "cap": 54500,
                 "alt": 0, "roof": True, "tz": -7, "hot": False},
    "vancouver": {"city": "Vancouver", "stadium": "BC Place", "cap": 54500,
                  "alt": 0, "roof": True, "tz": -7, "hot": False},
}

# city -> venue key (for knockout MATCH_SCHEDULE city lookups)
CITY_TO_KEY = {}
for _k, _v in VENUES.items():
    CITY_TO_KEY.setdefault(_v["city"], _k)


def resolve_venue(venue_str: str | None, city: str | None = None) -> dict | None:
    """Match an fd.org venue string (or schedule city) to a stadium profile."""
    if venue_str:
        s = venue_str.lower()
        for kw, v in VENUES.items():
            if kw in s:
                return v
    if city and city in CITY_TO_KEY:
        return VENUES[CITY_TO_KEY[city]]
    return None
