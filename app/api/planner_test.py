from fastapi import APIRouter
from pydantic import BaseModel

from app.settings import settings
from app.infra.http import OllamaCloudClient
from app.agent.planner import LLMPlanner

router = APIRouter()

class PlannerTestIn(BaseModel):
    message: str

@router.post("/planner-test")
async def planner_test(body: PlannerTestIn):
    client = OllamaCloudClient(
        base_url=settings.OLLAMA_API_BASE,
        api_key=settings.OLLAMA_API_KEY,
        model=settings.OLLAMA_MODEL,
        timeout_sec=settings.OLLAMA_TIMEOUT_SEC,
        retries=settings.OLLAMA_RETRIES,
    )
    planner = LLMPlanner(client)

    plan = await planner.plan(
        message=body.message,
        session_summary="",
        tools_catalog="TOOLS DISPONIBLES: get_help, identify_customer, get_report, create_ticket",
        request_id="planner-test",
    )
    return {"ok": True, "plan": plan}