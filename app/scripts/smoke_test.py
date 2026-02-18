from __future__ import annotations

import json
import os
import sys
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Optional

import requests


# ----------------------------
# Config
# ----------------------------

@dataclass
class Cfg:
    base_url: str
    internal_api_key: str
    do_admin_cleanup: bool
    do_db_checks: bool
    do_burst: bool
    mysql_host: str
    mysql_port: int
    mysql_user: str
    mysql_pass: str
    mysql_db: str


def env_bool(name: str, default: str = "0") -> bool:
    v = os.getenv(name, default).strip().lower()
    return v in ("1", "true", "yes", "y", "on")


DEFAULT_TIMEOUT = int(os.getenv("SMOKE_TIMEOUT_SEC", "60"))


def load_cfg() -> Cfg:
    return Cfg(
        base_url=os.getenv("SMOKE_BASE_URL", "http://localhost:8000").rstrip("/"),
        internal_api_key=os.getenv("INTERNAL_API_KEY", ""),
        do_admin_cleanup=env_bool("SMOKE_ADMIN_CLEANUP", "0"),
        do_db_checks=env_bool("SMOKE_DB_CHECKS", "0"),
        do_burst=env_bool("SMOKE_DO_BURST", "0"),
        mysql_host=os.getenv("DB_HOST", "127.0.0.1"),
        mysql_port=int(os.getenv("DB_PORT", "3306")),
        mysql_user=os.getenv("DB_USER", "app_user"),
        mysql_pass=os.getenv("DB_PASS", "app_pass"),
        mysql_db=os.getenv("DB_NAME", "app_db"),
    )


def assert_true(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


# ----------------------------
# HTTP helpers
# ----------------------------

def post_json(
    url: str,
    payload: Dict[str, Any],
    headers: Optional[Dict[str, str]] = None,
    timeout: int = DEFAULT_TIMEOUT,
):
    h = {"Content-Type": "application/json"}
    if headers:
        h.update(headers)
    # requests ya serializa bien
    return requests.post(url, json=payload, headers=h, timeout=timeout)


def get(
    url: str,
    headers: Optional[Dict[str, str]] = None,
    timeout: int = DEFAULT_TIMEOUT,
):
    return requests.get(url, headers=headers or {}, timeout=timeout)


def pretty(obj: Any) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False, indent=2)
    except Exception:
        return str(obj)


# ----------------------------
# Optional steps
# ----------------------------

def run_admin_cleanup(cfg: Cfg) -> None:
    if not cfg.internal_api_key:
        print("[WARN] SMOKE_ADMIN_CLEANUP=1 pero INTERNAL_API_KEY está vacío. Salteo cleanup.")
        return

    headers = {"x-api-key": cfg.internal_api_key}
    r1 = requests.post(f"{cfg.base_url}/admin/cleanup/dedupe", headers=headers, timeout=DEFAULT_TIMEOUT)
    r2 = requests.post(f"{cfg.base_url}/admin/cleanup/sessions", headers=headers, timeout=DEFAULT_TIMEOUT)

    print("ADMIN cleanup dedupe:", r1.status_code, r1.text)
    print("ADMIN cleanup sessions:", r2.status_code, r2.text)

    assert_true(r1.status_code == 200, "Admin cleanup dedupe falló")
    assert_true(r2.status_code == 200, "Admin cleanup sessions falló")


def db_check_latest_rows(cfg: Cfg, session_id: str) -> None:
    # Requiere: pip install pymysql
    import pymysql  # type: ignore

    conn = pymysql.connect(
        host=cfg.mysql_host,
        port=cfg.mysql_port,
        user=cfg.mysql_user,
        password=cfg.mysql_pass,
        database=cfg.mysql_db,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )

    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, type, intent, channel, tool_name, confirmed, created_at "
                "FROM audit_events ORDER BY id DESC LIMIT 10"
            )
            rows = cur.fetchall()
            print("DB audit_events last 10:")
            print(pretty(rows))
            assert_true(len(rows) > 0, "No hay filas en audit_events (esperaba al menos 1)")

            cur.execute(
                "SELECT session_id, history_json, facts_json, updated_at, expires_at "
                "FROM sessions WHERE session_id = %s LIMIT 1",
                (session_id,),
            )
            srow = cur.fetchone()
            print("DB sessions row:")
            print(pretty(srow))
            assert_true(srow is not None, "No se encontró la session en DB (sessions)")
            assert_true("history_json" in srow and srow["history_json"], "history_json vacío en DB")
    finally:
        conn.close()


