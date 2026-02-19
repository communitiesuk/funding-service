const serializeFormData = (form, dataType, questionId, formId) => {
    const formData = new FormData(form);
    const data = {
        csrf_token: formData.get("csrf_token"),
        data_type: dataType,
        text: formData.get("text"),
        hint: formData.get("hint"),
        name: formData.get("name"),
        form_id: formData.get("form_id") || formId,
    };

    if (questionId) {
        data.question_id = questionId;
    }

    // Type-specific fields
    if (formData.has("rows")) data.rows = formData.get("rows");
    if (formData.has("word_limit"))
        data.word_limit = formData.get("word_limit");
    if (formData.has("prefix")) data.prefix = formData.get("prefix");
    if (formData.has("suffix")) data.suffix = formData.get("suffix");
    if (formData.has("width")) data.width = formData.get("width");
    if (formData.has("number_type"))
        data.number_type = formData.get("number_type");
    if (formData.has("max_decimal_places"))
        data.max_decimal_places = formData.get("max_decimal_places");
    if (formData.has("data_source_items"))
        data.data_source_items = formData.get("data_source_items");
    if (formData.has("separate_option_if_no_items_match"))
        data.separate_option_if_no_items_match = true;
    if (formData.has("none_of_the_above_item_text"))
        data.none_of_the_above_item_text = formData.get(
            "none_of_the_above_item_text",
        );
    if (formData.has("approximate_date")) data.approximate_date = true;

    return data;
};

const readAnswerFromPreview = (target, dataType) => {
    switch (dataType) {
        case "YES_NO":
        case "RADIOS": {
            const checked = target.querySelector("input[type=radio]:checked");
            return checked ? checked.value : "";
        }
        case "CHECKBOXES": {
            const checkedBoxes = target.querySelectorAll(
                "input[type=checkbox]:checked",
            );
            return Array.from(checkedBoxes).map((cb) => cb.value);
        }
        case "DATE": {
            const day = target.querySelector("input[id$='-day']")?.value || "";
            const month =
                target.querySelector("input[id$='-month']")?.value || "";
            const year =
                target.querySelector("input[id$='-year']")?.value || "";
            return [day, month, year];
        }
        case "TEXT_MULTI_LINE": {
            const textarea = target.querySelector("textarea");
            return textarea ? textarea.value : "";
        }
        default: {
            const input = target.querySelector(
                "input[type=text], input[type=email], input[type=url], input[type=number]",
            );
            return input ? input.value : "";
        }
    }
};

const fetchPreview = async (endpoint, data, target) => {
    target.innerHTML = `<p class="govuk-body">Preview loading...</p>`;

    try {
        const response = await window.fetch(endpoint, {
            method: "POST",
            mode: "same-origin",
            cache: "no-cache",
            credentials: "same-origin",
            headers: {
                "Content-Type": "application/json",
            },
            redirect: "follow",
            referrerPolicy: "same-origin",
            body: JSON.stringify(data),
        });

        const json = await response.json();
        if (json.question_html) {
            target.innerHTML = json.question_html;
        } else if (json.errors && json.errors.length > 0) {
            target.innerHTML = `<p class="govuk-body govuk-error-colour">${json.errors[0]}</p>`;
        } else {
            target.innerHTML = `<p class="govuk-body">No preview available</p>`;
        }
    } catch {
        target.innerHTML = `<p class="govuk-body">There was an error loading the preview</p>`;
        const retryButton = document.createElement("button");
        retryButton.classList.add("govuk-button", "govuk-button--secondary");
        retryButton.innerHTML = "Retry preview";
        retryButton.addEventListener("click", (event) => {
            event.preventDefault();
            fetchPreview(endpoint, data, target);
        });
        target.appendChild(retryButton);
    }
};

/**
 * Renders a live preview of a question when the user switches to the Preview tab.
 * @param {HTMLElement} moduleElement - The element with `data-module="ajax-question-preview"`.
 */
const ajaxQuestionPreview = (moduleElement) => {
    const endpoint = moduleElement.getAttribute(
        "data-question-preview-endpoint",
    );
    const dataType = moduleElement.getAttribute("data-question-data-type");
    const questionId = moduleElement.getAttribute("data-question-id");
    const formId = moduleElement.getAttribute("data-question-form-id");
    const target = moduleElement.querySelector(
        "[data-question-preview-target]",
    );
    const form = moduleElement.closest("form");

    if (!endpoint || !target || !form) return;

    // Listen for clicks on the Preview tab link
    const previewTabLink = moduleElement.querySelector(
        'a.govuk-tabs__tab[href="#preview-question"]',
    );
    if (previewTabLink) {
        previewTabLink.addEventListener("click", () => {
            const data = serializeFormData(form, dataType, questionId, formId);
            fetchPreview(endpoint, data, target);
        });
    }

    // Listen for clicks on the "Check answer" button within the preview target
    target.addEventListener("click", (event) => {
        const checkButton = event.target.closest("[data-check-answer]");
        if (!checkButton) return;

        event.preventDefault();
        const data = serializeFormData(form, dataType, questionId, formId);
        data.answer = readAnswerFromPreview(target, dataType);
        fetchPreview(endpoint, data, target);
    });
};

export default ajaxQuestionPreview;
