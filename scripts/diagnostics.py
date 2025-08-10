#!/usr/bin/env python
"""Diagnostic script for FutureSignalBot environment & external services.

Safely tests:
 - Python & platform info
 - Presence & length (masked) of critical environment variables
 - Config loading fallback effectiveness
 - Telegram getMe reachability
 - MEXC public time endpoint reachability
 - Coinglass (if key present) simple endpoint
 - Gemini API basic model listing (if key present)

Outputs a structured summary (print + JSON). Secrets are masked.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import socket
import sys
import time
from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional
import importlib

try:
    import requests  # type: ignore
except Exception as e:  # pragma: no cover
    print(f"[WARN] requests import failed: {e}")
    requests = None  # type: ignore


def _mask(val: str, keep: int = 4) -> str:
    if not val:
        return ""
    if len(val) <= keep:
        return "*" * len(val)
    return val[:keep] + "..." + ("*" * 4)


@dataclass
class SectionResult:
    ok: bool
    detail: str = ""
    extra: Optional[Dict[str, Any]] = None


@dataclass
class Diagnostics:
    python: SectionResult
    env_vars: SectionResult
    config: SectionResult
    telegram: SectionResult
    mexc: SectionResult
    coinglass: SectionResult
    gemini: SectionResult
    meta: Dict[str, Any]


def check_python() -> SectionResult:
    return SectionResult(
        ok=True,
        detail=f"Python {platform.python_version()} ({sys.executable}) on {platform.platform()}",
        extra={"cwd": os.getcwd()},
    )


def check_env_vars() -> SectionResult:
    keys = [
        "TELEGRAM_BOT_TOKEN",
        "MEXC_API_KEY",
        "MEXC_SECRET_KEY",
        "COINGLASS_API_KEY",
        "GEMINI_API_KEY",
    ]
    present = {}
    missing = []
    for k in keys:
        v = os.getenv(k, "")
        if v:
            present[k] = _mask(v)
        else:
            missing.append(k)
    ok = "TELEGRAM_BOT_TOKEN" in present
    detail = "Loaded" if ok else "Telegram token missing"
    return SectionResult(ok=ok, detail=detail, extra={"present": present, "missing": missing})


def load_config_module() -> SectionResult:
    try:
        cfg_mod = importlib.import_module("config")
        token = getattr(cfg_mod, "Config").TELEGRAM_BOT_TOKEN  # type: ignore
        return SectionResult(
            ok=bool(token),
            detail="Config loaded" if token else "Config token empty",
            extra={"token_mask": _mask(token)},
        )
    except Exception as e:  # pragma: no cover
        return SectionResult(ok=False, detail=f"Import failed: {e}")


def check_telegram(no_network: bool = False) -> SectionResult:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token:
        return SectionResult(ok=False, detail="No token in env")
    if no_network or requests is None:
        return SectionResult(ok=True, detail="Network skipped", extra={"token_prefix": token.split(':')[0][:4]})
    url = f"https://api.telegram.org/bot{token}/getMe"
    try:
        r = requests.get(url, timeout=10)
        ok = False
        j: Dict[str, Any] = {}
        try:
            j = r.json()
            ok = bool(j.get("ok"))
        except Exception:
            pass
        return SectionResult(
            ok=ok,
            detail=f"HTTP {r.status_code}",
            extra={"raw_ok": j.get("ok"), "description": j.get("description")},
        )
    except Exception as e:  # pragma: no cover
        return SectionResult(ok=False, detail=str(e))


def check_mexc(no_network: bool = False) -> SectionResult:
    if no_network or requests is None:
        return SectionResult(ok=True, detail="Network skipped")
    url = "https://api.mexc.fm/api/v3/time"
    try:
        r = requests.get(url, timeout=10)
        ok = r.status_code == 200
        return SectionResult(ok=ok, detail=f"HTTP {r.status_code}")
    except Exception as e:
        return SectionResult(ok=False, detail=str(e))


def check_coinglass(no_network: bool = False) -> SectionResult:
    key = os.getenv("COINGLASS_API_KEY", "")
    if not key:
        return SectionResult(ok=True, detail="No key (optional)")
    if no_network or requests is None:
        return SectionResult(ok=True, detail="Network skipped")
    url = "https://open-api-v4.coinglass.com/api/index/fear-and-greed?size=1"
    try:
        r = requests.get(url, headers={"CG-API-KEY": key}, timeout=15)
        ok = r.status_code == 200
        extra: Dict[str, Any] = {"status": r.status_code}
        if ok:
            try:
                data = r.json()
                extra["data_keys"] = list(data.keys())[:5]
            except Exception:
                pass
        return SectionResult(ok=ok, detail=f"HTTP {r.status_code}", extra=extra)
    except Exception as e:
        return SectionResult(ok=False, detail=str(e))


def check_gemini(no_network: bool = False) -> SectionResult:
    key = os.getenv("GEMINI_API_KEY", "")
    if not key:
        return SectionResult(ok=True, detail="No key (optional)")
    if no_network:
        return SectionResult(ok=True, detail="Network skipped")
    try:
        import google.genai as genai  # type: ignore
        client = genai.Client(api_key=key)
        models = []
        try:
            for m in client.models.list():  # type: ignore
                models.append(getattr(m, "name", str(m)))
                if len(models) >= 1:
                    break
        except Exception as inner:
            return SectionResult(ok=False, detail=f"List failed: {inner}")
        return SectionResult(ok=True, detail="Model list ok", extra={"sample_model": models[0] if models else None})
    except Exception as e:  # pragma: no cover
        return SectionResult(ok=False, detail=f"Import/client error: {e}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Diagnostics for FutureSignalBot")
    ap.add_argument("--json", action="store_true", help="Only output JSON result")
    ap.add_argument("--no-network", action="store_true", help="Skip network calls")
    args = ap.parse_args()

    started = time.time()
    results = Diagnostics(
        python=check_python(),
        env_vars=check_env_vars(),
        config=load_config_module(),
        telegram=check_telegram(no_network=args.no_network),
        mexc=check_mexc(no_network=args.no_network),
        coinglass=check_coinglass(no_network=args.no_network),
        gemini=check_gemini(no_network=args.no_network),
        meta={
            "hostname": socket.gethostname(),
            "duration_sec": round(time.time() - started, 3),
            "no_network": args.no_network,
        },
    )

    data = asdict(results)
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return

    print("==== FutureSignalBot Diagnostics ====")
    for section in [
        ("Python", results.python),
        ("Env Vars", results.env_vars),
        ("Config", results.config),
        ("Telegram", results.telegram),
        ("MEXC", results.mexc),
        ("Coinglass", results.coinglass),
        ("Gemini", results.gemini),
    ]:
        name, res = section
        status = "OK" if res.ok else "FAIL"
        print(f"[{name:<9}] {status} - {res.detail}")
        if res.extra:
            print(f"    extra: {res.extra}")
    print(f"Meta: {results.meta}")

    if not results.telegram.ok:
        sys.exit(2)


if __name__ == "__main__":
    main()
