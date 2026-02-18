from __future__ import annotations

import json
import asyncio
from typing import Any, Dict, Optional

import httpx

from app.core.errors import LLMError


class OllamaCloudClient:
    """
    Conector Ollama (API directo):
      POST {OLLAMA_API_BASE}/api/chat
      Authorization: Bearer {OLLAMA_API_KEY}

    Soporta:
      - chat_text(): salida libre (answerer)
      - chat_json(): salida esperada JSON (planner/repair)
      - format_schema: para structured outputs (muy recomendado para planner)
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout_sec: int = 30,
        retries: int = 2,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_sec = timeout_sec
        self.retries = retries

    async def chat_json(
        self,
        system: str,
        user: str,
        request_id: str,
        format_schema: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Devuelve el contenido del assistant como string.
        Esperamos JSON estricto (planner/repair).
        Si pasás format_schema, Ollama intentará ajustarse al schema.
        """
        return await self._chat(
            system=system,
            user=user,
            request_id=request_id,
            format_schema=format_schema,
        )

    async def chat_text(self, system: str, user: str, request_id: str) -> str:
        """
        Devuelve texto libre (answerer).
        """
        return await self._chat(system=system, user=user, request_id=request_id)

    async def _chat(
        self,
        system: str,
        user: str,
        request_id: str,
        format_schema: Optional[Dict[str, Any]] = None,
    ) -> str:
        # ✅ Ollama: /api/chat
        url = f"{self.base_url}/api/chat"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "X-Request-Id": request_id,
        }

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
        }

        # ✅ Structured outputs / JSON schema (opcional)
        # Ollama acepta `format` para forzar salida estructurada (cuando el modelo lo soporta).
        if format_schema is not None:
            payload["format"] = format_schema

        last_err: Optional[Exception] = None

        async with httpx.AsyncClient(timeout=self.timeout_sec) as client:
            for attempt in range(self.retries + 1):
                try:
                    resp = await client.post(url, headers=headers, json=payload)

                    # errores HTTP claros
                    if resp.status_code >= 400:
                        raise LLMError(f"Ollama error {resp.status_code}: {resp.text[:800]}")

                    data = resp.json()

                    # Ollama normal: {"message":{"content":"..."}, "done":true}
                    content = None
                    if isinstance(data, dict):
                        if isinstance(data.get("message"), dict):
                            content = data["message"].get("content")
                        # Compat OpenAI-like
                        elif isinstance(data.get("choices"), list) and data["choices"]:
                            content = data["choices"][0].get("message", {}).get("content")
                        elif isinstance(data.get("content"), str):
                            content = data.get("content")

                    if not isinstance(content, str) or not content.strip():
                        raise LLMError(f"Unexpected LLM response shape: {json.dumps(data)[:800]}")

                    return content.strip()

                except (httpx.TimeoutException, httpx.NetworkError) as e:
                    last_err = e
                    # backoff simple
                    if attempt < self.retries:
                        await asyncio.sleep(0.5 * (attempt + 1))
                        continue
                    break
                except Exception as e:
                    last_err = e
                    if attempt < self.retries:
                        await asyncio.sleep(0.2 * (attempt + 1))
                        continue
                    break

        raise LLMError(f"Failed calling Ollama after retries: {last_err}")