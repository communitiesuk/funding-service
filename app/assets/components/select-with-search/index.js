import Choices from "choices.js";

/**
 * Select with search, adapted from govuk_publishing_components.
 * Progressive enhancement of a <select data-module="select-with-search"> using Choices.js.
 *
 * https://github.com/alphagov/govuk_publishing_components/blob/d1840a1fcf5f8367dd10ad7aede9ce78184da019/app/assets/javascripts/govuk_publishing_components/components/select-with-search.js
 *
 * Extended to support per-option hint text: any <option data-hint="..."> has its hint rendered
 * below the option label in the dropdown. Hints are also included in search behaviour.
 */
export default function selectWithSearch(selectEl) {
    if (!selectEl.matches("select")) {
        console.error("select-with-search must be applied to a select element");
        return;
    }

    const selectOneText = "Select one";
    const blankOptionText = "Select none";
    const placeholderOption = selectEl.querySelector(
        'option[value=""]:first-child',
    );
    if (placeholderOption && placeholderOption.textContent === "") {
        placeholderOption.textContent = selectEl.multiple
            ? "Select all that apply"
            : selectOneText;
    }

    const describedBy = selectEl.getAttribute("aria-describedby") || "";
    const labelId = `${selectEl.id}-label ${describedBy}`.trim();

    const hintsByValue = new Map();
    for (const option of selectEl.options) {
        if (option.dataset.hint) {
            hintsByValue.set(option.value, option.dataset.hint);
            option.dataset.customProperties = JSON.stringify({
                hint: option.dataset.hint,
            });
        }
    }

    const choices = new Choices(selectEl, {
        allowHTML: false,
        searchPlaceholderValue: "Search in list",
        shouldSort: false,
        itemSelectText: "",
        searchResultLimit: 100,
        removeItemButton: selectEl.multiple,
        labelId: labelId,
        searchFields: ["label", "customProperties.hint"],
        fuseOptions: {
            ignoreLocation: true,
            threshold: 0,
        },
        callbackOnInit() {
            if (this.dropdown.type === "select-multiple") {
                this.containerInner.element.prepend(this.input.element);
            } else {
                // Update text for blank option in the hidden select
                const selectElement = this.passedElement.element;
                if (selectElement.id.search("blank") > 0) {
                    selectElement.firstChild.innerText = blankOptionText;
                }
                // Update text for blank option in the choices dropdown
                // choices.js 'lastChild' in this context is the listbox of choices:
                const listbox = this.dropdown.element.lastChild;
                // choices.js 'firstChild' in this context is the first option.
                // This always displays "Select One" for selects with a blank option:
                var blankOption = listbox.firstChild;
                if (blankOption && blankOption.textContent === selectOneText) {
                    blankOption.innerText = blankOptionText;
                }
            }
            this.itemList.element.setAttribute("aria-labelledby", labelId);
        },
        callbackOnCreateTemplates() {
            const defaultTemplates = Choices.defaults.templates;
            return {
                choice(...args) {
                    const element = defaultTemplates.choice.call(this, ...args);
                    const hint = hintsByValue.get(String(args[1].value));
                    if (hint) {
                        const hintEl = document.createElement("span");
                        hintEl.className =
                            "app-select-with-search__option-hint";
                        hintEl.textContent = hint;
                        element.appendChild(hintEl);
                    }
                    return element;
                },
            };
        },
    });

    // Reset blank 'Select One' to 'Select None' on each change
    // This is because choices.js rebuilds the widget on each
    // change event and resets the text. We can't use the preferred
    // refresh method as this loses the current state of the dropdown.
    const selectElement = choices.passedElement.element;
    const listbox = choices.dropdown.element.lastChild;
    selectElement.addEventListener(
        "change",
        function (event) {
            var blankOption = listbox.firstChild;
            if (blankOption && blankOption.textContent === selectOneText) {
                blankOption.innerText = blankOptionText;
            }
        },
        false,
    );
}
