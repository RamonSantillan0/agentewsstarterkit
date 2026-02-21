from __future__ import annotations

import json
from typing import Any, Dict, Optional

from app.settings import Settings
from app.agent.schema import AgentResponse, UserMessage, PlannerOutput
from app.agent.planner import LLMPlanner
from app.agent.answerer import LLMAnswerer
from app.core.events import EventBus
from app.core.logging import log_event
from app.core.errors import ToolError
from app.core.session_store import SessionStore
from app.core.dedupe import DedupeStore
from app.plugins.registry import ToolRegistry
from app.infra.http import OllamaCloudClient
from app.infra.utils import new_request_id

from app.infra.db import get_db_session
from app.agent.confirmations_db import confirmations_store
from app.core.rate_limit import MemoryFixedWindowLimiter

from app.infra.mailer import SMTPMailer



class AgentOrchestrator:
    def __init__(
        self,
        settings: Settings,
        tool_registry: ToolRegistry,
        session_store: SessionStore,
        dedupe_store: DedupeStore,
        event_bus: EventBus,
    ):
        self.settings = settings
        self.tool_registry = tool_registry
        self.session_store = session_store
        self.dedupe_store = dedupe_store
        self.event_bus = event_bus

        # ✅ Rate limit por sesión (in-memory)
        self.session_limiter = MemoryFixedWindowLimiter(
            max_requests=settings.RATE_LIMIT_SESSION_MAX,
            window_sec=settings.RATE_LIMIT_SESSION_WINDOW_SEC,
        )

        self.ollama = OllamaCloudClient(
            base_url=settings.OLLAMA_API_BASE,
            api_key=settings.OLLAMA_API_KEY,
            model=settings.OLLAMA_MODEL,
            timeout_sec=settings.OLLAMA_TIMEOUT_SEC,
            retries=settings.OLLAMA_RETRIES,
        )
        self.planner = LLMPlanner(self.ollama)
        self.answerer = LLMAnswerer(self.ollama)
        # ✅ Mailer (singleton)
        self.mailer = SMTPMailer(self.settings)

    async def handle_message(self, msg: UserMessage, request_headers: Dict[str, str]) -> AgentResponse:
        request_id = new_request_id()
        session_id = msg.session_id or request_id
        if self.settings.RATE_LIMIT_ENABLED:
            res = self.session_limiter.check(f"sess:{session_id}")
            if not res.allowed:
                return AgentResponse(
                    intent="rate_limited",
                    reply=f"⚠️ Estás enviando demasiados mensajes. Probá de nuevo en {res.retry_after_sec}s.",
                    missing=[],
                    data={"retry_after_sec": res.retry_after_sec, "scope": "session"},
                )

        try:
            # ✅ Dedupe (persistente/atómico via store)
            if msg.message_id:
                provider = msg.channel or "unknown"
                payload_hash = (request_headers or {}).get("x-payload-hash")

                is_first = await self.dedupe_store.mark(
                    provider=provider,
                    message_id=msg.message_id,
                    ttl_sec=self.settings.DEDUPE_TTL_SEC,
                    payload_hash=payload_hash,
                )
                if not is_first:
                    return AgentResponse(intent="unknown", reply="Mensaje duplicado (dedupe).", missing=[], data={})

            # Load session
            session = await self.session_store.get(session_id) or {"history": [], "facts": {}}
            session_summary = self._summarize_session(session)

            # Audit IN
            self.event_bus.append({
                "type": "IN",
                "request_id": request_id,
                "session_id": session_id,
                "channel": msg.channel,
                "text": msg.message,
            })
            log_event("in", request_id=request_id, session_id=session_id, channel=msg.channel)

            # 2-step confirmation shortcut: "confirm <token>" / "confirmar <token>"
            maybe_token = self._extract_confirm_token(msg.message)
            if maybe_token:
                pending = self._consume_confirmation(token=maybe_token, session_id=session_id)
                if not pending:
                    reply = "❌ Confirmación inválida o expirada. Volvé a solicitar la acción."
                    return self._finalize(msg, session_id, request_id, intent="write_action", reply=reply, missing=[], data={})

                tool_name = pending["tool_name"]
                tool_args = pending["tool_args"]

                result = await self._run_tool(tool_name, tool_args, msg, session_id, request_id, confirmed=True)
                reply = self._format_write_result(tool_name, result)

                return self._finalize(
                    msg, session_id, request_id,
                    intent="write_action",
                    reply=reply,
                    missing=[],
                    data={"tool_results": {tool_name: result}},
                    debug={"confirmed": True, "tool": tool_name} if self._debug_enabled() else None,
                )

                        # Tools catalog
            tools_catalog = self.tool_registry.describe_tools()

            # Planner
            plan_dict = await self.planner.plan(
                message=msg.message,
                session_summary=session_summary,
                tools_catalog=tools_catalog,
                request_id=request_id,
            )
            plan = PlannerOutput.model_validate(plan_dict)

            # ✅ Audit PLAN (log siempre, incluso si luego cortamos por guardrail)
            self.event_bus.append({
                "type": "PLAN",
                "request_id": request_id,
                "session_id": session_id,
                "channel": msg.channel,
                "intent": plan.intent,
                "plan": plan_dict,
            })
            log_event("plan", request_id=request_id, session_id=session_id, intent=plan.intent, confidence=plan.confidence)

            # -----------------------------
            # ✅ Guardrails robustos
            # -----------------------------
            msg_low = (msg.message or "").lower()

            wants_register_customer = any(
                k in msg_low for k in [
                    "registrar cliente",
                    "alta cliente",
                    "crear cliente",
                    "nuevo cliente",
                    "registrar usuario",
                    "alta usuario",
                    "crear usuario",
                ]
            )

            # 1) Si el usuario pide registrar cliente/usuario -> debe haber tool_calls
            if wants_register_customer and not plan.tool_calls:
                return self._finalize(
                    msg, session_id, request_id,
                    intent="error",
                    reply=(
                        "⚠️ Para registrar un cliente/usuario necesito ejecutar una herramienta y no se generó ninguna.\n"
                        "Probá con:\n"
                        "registrar cliente | display_name=Nombre Apellido | email=mail@dominio.com | phone=+54..."
                    ),
                    missing=[],
                    data={"slots": plan.slots.model_dump(), "plan": plan.model_dump()},
                    debug={"plan": plan.model_dump()} if self._debug_enabled() else None,
                )

            # 2) Si el usuario pidió registrar y hay tool_calls, asegurá que use register_customer si existe
            if wants_register_customer and plan.tool_calls:
                first = plan.tool_calls[0].name
                if first != "register_customer" and self.tool_registry.get("register_customer"):
                    return self._finalize(
                        msg, session_id, request_id,
                        intent="error",
                        reply=(
                            "⚠️ Para registrar clientes debe usarse la herramienta register_customer.\n"
                            "Reintentá con:\n"
                            "registrar cliente | display_name=Nombre Apellido | email=mail@dominio.com | phone=+54..."
                        ),
                        missing=[],
                        data={"slots": plan.slots.model_dump(), "plan": plan.model_dump()},
                        debug={"plan": plan.model_dump()} if self._debug_enabled() else None,
                    )

            # 3) Regla general: write_action siempre requiere tool_calls (sin importar texto)
            if plan.intent == "write_action" and not plan.tool_calls:
                return self._finalize(
                    msg, session_id, request_id,
                    intent="error",
                    reply=(
                        "⚠️ Para ejecutar una acción de escritura necesito llamar una herramienta, "
                        "pero no se generó ninguna."
                    ),
                    missing=[],
                    data={"slots": plan.slots.model_dump(), "plan": plan.model_dump()},
                    debug={"plan": plan.model_dump()} if self._debug_enabled() else None,
                )

            # -----------------------------
            # Missing -> ask for missing
            # -----------------------------
            if plan.missing:
                reply = self._ask_for_missing(plan.missing)
                return self._finalize(
                    msg, session_id, request_id,
                    intent=plan.intent,
                    reply=reply,
                    missing=list(plan.missing),
                    data={"slots": plan.slots.model_dump()},
                    debug={"plan": plan_dict} if self._debug_enabled() else None,
                )

            # If final (no tools needed)
            # ✅ Permitimos final SOLO si NO es una acción de escritura y no hay tools
            if plan.final and not plan.tool_calls and plan.intent != "write_action":
                return self._finalize(
                    msg, session_id, request_id,
                    intent=plan.intent,
                    reply=plan.final,
                    missing=[],
                    data={"slots": plan.slots.model_dump()},
                    debug={"plan": plan_dict} if self._debug_enabled() else None,
                )

            # If final (no tools needed)
            if plan.final and not plan.tool_calls:
                return self._finalize(
                    msg, session_id, request_id,
                    intent=plan.intent,
                    reply=plan.final,
                    missing=[],
                    data={"slots": plan.slots.model_dump()},
                    debug={"plan": plan_dict} if self._debug_enabled() else None,
                )

            # Execute tools sequentially (allowlist enforced by registry)
            tool_results: Dict[str, Any] = {}
            for tc in plan.tool_calls:
                tool = self.tool_registry.get(tc.name)
                if not tool:
                    raise ToolError(f"Tool not found: {tc.name}")

                # Write -> requires confirmation (persistida en MySQL)
                if "write" in tool.scopes:
                    token = self._create_confirmation(session_id=session_id, tool_name=tc.name, tool_args=tc.args)

                    reply = (
                        f"⚠️ Esta acción requiere confirmación.\n"
                        f"- Acción: {tc.name}\n"
                        f"- Datos: {json.dumps(tc.args, ensure_ascii=False)}\n\n"
                        f"Si querés continuar, respondé: confirm {token}"
                    )
                    return self._finalize(
                        msg, session_id, request_id,
                        intent=plan.intent,
                        reply=reply,
                        missing=[],
                        data={"pending_confirmation": {"token": token, "tool": tc.name}},
                        debug={"plan": plan_dict} if self._debug_enabled() else None,
                    )

                result = await self._run_tool(tc.name, tc.args, msg, session_id, request_id, confirmed=False)
                tool_results[tc.name] = result

            # Answerer (optional)
            if self.settings.ENABLE_ANSWERER:
                reply = await self.answerer.answer(
                    message=msg.message,
                    intent=plan.intent,
                    slots=plan.slots.model_dump(),
                    tool_results=tool_results,
                    session_summary=session_summary,
                    request_id=request_id,
                )
            else:
                reply = self._fallback_reply(plan.intent, tool_results)

            return self._finalize(
                msg, session_id, request_id,
                intent=plan.intent,
                reply=reply,
                missing=[],
                data={"slots": plan.slots.model_dump(), "tool_results": tool_results},
                debug={"plan": plan_dict, "tool_results": tool_results} if self._debug_enabled() else None,
            )

        except Exception as e:
            # ✅ Audit ERROR (append-only)
            self.event_bus.append({
                "type": "ERROR",
                "request_id": request_id,
                "session_id": session_id,
                "channel": msg.channel,
                "error": str(e),
            })
            log_event("error", request_id=request_id, session_id=session_id, channel=msg.channel, error=str(e))

            # Respuesta segura al usuario
            return AgentResponse(
                intent="error",
                reply="⚠️ Ocurrió un error procesando tu mensaje. Probá de nuevo o reformulalo.",
                missing=[],
                data={},
                debug={"error": str(e)} if self._debug_enabled() else None,
            )

    def _create_confirmation(self, session_id: str, tool_name: str, tool_args: Dict[str, Any]) -> str:
        db = get_db_session()
        try:
            return confirmations_store.create(
                db,
                session_id=session_id,
                tool_name=tool_name,
                tool_args=tool_args,
                ttl_sec=self.settings.CONFIRMATION_TTL_SEC,  # ✅
            )
        finally:
            db.close()

    def _consume_confirmation(self, token: str, session_id: str) -> Optional[Dict[str, Any]]:
        db = get_db_session()
        try:
            return confirmations_store.consume(db, token=token, session_id=session_id)
        finally:
            db.close()

    async def _run_tool(
        self,
        name: str,
        args: Dict[str, Any],
        msg: UserMessage,
        session_id: str,
        request_id: str,
        confirmed: bool,
    ) -> Dict[str, Any]:
        tool = self.tool_registry.get(name)
        if not tool:
            raise ToolError(f"Tool not found: {name}")

        parsed = tool.input_model.model_validate(args)

        ctx = {
            "request_id": request_id,
            "session_id": session_id,
            "channel": msg.channel,
            "user_id": msg.user_id,
            "confirmed": confirmed,

            # ✅ NUEVO
            "mailer": self.mailer,
            "settings": self.settings,  # opcional
        }


        try:
            out = await tool.run(parsed, ctx)

            # ✅ TOOL (resultado) — 1 solo evento por tool
            self.event_bus.append({
                "type": "TOOL",
                "request_id": request_id,
                "session_id": session_id,
                "channel": msg.channel,
                "tool_name": name,
                "confirmed": confirmed,
                "args": args,
                "result": out,
            })
            log_event("tool", request_id=request_id, session_id=session_id, tool=name)

            return out

        except Exception as e:
            self.event_bus.append({
                "type": "ERROR",
                "request_id": request_id,
                "session_id": session_id,
                "channel": msg.channel,
                "tool_name": name,
                "confirmed": confirmed,
                "error": str(e),
            })
            log_event("error_tool", request_id=request_id, session_id=session_id, tool=name, error=str(e))
            raise


    def _finalize(
        self,
        msg: UserMessage,
        session_id: str,
        request_id: str,
        intent: str,
        reply: str,
        missing: list[str],
        data: Dict[str, Any],
        debug: Optional[Dict[str, Any]] = None,
    ) -> AgentResponse:
        session = self.session_store.get_sync(session_id) or {"history": [], "facts": {}}
        session["history"].append({"in": msg.message, "out": reply, "intent": intent})
        self.session_store.set_sync(session_id, session)

        self.event_bus.append({
            "type": "OUT",
            "request_id": request_id,
            "session_id": session_id,
            "channel": msg.channel,
            "intent": intent,
        })
        log_event("out", request_id=request_id, session_id=session_id, intent=intent)

        return AgentResponse(
            intent=intent,
            reply=reply,
            missing=missing,
            data=data,
            debug=debug if self._debug_enabled() else None,
        )

    def _ask_for_missing(self, missing: list[str]) -> str:
        questions = []
        if "cliente_ref" in missing:
            questions.append("• ¿A qué cliente te referís? (nombre o referencia)")
        if "periodo" in missing:
            questions.append("• ¿Qué período? (YYYY-MM, por ejemplo 2025-12)")
        return "Me falta un dato para ayudarte:\n" + "\n".join(questions)

    def _fallback_reply(self, intent: str, tool_results: Dict[str, Any]) -> str:
        return f"Intent: {intent}\nResultados: {json.dumps(tool_results, ensure_ascii=False)}"

    def _summarize_session(self, session: Dict[str, Any]) -> str:
        history = session.get("history", [])
        if not history:
            return "Sin historial."
        last = history[-3:]
        lines = []
        for h in last:
            lines.append(f"- IN: {h.get('in','')}")
            lines.append(f"  OUT: {h.get('out','')}")
        return "\n".join(lines)

    def _extract_confirm_token(self, text: str) -> Optional[str]:
        raw = text.strip()
        low = raw.lower()
        if low.startswith("confirm "):
            return raw.split(" ", 1)[1].strip()
        if low.startswith("confirmar "):
            return raw.split(" ", 1)[1].strip()
        return None

    def _format_write_result(self, tool_name: str, result: Dict[str, Any]) -> str:
        ok = result.get("ok", True)
        if not ok:
            err = result.get("error") or result.get("detail") or result
            return f"❌ No pude completar la acción ({tool_name}).\n• Detalle: {err}"

        # ✅ Turnos: reservar
        if tool_name == "create_appointment":
            appt_id = result.get("appointment_id")
            return (
                "✅ Turno reservado.\n"
                f"• ID: {appt_id}\n"
                f"• Estado: reservado"
            )

        # ✅ Turnos: cancelar
        if tool_name == "cancel_appointment":
            appt_id = result.get("appointment_id")
            service = result.get("service", "")
            start = result.get("start", "")
            end = result.get("end", "")
            return (
                "✅ Turno cancelado.\n"
                f"• ID: {appt_id}\n"
                f"• Servicio: {service}\n"
                f"• Fecha y hora: {start} a {end}"
            )

        # ✅ Turnos: reprogramar
        if tool_name == "reschedule_appointment":
            appt_id = result.get("appointment_id")
            service = result.get("service", "")
            new_start = result.get("new_start", "")
            new_end = result.get("new_end", "")
            return (
                "✅ Turno reprogramado.\n"
                f"• ID: {appt_id}\n"
                f"• Servicio: {service}\n"
                f"• Nuevo horario: {new_start} a {new_end}"
            )

        return f"✅ Acción ejecutada: {tool_name}"

    def _debug_enabled(self) -> bool:
        return self.settings.ENV == "dev" and self.settings.EXPOSE_DEBUG