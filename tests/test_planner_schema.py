from app.agent.schema import PlannerOutput


def test_planner_schema_valid_minimal():
    obj = {
        "intent": "faq",
        "slots": {"cliente_ref": None, "periodo": None, "otros": {}},
        "missing": [],
        "tool_calls": [],
        "final": "Hola, ¿en qué puedo ayudarte?",
        "confidence": 0.8,
    }
    model = PlannerOutput.model_validate(obj)
    assert model.intent == "faq"
    assert model.final is not None
    assert 0 <= model.confidence <= 1


def test_planner_schema_missing_no_tools():
    obj = {
        "intent": "read_data",
        "slots": {"cliente_ref": None, "periodo": None, "otros": {}},
        "missing": ["cliente_ref"],
        "tool_calls": [],
        "final": None,
        "confidence": 0.4,
    }
    model = PlannerOutput.model_validate(obj)
    assert "cliente_ref" in model.missing
    assert model.tool_calls == []