from __future__ import annotations

import json
from typing import Any, Dict, Tuple

from pydantic import ValidationError

from app.agent.schema import PlannerOutput


def parse_json_strict(text: str) -> Dict[str, Any]:
    """
    Parse estricto: esperamos que text sea JSON (objeto) sin markdown.
    """
    text = text.strip()
    return json.loads(text)


def validate_planner_output(obj: Dict[str, Any]) -> Tuple[PlannerOutput, None | str]:
    """
    Valida contra Pydantic. Devuelve (model, error_message).
    """
    try:
        model = PlannerOutput.model_validate(obj)
        return model, None
    except ValidationError as e:
        return None, str(e)