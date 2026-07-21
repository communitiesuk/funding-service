import { initAll } from "govuk-frontend";

// Uncomment this when we need MoJ Frontend components.
// Consider only importing+initialising the components that we use.
// import { initAll as mojInitAll } from "@ministryofjustice/frontend";
import accessibleAutocomplete from "accessible-autocomplete";
import { pasteListener } from "./components/paste-html-to-markdown";
import { initAjaxMarkdownPreviews } from "./components/ajax-markdown-preview";
import textareaNoNewlines from "./components/textarea-no-newlines/index.js";
import contextAwareEditor from "./components/context-aware-editor/index.js";
import { initSectionNavScroll } from "./components/submission-section-nav/index.js";
import selectWithSearch from "./components/select-with-search/index.js";

initAll();
// mojInitAll();
initSectionNavScroll();

for (let el of document.querySelectorAll("[data-accessible-autocomplete]")) {
    const fallbackOption = el.dataset.accessibleAutocompleteFallbackOption;

    // If we've set up a fallback option on the accessible autocomplete, it should *always* be shown regardless of the
    // query the user has entered. This is used for "Other"-style answers, to help make sure they're always
    // discoverable for users.
    const availableOptions = [].filter
        .call(el.options, (option) => option.value)
        .map((option) => option.textContent || option.innerText);
    const suggest = (query, populateResults) => {
        const filteredResults = availableOptions.filter(
            (option) =>
                option.toLowerCase().indexOf(query.toLowerCase()) !== -1 ||
                option === fallbackOption,
        );
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

initAjaxMarkdownPreviews();

document
    .querySelectorAll('[data-module="context-aware-editor"]')
    .forEach((element) => {
        contextAwareEditor(element);
        // Add paste listener for markdown conversion
        const textarea = element.querySelector(
            "[data-context-aware-editor-target]",
        );
        if (textarea) {
            textarea.addEventListener("paste", pasteListener);
        }
    });

document
    .querySelectorAll('[data-module="paste-html-bullets-as-markdown"]')
    .forEach((element) => {
        element.addEventListener("paste", pasteListener);
    });

document
    .querySelectorAll('[data-module="textarea-no-newlines"]')
    .forEach((element) => {
        textareaNoNewlines(element);
    });

document
    .querySelectorAll('[data-module="select-with-search"]')
    .forEach((element) => {
        selectWithSearch(element);
    });
