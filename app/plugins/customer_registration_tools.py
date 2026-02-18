from __future__ import annotations

import os
import re
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field
from sqlalchemy import text

from app.infra.db import get_db_session
from app.plugins.base import Tool


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _now_utc_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def _hash_code(code: str) -> str:
    pepper = os.getenv("EMAIL_CODE_PEPPER", "dev-pepper-change-me")
    raw = f"{pepper}:{code}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _generate_code_6() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


class RegisterCustomerArgs(BaseModel):
    display_name: str = Field(..., min_length=2, max_length=200)
    email: str = Field(..., min_length=5, max_length=255)
    phone: Optional[str] = Field(default=None, max_length=50)


class VerifyEmailCodeArgs(BaseModel):
    email: str = Field(..., min_length=5, max_length=255)
    code: str = Field(..., min_length=6, max_length=6)

class ResendVerificationCodeArgs(BaseModel):
    email: str = Field(..., min_length=5, max_length=255)


class RegisterCustomerTool:
    name = "register_customer"
    description = "Registra cliente (pending) y envía código de verificación por email. Requiere confirmación."
    input_model = RegisterCustomerArgs
    scopes = ["write"]

    async def run(self, args: RegisterCustomerArgs, ctx: Dict[str, Any]) -> Dict[str, Any]:
        email = _normalize_email(args.email)
        if not EMAIL_RE.match(email):
            return {"ok": False, "error": "invalid_email"}

        ttl_minutes = int(os.getenv("EMAIL_CODE_TTL_MINUTES", "15"))
        expires_at = (_now_utc_naive() + timedelta(minutes=ttl_minutes))
        code = _generate_code_6()
        code_hash = _hash_code(code)

        db = get_db_session()
        try:
            row = db.execute(
                text("SELECT id, status FROM customers WHERE email = :email LIMIT 1"),
                {"email": email},
            ).fetchone()

            if row:
                customer_id, status = row
                if status == "verified":
                    return {"ok": True, "customer_id": str(customer_id), "status": "verified"}
                db.execute(
                    text("""
                        UPDATE customers
                        SET display_name = :display_name,
                            phone = :phone,
                            status = 'pending',
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = :id
                    """),
                    {"display_name": args.display_name.strip(), "phone": args.phone, "id": customer_id},
                )
            else:
                res = db.execute(
                    text("""
                        INSERT INTO customers (display_name, email, phone, status)
                        VALUES (:display_name, :email, :phone, 'pending')
                    """),
                    {"display_name": args.display_name.strip(), "email": email, "phone": args.phone},
                )
                customer_id = res.lastrowid

            # invalidar verificaciones anteriores pendientes
            db.execute(
                text("""
                    UPDATE email_verifications
                    SET used_at = COALESCE(used_at, CURRENT_TIMESTAMP)
                    WHERE customer_id = :cid AND used_at IS NULL
                """),
                {"cid": customer_id},
            )

            db.execute(
                text("""
                    INSERT INTO email_verifications (customer_id, code_hash, expires_at, attempts)
                    VALUES (:cid, :code_hash, :expires_at, 0)
                """),
                {"cid": customer_id, "code_hash": code_hash, "expires_at": expires_at},
            )
            db.commit()
        finally:
            db.close()

        # enviar email
        mailer = ctx.get("mailer")
        subject = "Tu código de verificación"
        body = (
            f"Hola {args.display_name.strip()},\n\n"
            f"Tu código de verificación es: {code}\n"
            f"Vence en {ttl_minutes} minutos.\n\n"
            f"Si no fuiste vos, ignorá este email.\n"
        )

        if not mailer:
            return {"ok": False, "error": "mailer_not_configured"}

        await mailer.send(to=email, subject=subject, body=body)

        return {
            "ok": True,
            "customer_id": str(customer_id),
            "status": "pending",
            "email_sent": True,
            "expires_in_minutes": ttl_minutes,
        }


