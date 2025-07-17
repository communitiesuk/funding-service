from typing import Any

from govuk_frontend_wtf.wtforms_widgets import GovSelect
from wtforms import Field


class MHCLGAccessibleAutocomplete(GovSelect):
    is_accessible_autocomplete: bool = True

    def __call__(self, field: Field, **kwargs: Any) -> Any:
        # Set `data-accessible-autocomplete` on select field, which our JS will pick up and enhance automatically.
        params = kwargs.get("params", {})
        attributes = params.get("attributes", {})
        attributes.setdefault("data-accessible-autocomplete", "1")
        params["attributes"] = attributes
        return super().__call__(field, **kwargs)
