from __future__ import annotations
from typing import List
from app.plugins.base import Tool

from app.plugins.tools_mock import register as register_mock_tools
from app.plugins.customer_registration_tools import register as register_customer_email_tools

def provide_tools() -> List[Tool]:
    tools: List[Tool] = []
    tools.extend(register_mock_tools())
    tools.extend(register_customer_email_tools())
    return tools