class VerifyEmailCodeTool:
    name = "verify_email_code"
    description = "Verifica email con código de 6 dígitos."
    input_model = VerifyEmailCodeArgs
    scopes = ["read"]

    async def run(self, args: VerifyEmailCodeArgs, ctx: Dict[str, Any]) -> Dict[str, Any]:
        email = _normalize_email(args.email)
        code = (args.code or "").strip()

        if not EMAIL_RE.match(email):
            return {"ok": False, "error": "invalid_email"}
        if not (len(code) == 6 and code.isdigit()):
            return {"ok": False, "error": "invalid_code_format"}

        db = get_db_session()
        try:
            cust = db.execute(
                text("SELECT id, status FROM customers WHERE email = :email LIMIT 1"),
                {"email": email},
            ).fetchone()
            if not cust:
                return {"ok": False, "error": "invalid_code_or_expired"}

            customer_id, status = cust
            if status == "verified":
                return {"ok": True, "customer_id": str(customer_id), "status": "verified"}

            ev = db.execute(
                text("""
                    SELECT id, code_hash, expires_at, attempts
                    FROM email_verifications
                    WHERE customer_id = :cid AND used_at IS NULL
                    ORDER BY created_at DESC
                    LIMIT 1
                """),
                {"cid": customer_id},
            ).fetchone()

            if not ev:
                return {"ok": False, "error": "invalid_code_or_expired"}

            ev_id, code_hash, expires_at, attempts = ev
            now = _now_utc_naive()

            if expires_at < now:
                return {"ok": False, "error": "invalid_code_or_expired"}

            max_attempts = int(os.getenv("EMAIL_CODE_MAX_ATTEMPTS", "5"))
            if attempts >= max_attempts:
                return {"ok": False, "error": "too_many_attempts"}

            if _hash_code(code) != code_hash:
                db.execute(text("UPDATE email_verifications SET attempts = attempts + 1 WHERE id = :id"), {"id": ev_id})
                db.commit()
                return {"ok": False, "error": "invalid_code_or_expired"}

            db.execute(text("UPDATE email_verifications SET used_at = CURRENT_TIMESTAMP WHERE id = :id"), {"id": ev_id})
            db.execute(text("UPDATE customers SET status='verified', updated_at=CURRENT_TIMESTAMP WHERE id = :cid"),
                       {"cid": customer_id})
            db.commit()

            return {"ok": True, "customer_id": str(customer_id), "status": "verified"}
        finally:
            db.close()


class ResendVerificationCodeTool:
    name = "resend_verification_code"
    description = "Reenvía un nuevo código de verificación si el cliente está pendiente (invalida el anterior)."
    input_model = ResendVerificationCodeArgs
    scopes = ["read"]  # ✅ recomendado: no pedir confirmación

    async def run(self, args: ResendVerificationCodeArgs, ctx: Dict[str, Any]) -> Dict[str, Any]:
        email = _normalize_email(args.email)
        if not EMAIL_RE.match(email):
            return {"ok": False, "error": "invalid_email"}

        ttl_minutes = int(os.getenv("EMAIL_CODE_TTL_MINUTES", "15"))
        expires_at = (_now_utc_naive() + timedelta(minutes=ttl_minutes))

        code = _generate_code_6()
        code_hash = _hash_code(code)

        db = get_db_session()
        try:
            row = db.execute(
                text("SELECT id, status, display_name, phone FROM customers WHERE email = :email LIMIT 1"),
                {"email": email},
            ).fetchone()

            if not row:
                return {"ok": False, "error": "not_found"}

            customer_id, status, display_name, phone = row
            if status == "verified":
                return {"ok": True, "customer_id": str(customer_id), "status": "verified", "message": "Ya está verificado."}

            # invalidar verificaciones anteriores pendientes
            db.execute(
                text("""
                    UPDATE email_verifications
                    SET used_at = COALESCE(used_at, CURRENT_TIMESTAMP)
                    WHERE customer_id = :cid AND used_at IS NULL
                """),
                {"cid": customer_id},
            )

            db.execute(
                text("""
                    INSERT INTO email_verifications (customer_id, code_hash, expires_at, attempts)
                    VALUES (:cid, :code_hash, :expires_at, 0)
                """),
                {"cid": customer_id, "code_hash": code_hash, "expires_at": expires_at},
            )
            db.commit()
        finally:
            db.close()

        mailer = ctx.get("mailer")
        if not mailer:
            return {"ok": False, "error": "mailer_not_configured"}

        subject = "Tu nuevo código de verificación"
        body = (
            f"Hola {display_name or 'Cliente'},\n\n"
            f"Tu nuevo código es: {code}\n"
            f"Vence en {ttl_minutes} minutos.\n\n"
            f"Si no fuiste vos, ignorá este email.\n"
        )
        await mailer.send(to=email, subject=subject, body=body)

        resp = {
            "ok": True,
            "customer_id": str(customer_id),
            "status": "pending",
            "email_sent": True,
            "expires_in_minutes": ttl_minutes,
        }

        # opcional DEV
        if os.getenv("MAILER_DEV_RETURN_CODE", "0") == "1":
            resp["dev_code"] = code

        return resp




def register() -> List[Tool]:
    return [RegisterCustomerTool(), VerifyEmailCodeTool(), ResendVerificationCodeTool()]