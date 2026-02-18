from __future__ import annotations

import json
from typing import Any, Dict

from app.agent.prompts import PLANNER_SYSTEM, PLANNER_USER_TEMPLATE, REPAIR_SYSTEM
from app.agent.validators import parse_json_strict, validate_planner_output
from app.core.errors import LLMError
from app.infra.http import OllamaCloudClient
from app.agent.schema import PlannerOutput


class LLMPlanner:
    def __init__(self, client: OllamaCloudClient):
        self.client = client

    async def plan(
        self,
        message: str,
        session_summary: str,
        tools_catalog: str,
        request_id: str,
    ) -> Dict[str, Any]:
        user_prompt = PLANNER_USER_TEMPLATE.format(
            message=message,
            session_summary=session_summary,
            tools_catalog=tools_catalog,
        )

        # ✅ Structured outputs: schema Pydantic -> JSON schema
        planner_schema = PlannerOutput.model_json_schema()

        raw_text = await self.client.chat_json(
            system=PLANNER_SYSTEM,
            user=user_prompt,
            request_id=request_id,
            format_schema=planner_schema,
        )

        # 1) parse JSON estricto
        try:
            obj = parse_json_strict(raw_text)
        except Exception:
            # repair 1 vez: pedir JSON válido (idealmente ajustado al schema)
            repaired = await self._repair(raw_text, request_id=request_id, schema=planner_schema)
            obj = parse_json_strict(repaired)

        # 2) validar contra modelo Pydantic (reglas y tipos)
        model, err = validate_planner_output(obj)
        if err:
            # repair 1 vez si no pasa schema
            repaired = await self._repair(
                json.dumps(obj, ensure_ascii=False),
                request_id=request_id,
                schema=planner_schema,
            )
            obj2 = parse_json_strict(repaired)
            model2, err2 = validate_planner_output(obj2)
            if err2:
                raise LLMError(f"Planner output invalid after repair: {err2}")
            return model2.model_dump()

        return model.model_dump()

    async def _repair(self, bad_output: str, request_id: str, schema: Dict[str, Any]) -> str:
        """
        1 solo intento de repair.
        Incluimos el schema para forzar forma exacta.
        """
        schema_compact = json.dumps(schema, ensure_ascii=False)
        prompt = (
            "Tu tarea: devolver SOLO un JSON válido, sin markdown, sin texto extra.\n"
            "Debe ajustarse EXACTAMENTE al siguiente JSON Schema:\n"
            f"{schema_compact}\n\n"
            "Salida inválida a reparar:\n"
            f"{bad_output}\n\n"
            "Devolvé SOLO el JSON válido."
        )
        # También podemos pasar format_schema al repair para reforzar aún más
        return await self.client.chat_json(
            system=REPAIR_SYSTEM,
            user=prompt,
            request_id=request_id,
            format_schema=schema,
        )