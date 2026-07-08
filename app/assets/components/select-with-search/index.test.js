/**
 * @vitest-environment jsdom
 */

import selectWithSearch from "./index.js";

beforeAll(() => {
    window.matchMedia = vi.fn().mockReturnValue({
        matches: false,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
    });
});

function buildSelect({ options, multiple = false, id = "test-select" } = {}) {
    const optionHtml = options
        .map((o) => {
            const attrs = [`value="${o.value}"`];
            if (o.selected) attrs.push("selected");
            if (o.hint) attrs.push(`data-hint="${o.hint}"`);
            return `<option ${attrs.join(" ")}>${o.text}</option>`;
        })
        .join("");

    document.body.innerHTML =
        `<label id="${id}-label" for="${id}">Label</label>` +
        `<select id="${id}" name="${id}" ${multiple ? "multiple" : ""} data-module="select-with-search">` +
        optionHtml +
        "</select>";

    return document.querySelector("select");
}

function getDropdownChoices() {
    const list = document.querySelector(".choices__list--dropdown");
    if (!list) return [];
    return Array.from(list.querySelectorAll(".choices__item[role='option']"));
}

function typeInSearch(text) {
    const input = document.querySelector("input[type='search']");
    input.focus();
    input.value = text;
    input.dispatchEvent(new Event("input", { bubbles: true }));
}

describe("selectWithSearch", () => {
    afterEach(() => {
        document.body.innerHTML = "";
    });

    test("initialises Choices.js on a select element", () => {
        const select = buildSelect({
            options: [
                { value: "", text: "" },
                { value: "1", text: "Alpha" },
            ],
        });
        selectWithSearch(select);

        expect(document.querySelector(".choices")).not.toBeNull();
    });

    test("sets placeholder text for single select", () => {
        const select = buildSelect({
            options: [
                { value: "", text: "" },
                { value: "1", text: "Alpha" },
            ],
        });
        selectWithSearch(select);

        const placeholder = document.querySelector(
            ".choices__item--choice[data-value='']",
        );
        expect(placeholder.textContent).toContain("Select one");
    });

    test("sets placeholder text for multiple select", () => {
        const select = buildSelect({
            multiple: true,
            options: [
                { value: "", text: "" },
                { value: "1", text: "Alpha" },
            ],
        });
        selectWithSearch(select);

        const input = document.querySelector("input[type='search']");
        expect(input.placeholder).toBe("Select all that apply");
    });

    test("renders hint text below option label", () => {
        const select = buildSelect({
            options: [
                { value: "1", text: "Alpha", hint: "First letter" },
                { value: "2", text: "Beta" },
            ],
        });
        selectWithSearch(select);

        const hintEl = document.querySelector(
            ".app-select-with-search__option-hint",
        );
        expect(hintEl).not.toBeNull();
        expect(hintEl.textContent).toBe("First letter");
    });

    test("does not render hint element for options without hints", () => {
        const select = buildSelect({
            options: [
                { value: "1", text: "Alpha" },
                { value: "2", text: "Beta" },
            ],
        });
        selectWithSearch(select);

        const hintEls = document.querySelectorAll(
            ".app-select-with-search__option-hint",
        );
        expect(hintEls).toHaveLength(0);
    });

    test("search matches on option label", () => {
        const select = buildSelect({
            options: [
                { value: "1", text: "Alpha", hint: "First letter" },
                { value: "2", text: "Beta", hint: "Second letter" },
            ],
        });
        selectWithSearch(select);

        typeInSearch("Alpha");
        const choices = getDropdownChoices();
        expect(choices).toHaveLength(1);
        expect(choices[0].textContent).toContain("Alpha");
    });

    test("search matches on hint text", () => {
        const select = buildSelect({
            options: [
                { value: "1", text: "Alpha", hint: "First letter" },
                { value: "2", text: "Beta", hint: "Second letter" },
            ],
        });
        selectWithSearch(select);

        typeInSearch("Second");
        const choices = getDropdownChoices();
        expect(choices).toHaveLength(1);
        expect(choices[0].textContent).toContain("Beta");
    });

    test("search is case-insensitive on hint text", () => {
        const select = buildSelect({
            options: [
                { value: "1", text: "Alpha", hint: "First letter" },
                { value: "2", text: "Beta", hint: "Second letter" },
            ],
        });
        selectWithSearch(select);

        typeInSearch("second");
        const choices = getDropdownChoices();
        expect(choices).toHaveLength(1);
        expect(choices[0].textContent).toContain("Beta");
    });

    test("search returns no results when nothing matches", () => {
        const select = buildSelect({
            options: [
                { value: "1", text: "Alpha", hint: "First letter" },
                { value: "2", text: "Beta", hint: "Second letter" },
            ],
        });
        selectWithSearch(select);

        typeInSearch("Zzzzz");
        const choices = getDropdownChoices();
        expect(choices).toHaveLength(0);
    });

    test("logs error when applied to a non-select element", () => {
        document.body.innerHTML = "<div></div>";
        const div = document.querySelector("div");

        const errorSpy = vi
            .spyOn(console, "error")
            .mockImplementation(() => {});
        selectWithSearch(div);
        expect(errorSpy).toHaveBeenCalledWith(
            "select-with-search must be applied to a select element",
        );
    });
});
