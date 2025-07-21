import { initAll } from 'govuk-frontend'
import accessibleAutocomplete from 'accessible-autocomplete'

initAll()

for (let el of document.querySelectorAll("[data-accessible-autocomplete]")) {
    const fallbackOption = el.dataset.accessibleAutocompleteFallbackOption;

    // If we've set up a fallback option on the accessible autocomplete, it should *always* be shown regardless of the
    // query the user has entered. This is used for "None of the above"-style answers, to help make sure they're always
    // discoverable for users.
    const availableOptions = [].filter.call(el.options, option => (option.value)).map(option => option.textContent || option.innerText);
    const suggest = (query, populateResults) => {
        const filteredResults = availableOptions.filter(option => option.toLowerCase().indexOf(query.toLowerCase()) !== -1 || option === fallbackOption);
        return populateResults(filteredResults);
    };

    accessibleAutocomplete.enhanceSelectElement({
        selectElement: el,
        showAllValues: true,
        confirmOnBlur: false,
        source: suggest,
        displayMenu: "overlay",
    });
}
