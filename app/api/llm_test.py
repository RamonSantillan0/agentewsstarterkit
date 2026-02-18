from fastapi import APIRouter
from app.infra.http import OllamaCloudClient
from app.settings import settings

router = APIRouter()

@router.get("/llm-test")
async def llm_test():
    client = OllamaCloudClient(
        base_url=settings.OLLAMA_API_BASE,
        api_key=settings.OLLAMA_API_KEY,
        model=settings.OLLAMA_MODEL,
        timeout_sec=settings.OLLAMA_TIMEOUT_SEC,
        retries=settings.OLLAMA_RETRIES,
    )
    out = await client.chat_text(
        system="Respondé exactamente: OK",
        user="Hola",
        request_id="llm-test",
    )
    return {"ok": True, "output": out}