// This file contains JS that is only used by the platform admin/flask-admin pages. GOV.UK Frontend components are
// initialised by the xgovuk-flask-admin bundle, so this entrypoint must only wire up our own components.
import ajaxMarkdownPreview from "./components/ajax-markdown-preview";
import { createToolbarForTextArea } from "./components/context-aware-editor/toolbar.js";

document
    .querySelectorAll('[data-module="ajax-markdown-preview"]')
    .forEach((element) => {
        ajaxMarkdownPreview(
            element.querySelector("[data-ajax-markdown-target]"),
            element.querySelector("[data-ajax-markdown-source]"),
            element.getAttribute("data-ajax-markdown-endpoint"),
        );
    });

document.querySelectorAll("[data-markdown-toolbar]").forEach((textarea) => {
    const toolbarContainer = document.createElement("div");
    toolbarContainer.classList.add(
        "app-context-aware-editor__toolbar-container",
    );
    toolbarContainer.appendChild(createToolbarForTextArea(textarea, {}, false));
    textarea.parentNode.insertBefore(toolbarContainer, textarea);
});

// Mirror a plain-text input into an element in the markdown preview (used to show the release note's title as the
// preview's leading heading without round-tripping it through the markdown endpoint).
const previewTitleSource = document.querySelector(
    "[data-preview-title-source]",
);
const previewTitleTarget = document.querySelector(
    "[data-preview-title-target]",
);
if (previewTitleSource && previewTitleTarget) {
    previewTitleSource.addEventListener("input", () => {
        previewTitleTarget.textContent = previewTitleSource.value;
        previewTitleTarget.hidden = !previewTitleSource.value;
    });
}
