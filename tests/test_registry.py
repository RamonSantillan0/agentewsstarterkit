from app.plugins.registry import ToolRegistry
from app.settings import Settings


def test_registry_loads_mock_tools():
    s = Settings(_env_file=None)
    s.TOOLS_PROVIDER = "app.plugins.tools_mock:register"
    reg = ToolRegistry.from_settings(s)
    names = sorted([t.name for t in reg.list()])
    assert "get_help" in names
    assert "identify_customer" in names
    assert "get_report" in names
    assert "create_ticket" in names