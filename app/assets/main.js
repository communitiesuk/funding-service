import { initAll } from 'govuk-frontend';
import accessibleAutocomplete from 'accessible-autocomplete';
import markdownEditorToolbar from "./js/markdown-editor-toolbar";
import { pasteListener } from './js/paste-html-to-markdown';
import ajaxMarkdownPreview from './js/ajax-markdown-preview';
import textareaNoNewlines from "./js/textarea-no-newlines/index.js";

initAll();

for (let el of document.querySelectorAll("[data-accessible-autocomplete]")) {
    const fallbackOption = el.dataset.accessibleAutocompleteFallbackOption;

    // If we've set up a fallback option on the accessible autocomplete, it should *always* be shown regardless of the
    // query the user has entered. This is used for "Other"-style answers, to help make sure they're always
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

document
  .querySelectorAll('[data-module="markdown-editor-toolbar"]')
  .forEach(element => {
    markdownEditorToolbar(
      element,
      JSON.parse(element.getAttribute('data-i18n')),
      element.getAttribute('data-allow-headings') === 'true'
    );
    element.addEventListener('paste', pasteListener);
  });

document
  .querySelectorAll('[data-module="ajax-markdown-preview"]')
  .forEach(element => {
    ajaxMarkdownPreview(
      element.querySelector('[data-ajax-markdown-target]'),
      element.querySelector('[data-ajax-markdown-source]'),
      element.getAttribute('data-ajax-markdown-endpoint'),
      JSON.parse(element.getAttribute('data-i18n'))
    )
  })

document
    .querySelectorAll('[data-module="paste-html-bullets-as-markdown"]')
    .forEach(element => {
        element.addEventListener('paste', pasteListener);
    });

document
    .querySelectorAll('[data-module="textarea-no-newlines"]')
    .forEach(element => {
        textareaNoNewlines(element);
    });
