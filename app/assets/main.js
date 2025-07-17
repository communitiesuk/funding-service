import { initAll } from 'govuk-frontend'
import accessibleAutocomplete from 'accessible-autocomplete'

initAll()

for (let el of document.querySelectorAll("[data-accessible-autocomplete]")) {
    accessibleAutocomplete.enhanceSelectElement({
        selectElement: el,
        showAllValues: true,
        confirmOnBlur: false,
        displayMenu: "overlay",
    });
}
