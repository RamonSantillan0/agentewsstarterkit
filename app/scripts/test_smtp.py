from dotenv import load_dotenv
load_dotenv()  # carga el .env desde el directorio actual

import os
import smtplib
from email.message import EmailMessage

host = os.getenv("SMTP_HOST", "")
port = int(os.getenv("SMTP_PORT", "587"))
user = os.getenv("SMTP_USER", "")
password = os.getenv("SMTP_PASSWORD", "")
from_email = os.getenv("SMTP_FROM", user)
to = os.getenv("SMTP_TO", "")

print("HOST=", repr(host), "PORT=", port, "FROM=", from_email, "TO=", to)  # debug rápido

if not host or not user or not password or not to:
    raise RuntimeError("Faltan variables SMTP en el entorno (.env no cargado o valores vacíos).")

msg = EmailMessage()
msg["From"] = from_email
msg["To"] = to
msg["Subject"] = "Test Gmail SMTP desde Python"
msg.set_content("Si recibís esto, tu SMTP está OK.")

with smtplib.SMTP(host, port, timeout=20) as s:
    s.set_debuglevel(1)  # opcional: muestra el diálogo SMTP
    s.ehlo()
    s.starttls()
    s.ehlo()
    s.login(user, password)
    s.send_message(msg)

print("OK: enviado")