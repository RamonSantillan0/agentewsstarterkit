from __future__ import annotations

import smtplib
from email.message import EmailMessage


class SMTPMailer:
    def __init__(self, settings) -> None:
        self.host = settings.SMTP_HOST
        self.port = settings.SMTP_PORT
        self.user = settings.SMTP_USER
        self.password = settings.SMTP_PASSWORD
        self.from_email = settings.SMTP_FROM or self.user

    async def send(self, to: str, subject: str, body: str) -> None:
        if not self.host or not self.user or not self.password:
            raise RuntimeError("SMTP no configurado (faltan SMTP_HOST/USER/PASSWORD).")

        msg = EmailMessage()
        msg["From"] = self.from_email
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)

        with smtplib.SMTP(self.host, self.port, timeout=20) as s:
            s.ehlo()
            s.starttls()
            s.ehlo()
            s.login(self.user, self.password)
            s.send_message(msg)