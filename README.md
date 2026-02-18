# Starter Kit — LLM Planner + Tool Plugins (FastAPI + MySQL)

Template reutilizable para construir **agentes con “planner”**: el LLM genera un **plan JSON estricto** (validado con Pydantic) y el backend ejecuta herramientas (tools/plugins) de forma segura.

> Pensado para agentes de soporte, ventas, backoffice, contabilidad, etc. Cambiás tools + prompts y reutilizás el core.

## Qué trae

- **FastAPI** con endpoints multi‑canal:
  - `POST /agent` (web)
  - `POST /wa/agent` (canal estilo WhatsApp, protegido con API key)
  - `POST /provider/inbound` (webhook de proveedor: dedupe + firma HMAC + anti‑replay)
  - `GET /health`
- **Orquestador**:
  - Planner (LLM → JSON) → ejecución de tools → respuesta
  - Confirmación en 2 pasos para acciones `write` (`confirm <token>`)
  - Dedupe de mensajes y auditoría
- **Tool Registry** (allowlist): el LLM solo puede llamar tools registradas y con schema de args real.
- **Persistencia MySQL**:
  - sesiones, dedupe, auditoría, confirmaciones pendientes
- **Ejemplos de tools** (mock + registro/confirmación de cliente por email)
- **Dockerfile** + `render.yaml` para deploy

## Arquitectura (alto nivel)

1) Usuario envía mensaje (web/wa/provider)
2) `AgentOrchestrator` arma contexto (historial + facts) y llama al **Planner**
3) Planner devuelve **plan JSON** validado por `PlannerOutput`
4) Se ejecutan **tool_calls** (solo allowlisted)
5) Si hay `write`, se genera **token de confirmación**
6) Se arma la respuesta final (con Answerer opcional)

## Requisitos

- Python 3.11+ (recomendado)
- MySQL 8+ (o compatible)
- Acceso a tu proveedor LLM (ej: Ollama Cloud o endpoint compatible)

## Setup local (rápido)

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env

uvicorn app.main:app --reload --port 8000
```

Abrí: `http://localhost:8000/docs`

## Variables de entorno (mínimas)

Usá `.env.example` como base. Las más importantes:

- `INTERNAL_API_KEY` → protege `/wa/agent`
- `DB_URL` → conexión MySQL (SQLAlchemy URL)
- `OLLAMA_BASE_URL`, `OLLAMA_API_KEY`, `OLLAMA_MODEL` → proveedor LLM
- `PROVIDER_HMAC_SECRET` / `PROVIDER_VERIFY_SIGNATURE` → firma webhook `/provider/inbound`
- `PROVIDER_MAX_SKEW_SEC` → anti‑replay

⚠️ **No versionar** `.env` con secretos.

## Endpoints principales

### Health
```bash
curl http://localhost:8000/health
```

### Web chat
```bash
curl -X POST http://localhost:8000/agent \
  -H 'Content-Type: application/json' \
  -d '{"message":"hola","session_id":"demo"}'
```

### WhatsApp style (protegido)
```bash
curl -X POST http://localhost:8000/wa/agent \
  -H 'Content-Type: application/json' \
  -H 'x-api-key: <TU_INTERNAL_API_KEY>' \
  -d '{"message":"hola","session_id":"+549..."}'
```

### Webhook proveedor (entrada real)
Tu proveedor (Twilio/YCloud/n8n/etc.) hace POST a:

- `POST /provider/inbound`

Este endpoint aplica:
- validación de tamaño
- verificación de firma HMAC (opcional)
- anti‑replay por timestamp
- dedupe de mensajes

## Confirmaciones en 2 pasos (write safety)

Para tools marcadas como `write`, el agente no ejecuta el cambio sin confirmación:

1) Usuario solicita acción (ej: registrar algo)
2) Backend devuelve un token: `confirm <token>`
3) Usuario responde con `confirm <token>`
4) Backend ejecuta y audita

Esto evita operaciones peligrosas por alucinaciones o mensajes ambiguos.

## Base de datos

El proyecto incluye bootstrap/DDL para crear tablas necesarias (según tu implementación actual).

Tablas típicas:
- `sessions`
- `dedupe_messages`
- `audit_events`
- `pending_confirmations`
- (opcionales) `customers`, `email_verifications`

## Agregar tus propias tools (plugins)

1) Crear una clase Tool con:
- `name`, `description`
- `input_model` (Pydantic)
- `run()` (la lógica)

2) Registrarla en `ToolRegistry`.

3) (Opcional) marcar como `write` para exigir confirmación.

La ventaja: el Planner recibe el **JSON Schema real** de cada tool, así reduce errores de parámetros.

## Docker

```bash
docker build -t llm-planner .
docker run --rm -p 8000:8000 --env-file .env llm-planner
```

## Deploy en Render

- Usá `render.yaml` (Blueprint)
- Seteá variables en Render (no en el repo)
- Conectá a una DB MySQL (o tu servicio externo)

## Seguridad (recomendado)

- Rotar secretos si alguna vez se publicaron.
- Mantener `PROVIDER_VERIFY_SIGNATURE=1` en producción.
- Activar anti‑replay y dedupe persistente.
- Limitar tools `write` y exigir confirmación.

## Troubleshooting

- **Errores MySQL**: verificá que `DB_URL` apunte a la DB correcta y que el schema esté aplicado.
- **El webhook se procesa dos veces**: asegurate de usar dedupe persistente (MySQL) en todos los canales.
- **Planner devuelve JSON inválido**: revisá prompt del planner y el schema `PlannerOutput`.

---

### License
Elegí la licencia que prefieras (MIT/Apache-2.0/propietaria) y agregala como `LICENSE`.
