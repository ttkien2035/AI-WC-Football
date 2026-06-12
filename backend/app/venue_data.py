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

# stadium coordinates by host city (for the Open-Meteo forecast lookup);
# point is the stadium itself, not downtown (e.g. Foxborough, Inglewood).
CITY_COORDS = {
    "Mexico City": (19.303, -99.151),    # Estadio Azteca
    "Guadalajara": (20.682, -103.463),   # Estadio Akron (Zapopan)
    "Monterrey": (25.669, -100.245),     # Estadio BBVA (Guadalupe)
    "Dallas": (32.748, -97.093),         # AT&T Stadium (Arlington)
    "Houston": (29.685, -95.411),        # NRG Stadium
    "Atlanta": (33.755, -84.401),        # Mercedes-Benz Stadium
    "Los Angeles": (33.953, -118.339),   # SoFi Stadium (Inglewood)
    "New York NJ": (40.813, -74.074),    # MetLife (East Rutherford)
    "Boston": (42.091, -71.264),         # Gillette (Foxborough)
    "Philadelphia": (39.901, -75.168),   # Lincoln Financial Field
    "Miami": (25.958, -80.239),          # Hard Rock (Miami Gardens)
    "Kansas City": (39.049, -94.484),    # Arrowhead
    "Seattle": (47.595, -122.332),       # Lumen Field
    "San Francisco": (37.403, -121.970), # Levi's (Santa Clara)
    "Toronto": (43.633, -79.419),        # BMO Field
    "Vancouver": (49.277, -123.112),     # BC Place
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
