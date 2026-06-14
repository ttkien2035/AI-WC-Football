"""Shared RapidAPI client for Sofascore + FotMob (one key, 500 req/month free).

Quota is precious, so EVERY response is cached to disk (data/rapid_cache/) keyed
by host+path+params — re-running a script costs ZERO quota. Each live call logs
the remaining monthly request count so we never blow the budget silently.

Key is read from the project .env (RAPIDAPI_KEY) or the env var of the same name.
Nothing here is committed-secret: .env and data/ are gitignored.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

CACHE = Path(__file__).parent / "data" / "rapid_cache"
_ENV_CACHE: dict[str, str] | None = None


def _load_env() -> dict[str, str]:
    global _ENV_CACHE
    if _ENV_CACHE is not None:
        return _ENV_CACHE
    env: dict[str, str] = {}
    p = Path(__file__).resolve()
    for parent in [p.parent, *p.parents]:
        f = parent / ".env"
        if f.exists():
            for line in f.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env.setdefault(k.strip(), v.strip())
            break
    _ENV_CACHE = env
    return env


def _conf(name: str, default: str = "") -> str:
    return os.environ.get(name) or _load_env().get(name, default)


SOFA_HOST = _conf("RAPIDAPI_SOFASCORE_HOST", "sofascore.p.rapidapi.com")
FOTMOB_HOST = _conf("RAPIDAPI_FOTMOB_HOST", "fotmob-api.p.rapidapi.com")

_KEYIDX = CACHE / ".keyidx"


def _keys() -> list[str]:
    """All configured keys, in rotation order (RAPIDAPI_KEY, _KEY1, _KEY2, ...)."""
    ks = []
    for name in ["RAPIDAPI_KEY", "RAPIDAPI_KEY1", "RAPIDAPI_KEY2",
                 "RAPIDAPI_KEY3", "RAPIDAPI_KEY4"]:
        v = _conf(name)
        if v and v not in ks:
            ks.append(v)
    return ks


def _cur_idx() -> int:
    try:
        return int(_KEYIDX.read_text().strip())
    except Exception:
        return 0


def _set_idx(i: int) -> None:
    try:
        _KEYIDX.parent.mkdir(parents=True, exist_ok=True)
        _KEYIDX.write_text(str(i))
    except Exception:
        pass


def _cache_path(host: str, path: str, params: dict | None) -> Path:
    q = urllib.parse.urlencode(sorted((params or {}).items()))
    h = hashlib.sha1(f"{host}{path}?{q}".encode()).hexdigest()[:16]
    safe = path.strip("/").replace("/", "_") or "root"
    return CACHE / host.split(".")[0] / f"{safe}_{h}.json"


def get(host: str, path: str, params: dict | None = None, *,
        ttl: float | None = None, verbose: bool = True):
    """GET with disk cache. ttl=None -> cache never expires (default; saves quota).
    Returns parsed JSON (or None on error). Set ttl in seconds for live data."""
    cp = _cache_path(host, path, params)
    if cp.exists():
        if ttl is None or (time.time() - cp.stat().st_mtime) < ttl:
            try:
                return json.loads(cp.read_text())
            except Exception:
                pass
    keys = _keys()
    if not keys:
        raise RuntimeError("no RAPIDAPI_KEY* set in .env or environment")
    url = f"https://{host}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)

    start = _cur_idx() % len(keys)
    for hop in range(len(keys)):           # try current key, rotate on exhaustion
        idx = (start + hop) % len(keys)
        req = urllib.request.Request(url, headers={
            "x-rapidapi-host": host, "x-rapidapi-key": keys[idx],
            "Content-Type": "application/json"})
        try:
            r = urllib.request.urlopen(req, timeout=25)
            body = r.read()
            rem = r.headers.get("X-RateLimit-Requests-Remaining")
            if verbose:
                print(f"  [rapid k{idx}] {host.split('.')[0]} {path} -> {r.status} "
                      f"(quota left: {rem})", flush=True)
            _set_idx(idx)
            # near-empty key -> advance so next call starts on a fresh one
            if rem is not None and rem.isdigit() and int(rem) <= 1:
                _set_idx((idx + 1) % len(keys))
            data = json.loads(body) if body else None
            cp.parent.mkdir(parents=True, exist_ok=True)
            cp.write_text(json.dumps(data))
            return data
        except urllib.error.HTTPError as e:
            rem = e.headers.get("X-RateLimit-Requests-Remaining")
            if e.code == 429:              # quota exhausted -> rotate to next key
                if verbose:
                    print(f"  [rapid k{idx}] 429 quota out -> rotating", flush=True)
                _set_idx((idx + 1) % len(keys))
                continue
            if verbose:
                print(f"  [rapid k{idx}] {host.split('.')[0]} {path} -> HTTP {e.code} "
                      f"(quota left: {rem})", flush=True)
            return None
        except Exception as e:
            if verbose:
                print(f"  [rapid k{idx}] {host.split('.')[0]} {path} -> ERR {type(e).__name__}",
                      flush=True)
            return None
    if verbose:
        print("  [rapid] all keys exhausted (429)", flush=True)
    return None


def sofa(path: str, params: dict | None = None, **kw):
    return get(SOFA_HOST, path, params, **kw)


def fotmob(path: str, params: dict | None = None, **kw):
    return get(FOTMOB_HOST, path, params, **kw)


def _ping(key: str):
    """Cheapest call to read a key's quota headers (costs 1 request on that key)."""
    req = urllib.request.Request(f"https://{FOTMOB_HOST}/api/v1/news/trending?ccode3=USA",
                                 headers={"x-rapidapi-host": FOTMOB_HOST, "x-rapidapi-key": key})
    try:
        r = urllib.request.urlopen(req, timeout=15)
        h = r.headers
    except urllib.error.HTTPError as e:
        h = e.headers
    except Exception:
        return None, None
    return h.get("X-RateLimit-Requests-Remaining"), h.get("X-RateLimit-Requests-Limit")


def audit_quota() -> list[dict]:
    """Ping every configured key and report remaining monthly quota.
    NOTE: this itself spends 1 request per key."""
    rep = []
    keys = _keys()
    print(f"=== RapidAPI quota audit ({len(keys)} keys) — costs 1 req/key ===")
    total_rem = 0
    for i, k in enumerate(keys):
        rem, lim = _ping(k)
        r = int(rem) if (rem and rem.isdigit()) else None
        if r is not None:
            total_rem += r
        flag = ""
        if r is not None:
            flag = "  <-- EXHAUSTED, add a new key" if r <= 2 else ("  <-- low" if r < 50 else "")
        print(f"  key{i} …{k[-6:]}  remaining {rem}/{lim}{flag}")
        rep.append({"idx": i, "tail": k[-6:], "remaining": r, "limit": lim})
    print(f"  TOTAL remaining across keys: {total_rem}")
    if total_rem < 50:
        print("  ⚠ pooled quota low — ask user for more RapidAPI keys to rotate")
    return rep


if __name__ == "__main__":
    audit_quota()
