import decimal
from typing import Any, List

from govuk_frontend_wtf.gov_form_base import GovFormBase, GovIterableBase
from govuk_frontend_wtf.wtforms_widgets import GovSelect
from wtforms import DecimalField, Field
from wtforms.fields.numeric import IntegerField as WTFormsIntegerField


class IntegerWithCommasField(WTFormsIntegerField):
    """
    IntegerField that accepts comma-separated input (e.g., "1,000,000").
    Commas are stripped before integer conversion.
    """

    def process_formdata(self, valuelist: list[Any]) -> None:
        """Override to strip commas from input before converting to integer."""
        if not valuelist:
            return

        # Strip commas from the input string before conversion
        cleaned_value = valuelist[0].replace(",", "") if isinstance(valuelist[0], str) else valuelist[0]

        try:
            self.data = int(cleaned_value)
        except ValueError as exc:
            self.data = None
            raise ValueError(self.gettext("The answer must be a whole number, like 100")) from exc


class DecimalWithCommasField(DecimalField):
    """
    DecimalField that accepts comma-separated input (e.g., "1,000,000.11").
    Commas are stripped before decimal conversion.
    """

    def process_formdata(self, valuelist: List[str]) -> None:
        if not valuelist:
            return
        # Strip commas from the input string before conversion
        cleaned_value = valuelist[0].replace(",", "") if isinstance(valuelist[0], str) else valuelist[0]

        try:
            self.data = decimal.Decimal(cleaned_value)
        except (decimal.InvalidOperation, ValueError) as exc:
            self.data = None
            raise ValueError(self.gettext("The answer must be a number, like 100.5")) from exc


class MHCLGAccessibleAutocomplete(GovSelect):
    is_accessible_autocomplete: bool = True

    template = "common/fields/accessible-autocomplete.html"

    def __init__(self, *args: Any, fallback_option: str | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fallback_option = fallback_option

    def __call__(self, field: Field, **kwargs: Any) -> Any:
        # Set `data-accessible-autocomplete` on select field, which our JS will pick up and enhance automatically.
        params = kwargs.setdefault("params", {})
        attributes = params.get("attributes", {})
        attributes.setdefault("data-accessible-autocomplete", "1")

        if self.fallback_option:
            attributes["data-accessible-autocomplete-fallback-option"] = self.fallback_option

        params["attributes"] = attributes
        return super().__call__(field, **kwargs)


class MHCLGDividableIterableBase(GovIterableBase):
    """
    This is to override the implementation of GovIterableBase in order to support adding an 'or' divider before the
    last radio item.
    """

    def __init__(self, *args: Any, insert_divider_before_last_item: bool = False, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.insert_divider_before_last_item = insert_divider_before_last_item

    def __call__(self, field, **kwargs):  # type: ignore[no-untyped-def]
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

    def map_gov_params(self, field, **kwargs):  # type: ignore[no-untyped-def]
        params = super().map_gov_params(field, **kwargs)
        params.setdefault(
            "fieldset",
            {
                "legend": {"text": field.label.text},
            },
        )
        return params


class MHCLGCheckboxesInput(MHCLGDividableIterableBase):
    # An exact copy of govuk-frontend-wtf's `GovCheckboxesInput`, just with our own IterableBase override and an
    # addition for enabling the govuk 'exclusive' behaviour on the final checkbox if it's an "other".
    """Multiple checkboxes, from a SelectMultipleField

    This widget type doesn't exist in WTForms - the recommendation
    there is to use a combination of the list and checkbox widgets.
    However in the GOV.UK macros this type of field is not simply
    a list of smaller widgets - multiple checkboxes are a single
    construct of their own.
    """

    template = "govuk_frontend_wtf/checkboxes.html"
    input_type = "checkbox"

    def map_gov_params(self, field, **kwargs):  # type: ignore[no-untyped-def]
        params = super().map_gov_params(field, **kwargs)

        # This is the only bit of additional logic to uncheck all other checkboxes when the user the final option
        if self.insert_divider_before_last_item:
            params["items"][-1]["behaviour"] = "exclusive"

        params.setdefault(
            "fieldset",
            {
                "legend": {
                    "text": field.label.text,
                },
            },
        )
        return params


class MHCLGApproximateDateInput(GovFormBase):
    """Renders two input fields representing Month and Year.

    To be used as a widget for WTForms' DateField or DateTimeField.
    The input field labels are hardcoded to "Month" and "Year".
    The provided label is set as a legend above the input fields.
    The field names MUST all be the same for this widget to work.
    """

    template = "govuk_frontend_wtf/date.html"

    def __call__(self, field, **kwargs):  # type: ignore[no-untyped-def]
        kwargs.setdefault("id", field.id)
        if "value" not in kwargs:
            kwargs["value"] = field._value()
        if "required" not in kwargs and "required" in getattr(field, "flags", []):
            kwargs["required"] = True
        return super().__call__(field, **kwargs)

    def map_gov_params(self, field, **kwargs):  # type: ignore[no-untyped-def]
        params = super().map_gov_params(field, **kwargs)
        month, year = [None] * 2
        if field.raw_data is not None:
            month, year = field.raw_data
        elif field.data:
            month, year = field.data.strftime("%m %Y").split(" ")

        params.setdefault(
            "fieldset",
            {
                "legend": {"text": field.label.text},
            },
        )
        params.setdefault(
            "items",
            [
                {
                    "label": "Month",
                    "id": f"{field.name}-month",
                    "name": field.name,
                    "classes": " ".join(
                        [
                            "govuk-input--width-2",
                            "govuk-input--error" if field.errors else "",
                        ]
                    ).strip(),
                    "value": month,
                },
                {
                    "label": "Year",
                    "id": f"{field.name}-year",
                    "name": field.name,
                    "classes": " ".join(
                        [
                            "govuk-input--width-4",
                            "govuk-input--error" if field.errors else "",
                        ]
                    ).strip(),
                    "value": year,
                },
            ],
        )
        return params
