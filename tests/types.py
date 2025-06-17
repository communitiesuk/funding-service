from dataclasses import dataclass
from typing import Any, Dict

from jinja2 import Template


@dataclass
class TemplateRenderRecord:
    template: Template
    context: Dict[str, Any]


TTemplatesRendered = Dict[str, TemplateRenderRecord]
