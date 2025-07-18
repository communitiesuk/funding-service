from typing import Any

from govuk_frontend_wtf.gov_form_base import GovIterableBase
from govuk_frontend_wtf.wtforms_widgets import GovSelect
from wtforms import Field


class MHCLGAccessibleAutocomplete(GovSelect):
    is_accessible_autocomplete: bool = True

    template = "common/fields/accessible-autocomplete.html"

    def __call__(self, field: Field, **kwargs: Any) -> Any:
        # Set `data-accessible-autocomplete` on select field, which our JS will pick up and enhance automatically.
        params = kwargs.get("params", {})
        attributes = params.get("attributes", {})
        attributes.setdefault("data-accessible-autocomplete", "1")
        params["attributes"] = attributes
        return super().__call__(field, **kwargs)


class MHCLGDividableIterableBase(GovIterableBase):
    """
    This is to override the implementation of GovIterableBase in order to support adding an 'or' divider before the
    last radio item.
    """

    def __init__(self, *args: Any, insert_divider_before_last_item: bool = True, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.insert_divider_before_last_item = insert_divider_before_last_item

    def __call__(self, field, **kwargs):  # type: ignore
        kwargs.setdefault("id", field.id)

        if "required" not in kwargs and "required" in getattr(field, "flags", []):
            kwargs["required"] = True

        kwargs["items"] = []

        for subfield in field:
            item = {"text": subfield.label.text, "value": subfield._value()}

            if getattr(subfield, "checked", subfield.data):
                item["checked"] = True

            kwargs["items"].append(item)

        # This is the only bit of custom/additional logic
        if self.insert_divider_before_last_item:
            kwargs["items"].insert(-1, {"divider": "or"})

        # Skip over GovIterableBase's __call__ because we're re-implementing it here, otherwise we'll lose the
        # custom logic inserting the `or` divider item.
        return super(GovIterableBase, self).__call__(field, **kwargs)


class MHCLGRadioInput(MHCLGDividableIterableBase):
    # An exact copy of govuk-frontend-wtf's `GovRadioInput`, just with our own IterableBase override.
    """Render radio button inputs.

    Uses the field label as the fieldset legend.
    """

    template = "govuk_frontend_wtf/radios.html"
    input_type = "radio"

    def map_gov_params(self, field, **kwargs):  # type: ignore
        params = super().map_gov_params(field, **kwargs)
        params.setdefault(
            "fieldset",
            {
                "legend": {"text": field.label.text},
            },
        )
        return params
