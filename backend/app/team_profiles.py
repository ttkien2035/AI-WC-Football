"""Curated tactical profiles for the 48 WC-2026 teams (early-2026 snapshot).

- style: i18n tag keys rendered vi/en by the frontend
- key_players: used for display AND for the absence Elo penalty (-40·w per
  starter missing from the announced XI, capped at -80) — see service.predict.
- value_tier: 1 (modest) .. 5 (elite squad value) — display only.
Real lineups/formations from LiveScore override these defaults when published.
"""

PROFILES = {
    "CZE": {"formation": "4-2-3-1", "style": ["direct", "set_pieces"], "manager": "Ivan Hašek", "value_tier": 2,
            "key_players": [{"name": "Patrik Schick", "pos": "FW", "w": 1.0}, {"name": "Tomáš Souček", "pos": "MF", "w": 0.7}, {"name": "Antonín Kinský", "pos": "GK", "w": 0.7}]},
    "MEX": {"formation": "4-3-3", "style": ["possession", "wing_play"], "manager": "Javier Aguirre", "value_tier": 3,
            "key_players": [{"name": "Santiago Giménez", "pos": "FW", "w": 1.0}, {"name": "Edson Álvarez", "pos": "MF", "w": 1.0}, {"name": "César Montes", "pos": "DF", "w": 0.7}]},
    "RSA": {"formation": "4-3-3", "style": ["counter", "physical"], "manager": "Hugo Broos", "value_tier": 2,
            "key_players": [{"name": "Ronwen Williams", "pos": "GK", "w": 1.0}, {"name": "Themba Zwane", "pos": "MF", "w": 0.7}, {"name": "Lyle Foster", "pos": "FW", "w": 0.7}]},
    "KOR": {"formation": "4-2-3-1", "style": ["transition", "technical"], "manager": "Hong Myung-bo", "value_tier": 3,
            "key_players": [{"name": "Son Heung-min", "pos": "FW", "w": 1.0}, {"name": "Lee Kang-in", "pos": "MF", "w": 1.0}, {"name": "Kim Min-jae", "pos": "DF", "w": 1.0}]},
    "BIH": {"formation": "4-2-3-1", "style": ["direct", "physical"], "manager": "Sergej Barbarez", "value_tier": 2,
            "key_players": [{"name": "Edin Džeko", "pos": "FW", "w": 0.7}, {"name": "Ermedin Demirović", "pos": "FW", "w": 1.0}, {"name": "Anel Ahmedhodžić", "pos": "DF", "w": 0.7}]},
    "CAN": {"formation": "3-5-2", "style": ["high_press", "physical"], "manager": "Jesse Marsch", "value_tier": 3,
            "key_players": [{"name": "Alphonso Davies", "pos": "DF", "w": 1.0}, {"name": "Jonathan David", "pos": "FW", "w": 1.0}, {"name": "Stephen Eustáquio", "pos": "MF", "w": 0.7}]},
    "QAT": {"formation": "5-3-2", "style": ["possession", "counter"], "manager": "Julen Lopetegui", "value_tier": 1,
            "key_players": [{"name": "Akram Afif", "pos": "FW", "w": 1.0}, {"name": "Almoez Ali", "pos": "FW", "w": 0.7}, {"name": "Meshaal Barsham", "pos": "GK", "w": 0.7}]},
    "SUI": {"formation": "4-2-3-1", "style": ["possession", "set_pieces"], "manager": "Murat Yakin", "value_tier": 3,
            "key_players": [{"name": "Granit Xhaka", "pos": "MF", "w": 1.0}, {"name": "Breel Embolo", "pos": "FW", "w": 0.7}, {"name": "Dan Ndoye", "pos": "FW", "w": 0.7}]},
    "BRA": {"formation": "4-2-3-1", "style": ["technical", "transition"], "manager": "Carlo Ancelotti", "value_tier": 5,
            "key_players": [{"name": "Vinícius Júnior", "pos": "FW", "w": 1.0}, {"name": "Rodrygo", "pos": "FW", "w": 0.7}, {"name": "Alisson", "pos": "GK", "w": 0.7}]},
    "MAR": {"formation": "4-3-3", "style": ["counter", "physical"], "manager": "Walid Regragui", "value_tier": 4,
            "key_players": [{"name": "Achraf Hakimi", "pos": "DF", "w": 1.0}, {"name": "Brahim Díaz", "pos": "FW", "w": 0.7}, {"name": "Yassine Bounou", "pos": "GK", "w": 0.7}]},
    "HAI": {"formation": "4-4-2", "style": ["counter", "direct"], "manager": "Sébastien Migné", "value_tier": 1,
            "key_players": [{"name": "Frantzdy Pierrot", "pos": "FW", "w": 1.0}, {"name": "Danley Jean Jacques", "pos": "MF", "w": 0.7}, {"name": "Duckens Nazon", "pos": "FW", "w": 0.7}]},
    "SCO": {"formation": "5-3-2", "style": ["low_block", "set_pieces"], "manager": "Steve Clarke", "value_tier": 2,
            "key_players": [{"name": "Scott McTominay", "pos": "MF", "w": 1.0}, {"name": "Andrew Robertson", "pos": "DF", "w": 0.7}, {"name": "John McGinn", "pos": "MF", "w": 0.7}]},
    "TUR": {"formation": "4-2-3-1", "style": ["technical", "transition"], "manager": "Vincenzo Montella", "value_tier": 4,
            "key_players": [{"name": "Arda Güler", "pos": "MF", "w": 1.0}, {"name": "Hakan Çalhanoğlu", "pos": "MF", "w": 1.0}, {"name": "Kenan Yıldız", "pos": "FW", "w": 0.7}]},
    "USA": {"formation": "4-3-3", "style": ["high_press", "transition"], "manager": "Mauricio Pochettino", "value_tier": 3,
            "key_players": [{"name": "Christian Pulisic", "pos": "FW", "w": 1.0}, {"name": "Weston McKennie", "pos": "MF", "w": 0.7}, {"name": "Antonee Robinson", "pos": "DF", "w": 0.7}]},
    "PAR": {"formation": "4-4-2", "style": ["low_block", "counter"], "manager": "Gustavo Alfaro", "value_tier": 2,
            "key_players": [{"name": "Miguel Almirón", "pos": "FW", "w": 0.7}, {"name": "Julio Enciso", "pos": "FW", "w": 1.0}, {"name": "Gustavo Gómez", "pos": "DF", "w": 0.7}]},
    "AUS": {"formation": "4-4-2", "style": ["physical", "set_pieces"], "manager": "Tony Popovic", "value_tier": 2,
            "key_players": [{"name": "Jackson Irvine", "pos": "MF", "w": 0.7}, {"name": "Harry Souttar", "pos": "DF", "w": 0.7}, {"name": "Nestory Irankunda", "pos": "FW", "w": 0.7}]},
    "GER": {"formation": "4-2-3-1", "style": ["possession", "high_press"], "manager": "Julian Nagelsmann", "value_tier": 5,
            "key_players": [{"name": "Florian Wirtz", "pos": "MF", "w": 1.0}, {"name": "Jamal Musiala", "pos": "MF", "w": 1.0}, {"name": "Joshua Kimmich", "pos": "MF", "w": 0.7}]},
    "CUW": {"formation": "4-3-3", "style": ["counter", "technical"], "manager": "Dick Advocaat", "value_tier": 1,
            "key_players": [{"name": "Leandro Bacuna", "pos": "MF", "w": 0.7}, {"name": "Tahith Chong", "pos": "FW", "w": 0.7}, {"name": "Eloy Room", "pos": "GK", "w": 0.7}]},
    "CIV": {"formation": "4-3-3", "style": ["physical", "transition"], "manager": "Emerse Faé", "value_tier": 3,
            "key_players": [{"name": "Franck Kessié", "pos": "MF", "w": 0.7}, {"name": "Amad Diallo", "pos": "FW", "w": 1.0}, {"name": "Simon Adingra", "pos": "FW", "w": 0.7}]},
    "ECU": {"formation": "4-4-2", "style": ["physical", "transition"], "manager": "Sebastián Beccacece", "value_tier": 3,
            "key_players": [{"name": "Moisés Caicedo", "pos": "MF", "w": 1.0}, {"name": "Piero Hincapié", "pos": "DF", "w": 0.7}, {"name": "Kendry Páez", "pos": "MF", "w": 0.7}]},
    "SWE": {"formation": "4-4-2", "style": ["direct", "counter"], "manager": "Graham Potter", "value_tier": 3,
            "key_players": [{"name": "Alexander Isak", "pos": "FW", "w": 1.0}, {"name": "Viktor Gyökeres", "pos": "FW", "w": 1.0}, {"name": "Dejan Kulusevski", "pos": "MF", "w": 0.7}]},
    "NED": {"formation": "4-3-3", "style": ["possession", "high_press"], "manager": "Ronald Koeman", "value_tier": 4,
            "key_players": [{"name": "Virgil van Dijk", "pos": "DF", "w": 1.0}, {"name": "Frenkie de Jong", "pos": "MF", "w": 1.0}, {"name": "Cody Gakpo", "pos": "FW", "w": 0.7}]},
    "JPN": {"formation": "3-4-2-1", "style": ["technical", "high_press"], "manager": "Hajime Moriyasu", "value_tier": 4,
            "key_players": [{"name": "Kaoru Mitoma", "pos": "FW", "w": 1.0}, {"name": "Takefusa Kubo", "pos": "FW", "w": 1.0}, {"name": "Wataru Endo", "pos": "MF", "w": 0.7}]},
    "TUN": {"formation": "4-3-3", "style": ["low_block", "counter"], "manager": "Sami Trabelsi", "value_tier": 2,
            "key_players": [{"name": "Hannibal Mejbri", "pos": "MF", "w": 0.7}, {"name": "Elias Achouri", "pos": "FW", "w": 0.7}, {"name": "Montassar Talbi", "pos": "DF", "w": 0.7}]},
    "BEL": {"formation": "4-2-3-1", "style": ["transition", "technical"], "manager": "Rudi Garcia", "value_tier": 4,
            "key_players": [{"name": "Jérémy Doku", "pos": "FW", "w": 1.0}, {"name": "Kevin De Bruyne", "pos": "MF", "w": 0.7}, {"name": "Loïs Openda", "pos": "FW", "w": 0.7}]},
    "EGY": {"formation": "4-3-3", "style": ["counter", "low_block"], "manager": "Hossam Hassan", "value_tier": 3,
            "key_players": [{"name": "Mohamed Salah", "pos": "FW", "w": 1.0}, {"name": "Omar Marmoush", "pos": "FW", "w": 1.0}, {"name": "Mohamed Elneny", "pos": "MF", "w": 0.5}]},
    "IRN": {"formation": "4-3-3", "style": ["direct", "counter"], "manager": "Amir Ghalenoei", "value_tier": 2,
            "key_players": [{"name": "Mehdi Taremi", "pos": "FW", "w": 1.0}, {"name": "Sardar Azmoun", "pos": "FW", "w": 0.7}, {"name": "Alireza Beiranvand", "pos": "GK", "w": 0.7}]},
    "NZL": {"formation": "4-4-2", "style": ["low_block", "direct"], "manager": "Darren Bazeley", "value_tier": 1,
            "key_players": [{"name": "Chris Wood", "pos": "FW", "w": 1.0}, {"name": "Sarpreet Singh", "pos": "MF", "w": 0.7}, {"name": "Michael Boxall", "pos": "DF", "w": 0.5}]},
    "ESP": {"formation": "4-3-3", "style": ["possession", "high_press"], "manager": "Luis de la Fuente", "value_tier": 5,
            "key_players": [{"name": "Lamine Yamal", "pos": "FW", "w": 1.0}, {"name": "Pedri", "pos": "MF", "w": 1.0}, {"name": "Rodri", "pos": "MF", "w": 1.0}]},
    "CPV": {"formation": "4-4-2", "style": ["counter", "physical"], "manager": "Pedro Brito (Bubista)", "value_tier": 1,
            "key_players": [{"name": "Ryan Mendes", "pos": "FW", "w": 0.7}, {"name": "Jamiro Monteiro", "pos": "MF", "w": 0.7}, {"name": "Vozinha", "pos": "GK", "w": 0.5}]},
    "KSA": {"formation": "4-3-3", "style": ["possession", "counter"], "manager": "Hervé Renard", "value_tier": 2,
            "key_players": [{"name": "Salem Al-Dawsari", "pos": "FW", "w": 1.0}, {"name": "Mohamed Kanno", "pos": "MF", "w": 0.7}, {"name": "Saleh Al-Shehri", "pos": "FW", "w": 0.5}]},
    "URY": {"formation": "4-3-3", "style": ["high_press", "transition"], "manager": "Marcelo Bielsa", "value_tier": 4,
            "key_players": [{"name": "Federico Valverde", "pos": "MF", "w": 1.0}, {"name": "Darwin Núñez", "pos": "FW", "w": 0.7}, {"name": "Ronald Araújo", "pos": "DF", "w": 0.7}]},
    "IRQ": {"formation": "4-2-3-1", "style": ["direct", "set_pieces"], "manager": "Graham Arnold", "value_tier": 1,
            "key_players": [{"name": "Aymen Hussein", "pos": "FW", "w": 1.0}, {"name": "Ali Jasim", "pos": "FW", "w": 0.7}, {"name": "Jalal Hassan", "pos": "GK", "w": 0.5}]},
    "FRA": {"formation": "4-3-3", "style": ["transition", "counter"], "manager": "Didier Deschamps", "value_tier": 5,
            "key_players": [{"name": "Kylian Mbappé", "pos": "FW", "w": 1.0}, {"name": "Aurélien Tchouaméni", "pos": "MF", "w": 0.7}, {"name": "William Saliba", "pos": "DF", "w": 0.7}]},
    "SEN": {"formation": "4-3-3", "style": ["physical", "transition"], "manager": "Pape Thiaw", "value_tier": 3,
            "key_players": [{"name": "Sadio Mané", "pos": "FW", "w": 1.0}, {"name": "Pape Matar Sarr", "pos": "MF", "w": 0.7}, {"name": "Kalidou Koulibaly", "pos": "DF", "w": 0.7}]},
    "NOR": {"formation": "4-3-3", "style": ["direct", "transition"], "manager": "Ståle Solbakken", "value_tier": 4,
            "key_players": [{"name": "Erling Haaland", "pos": "FW", "w": 1.0}, {"name": "Martin Ødegaard", "pos": "MF", "w": 1.0}, {"name": "Alexander Sørloth", "pos": "FW", "w": 0.7}]},
    "ARG": {"formation": "4-3-3", "style": ["possession", "technical"], "manager": "Lionel Scaloni", "value_tier": 5,
            "key_players": [{"name": "Lionel Messi", "pos": "FW", "w": 1.0}, {"name": "Julián Álvarez", "pos": "FW", "w": 1.0}, {"name": "Enzo Fernández", "pos": "MF", "w": 0.7}]},
    "ALG": {"formation": "4-3-3", "style": ["technical", "counter"], "manager": "Vladimir Petković", "value_tier": 3,
            "key_players": [{"name": "Riyad Mahrez", "pos": "FW", "w": 0.7}, {"name": "Mohamed Amoura", "pos": "FW", "w": 1.0}, {"name": "Amine Gouiri", "pos": "FW", "w": 0.7}]},
    "AUT": {"formation": "4-2-2-2", "style": ["high_press", "physical"], "manager": "Ralf Rangnick", "value_tier": 3,
            "key_players": [{"name": "Marcel Sabitzer", "pos": "MF", "w": 0.7}, {"name": "Christoph Baumgartner", "pos": "MF", "w": 0.7}, {"name": "David Alaba", "pos": "DF", "w": 0.7}]},
    "JOR": {"formation": "4-3-3", "style": ["counter", "physical"], "manager": "Jamal Sellami", "value_tier": 1,
            "key_players": [{"name": "Mousa Al-Taamari", "pos": "FW", "w": 1.0}, {"name": "Yazan Al-Naimat", "pos": "FW", "w": 0.7}, {"name": "Yazeed Abulaila", "pos": "GK", "w": 0.5}]},
    "COD": {"formation": "4-3-3", "style": ["physical", "transition"], "manager": "Sébastien Desabre", "value_tier": 2,
            "key_players": [{"name": "Yoane Wissa", "pos": "FW", "w": 1.0}, {"name": "Cédric Bakambu", "pos": "FW", "w": 0.7}, {"name": "Chancel Mbemba", "pos": "DF", "w": 0.7}]},
    "POR": {"formation": "4-2-3-1", "style": ["possession", "technical"], "manager": "Roberto Martínez", "value_tier": 5,
            "key_players": [{"name": "Bruno Fernandes", "pos": "MF", "w": 1.0}, {"name": "Rafael Leão", "pos": "FW", "w": 0.7}, {"name": "Vitinha", "pos": "MF", "w": 0.7}]},
    "UZB": {"formation": "4-2-3-1", "style": ["counter", "technical"], "manager": "Fabio Cannavaro", "value_tier": 2,
            "key_players": [{"name": "Abdukodir Khusanov", "pos": "DF", "w": 1.0}, {"name": "Abbosbek Fayzullaev", "pos": "MF", "w": 0.7}, {"name": "Eldor Shomurodov", "pos": "FW", "w": 0.7}]},
    "COL": {"formation": "4-2-3-1", "style": ["possession", "wing_play"], "manager": "Néstor Lorenzo", "value_tier": 4,
            "key_players": [{"name": "Luis Díaz", "pos": "FW", "w": 1.0}, {"name": "James Rodríguez", "pos": "MF", "w": 0.7}, {"name": "Richard Ríos", "pos": "MF", "w": 0.7}]},
    "ENG": {"formation": "4-2-3-1", "style": ["possession", "set_pieces"], "manager": "Thomas Tuchel", "value_tier": 5,
            "key_players": [{"name": "Harry Kane", "pos": "FW", "w": 1.0}, {"name": "Jude Bellingham", "pos": "MF", "w": 1.0}, {"name": "Bukayo Saka", "pos": "FW", "w": 1.0}]},
    "CRO": {"formation": "4-3-3", "style": ["possession", "technical"], "manager": "Zlatko Dalić", "value_tier": 4,
            "key_players": [{"name": "Luka Modrić", "pos": "MF", "w": 0.7}, {"name": "Joško Gvardiol", "pos": "DF", "w": 1.0}, {"name": "Mateo Kovačić", "pos": "MF", "w": 0.7}]},
    "GHA": {"formation": "4-3-3", "style": ["transition", "physical"], "manager": "Otto Addo", "value_tier": 3,
            "key_players": [{"name": "Mohammed Kudus", "pos": "FW", "w": 1.0}, {"name": "Antoine Semenyo", "pos": "FW", "w": 1.0}, {"name": "Thomas Partey", "pos": "MF", "w": 0.5}]},
    "PAN": {"formation": "4-4-2", "style": ["low_block", "counter"], "manager": "Thomas Christiansen", "value_tier": 1,
            "key_players": [{"name": "Adalberto Carrasquilla", "pos": "MF", "w": 1.0}, {"name": "José Fajardo", "pos": "FW", "w": 0.7}, {"name": "Orlando Mosquera", "pos": "GK", "w": 0.5}]},
}

ABSENCE_ELO_PER_STAR = 40.0   # x player weight w; literature: 10-25% odds shift
ABSENCE_ELO_CAP = 80.0


def normalize_name(s: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c)).lower().strip()


def absence_penalty(tla: str, lineup_players: list[dict] | None) -> tuple[float, list[dict]]:
    """(-elo_penalty, key_players_with_status). Status: in_xi | missing | unknown.
    Only penalize when an XI is actually announced."""
    prof = PROFILES.get(tla)
    if not prof:
        return 0.0, []
    if not lineup_players:
        return 0.0, [{**kp, "status": "unknown"} for kp in prof["key_players"]]
    xi = {normalize_name(p["name"]) for p in lineup_players}

    def in_xi(kp):  # last-name fallback: diacritics/short-name variants
        n = normalize_name(kp["name"])
        return n in xi or any(n.split()[-1] in x.split() for x in xi)

    out, penalty = [], 0.0
    for kp in prof["key_players"]:
        ok = in_xi(kp)
        out.append({**kp, "status": "in_xi" if ok else "missing"})
        if not ok:
            penalty += ABSENCE_ELO_PER_STAR * kp.get("w", 0.7)
    return min(penalty, ABSENCE_ELO_CAP), out
