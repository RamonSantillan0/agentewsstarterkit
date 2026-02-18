from __future__ import annotations

import json
from typing import Any, Dict

from app.agent.prompts import ANSWERER_SYSTEM, ANSWERER_USER_TEMPLATE
from app.infra.http import OllamaCloudClient


class LLMAnswerer:
    def __init__(self, client: OllamaCloudClient):
        self.client = client

    async def answer(
        self,
        message: str,
        intent: str,
        slots: Dict[str, Any],
        tool_results: Dict[str, Any],
        session_summary: str,
        request_id: str,
    ) -> str:
        user_prompt = ANSWERER_USER_TEMPLATE.format(
            message=message,
            intent=intent,
            slots_json=json.dumps(slots, ensure_ascii=False),
            tool_results_json=json.dumps(tool_results, ensure_ascii=False),
            session_summary=session_summary,
        )
        # Answerer puede devolver texto normal (no JSON)
        return await self.client.chat_text(system=ANSWERER_SYSTEM, user=user_prompt, request_id=request_id)