# ----------------------------
# Main
# ----------------------------

def main() -> int:
    cfg = load_cfg()
    run_id = uuid.uuid4().hex[:8]
    session_id = os.getenv("SMOKE_SESSION_ID", "+5491111111111")
    provider_url = f"{cfg.base_url}/provider/inbound"

    print("=== Smoke Test ===")
    print("BASE:", cfg.base_url)
    print("SESSION:", session_id)
    print("RUN_ID:", run_id)
    print("TIMEOUT:", DEFAULT_TIMEOUT, "sec")
    print("DO_BURST:", cfg.do_burst)

    # 0) health
    r = get(f"{cfg.base_url}/health")
    print("GET /health:", r.status_code, r.text)
    assert_true(r.status_code in (200, 204), "/health no respondió 200/204")

    # 1) provider inbound basic
    msg_id_1 = f"smoke-{run_id}-1"
    payload = {"message": "hola smoke", "from": session_id, "message_id": msg_id_1}
    r1 = post_json(provider_url, payload)
    print("POST /provider/inbound #1:", r1.status_code)
    assert_true(r1.status_code == 200, f"/provider/inbound no respondió 200: {r1.text}")
    j1 = r1.json()
    print("Response #1:", pretty(j1))
    assert_true("reply" in j1, "Respuesta no trae 'reply'")

    # 2) dedupe: mismo message_id debe devolver "Mensaje duplicado"
    r2 = post_json(provider_url, payload)
    print("POST /provider/inbound #2 (dedupe):", r2.status_code)
    assert_true(r2.status_code == 200, f"Dedupe request no respondió 200: {r2.text}")
    j2 = r2.json()
    print("Response #2:", pretty(j2))
    assert_true("duplicado" in (j2.get("reply") or "").lower(), "No detectó dedupe (no dice duplicado)")

    # 3) session accumulation: mandar 1 mensaje distinto (message_id distinto)
    msg_id_3 = f"smoke-{run_id}-3"
    r3 = post_json(provider_url, {"message": "hola smoke 2", "from": session_id, "message_id": msg_id_3})
    print("POST /provider/inbound #3:", r3.status_code)
    assert_true(r3.status_code == 200, f"Request #3 falló: {r3.text}")

    # 4) rate limit burst (opcional)
    if cfg.do_burst:
        print("Rate limit session burst (puede o no disparar según tu config)...")
        rate_limited = False
        for i in range(1, 8):
            mid = f"smoke-{run_id}-rl-{i}"
            rr = post_json(provider_url, {"message": f"spam {i}", "from": session_id, "message_id": mid})

            if rr.status_code == 429:
                print("HTTP 429 detected (IP rate limit):", rr.text)
                break

            try:
                jj = rr.json()
            except Exception:
                print("Non-JSON response:", rr.status_code, rr.text)
                break

            if jj.get("intent") == "rate_limited":
                rate_limited = True
                print("[OK] Session rate limit triggered:", pretty(jj))
                break

            time.sleep(0.1)

        if not rate_limited:
            print("[INFO] Session rate limit no se disparó (ok si tus límites son altos).")
    else:
        print("[INFO] Burst deshabilitado (SMOKE_DO_BURST=0).")

    # 5) admin cleanup opcional
    if cfg.do_admin_cleanup:
        run_admin_cleanup(cfg)

    # 6) DB checks opcional
    if cfg.do_db_checks:
        db_check_latest_rows(cfg, session_id=session_id)

    print("[OK] Smoke test OK")
    return 0


if __name__ == "__main__":
    # (Opcional) intentar que stdout sea UTF-8 sin romper en Windows
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

    try:
        raise SystemExit(main())
    except Exception as e:
        print("[FAIL] Smoke test FAILED:", repr(e))
        sys.exit(1)