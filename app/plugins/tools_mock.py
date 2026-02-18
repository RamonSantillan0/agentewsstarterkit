from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, Field, AliasChoices

from app.plugins.base import Tool


class EmptyArgs(BaseModel):
    pass


class IdentifyArgs(BaseModel):
    customer_hint: str = Field(default="", description="Any identifier or hint")


class ReportArgs(BaseModel):
    # ✅ Canon: cliente_ref / periodo
    # ✅ Compat: acepta customer_id y client_id como alias de cliente_ref
    cliente_ref: str = Field(
        ...,
        description="ID o referencia del cliente",
        validation_alias=AliasChoices("cliente_ref", "customer_id", "client_id"),
    )
    # ✅ Compat: acepta period como alias de periodo
    periodo: str = Field(
        ...,
        description="Periodo YYYY-MM",
        validation_alias=AliasChoices("periodo", "period"),
    )

    # Opcional: topic demo
    topic: str = Field(default="summary", description="demo topic")


class CreateTicketArgs(BaseModel):
    title: str = Field(..., description="Título corto del ticket")
    detail: str = Field(..., description="Detalle del problema")


class GetHelpTool:
    name = "get_help"
    description = "Devuelve ayuda general sobre qué puede hacer el agente (modo demo)."
    input_model = EmptyArgs
    scopes = ["read"]

    async def run(self, args: BaseModel, ctx: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "ok": True,
            "help": [
                "Podés pedir: ayuda, identificar cliente, obtener un reporte demo, o crear un ticket (requiere confirmación).",
                "Ejemplos: 'ayuda', 'identificar Juan', 'reporte 2025-12 cliente 123', 'crear ticket por problema X'",
            ],
        }


class IdentifyCustomerTool:
    name = "identify_customer"
    description = "Identifica un cliente a partir de un texto (mock)."
    input_model = IdentifyArgs
    scopes = ["read"]

    async def run(self, args: IdentifyArgs, ctx: Dict[str, Any]) -> Dict[str, Any]:
        hint = (args.customer_hint or "").strip()
        if not hint:
            return {"ok": True, "matched": False, "candidates": []}

        return {
            "ok": True,
            "matched": True,
            "customer": {"id": "CUST_001", "display": hint.title()},
            "confidence": 0.72,
        }


class GetReportTool:
    name = "get_report"
    description = "Devuelve un reporte dummy (mock). Útil para demostrar que números vienen SOLO de tools."
    input_model = ReportArgs
    scopes = ["read"]

    async def run(self, args: ReportArgs, ctx: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "ok": True,
            "topic": args.topic,
            "cliente_ref": args.cliente_ref,
            "periodo": args.periodo,
            "values": {
                "metric_a": 123,
                "metric_b": 456,
                "note": "Valores dummy (mock).",
            },
        }


class CreateTicketTool:
    name = "create_ticket"
    description = "Crea un ticket (mock). Acción de escritura: requiere confirmación 2 pasos."
    input_model = CreateTicketArgs
    scopes = ["write"]

    async def run(self, args: CreateTicketArgs, ctx: Dict[str, Any]) -> Dict[str, Any]:
        # En el starter, si llega acá es porque ya fue confirmado
        return {
            "ok": True,
            "ticket_id": "TCK-1001",
            "title": args.title,
            "status": "created",
        }


def register() -> List[Tool]:
    return [
        GetHelpTool(),
        IdentifyCustomerTool(),
        GetReportTool(),
        CreateTicketTool(),
    ]