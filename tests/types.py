from typing import Any

from jinja2 import Template

type TTemplatesRendered = list[tuple[Template, dict[str, Any]]]
