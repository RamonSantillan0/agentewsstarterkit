import hmac
import hashlib
import time
from typing import Optional


def verify_webhook_signature(
    body: bytes,
    signature: str,
    timestamp: str,
    secret: str,
    replay_window_sec: int = 300,
    max_future_skew_sec: int = 30,  # tolerancia reloj proveedor
) -> bool:
    # 1) Validaciones básicas
    if not secret:
        return False
    if not signature:
        return False
    if not timestamp:
        return False

    # 2) Timestamp debe ser número (epoch seconds)
    try:
        ts = int(timestamp)
    except Exception:
        return False

    now = int(time.time())

    # 3) Anti-replay window: demasiado viejo o demasiado futuro => rechazo
    if ts < (now - replay_window_sec):
        return False
    if ts > (now + max_future_skew_sec):
        return False

    # 4) Construcción de mensaje a firmar (IMPORTANTE: esto debe coincidir con tu proveedor)
    # Patrón común: f"{timestamp}.{body}"
    msg = timestamp.encode("utf-8") + b"." + body

    expected = hmac.new(
        key=secret.encode("utf-8"),
        msg=msg,
        digestmod=hashlib.sha256,
    ).hexdigest()

    # 5) Comparación segura (evita timing attacks)
    return hmac.compare_digest(expected, signature)