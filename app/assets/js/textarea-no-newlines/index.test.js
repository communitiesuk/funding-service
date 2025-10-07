/**
 * @vitest-environment jsdom
 */

import textareaNoNewlines from ".";

describe("textareaNoNewlines", () => {
    let textarea;

    beforeEach(() => {
        document.body.innerHTML = "<textarea></textarea>";
        textarea = document.querySelector("textarea");
        textareaNoNewlines(textarea);
    });

    test("prevents Enter key from inserting newlines", () => {
        const enterEvent = new KeyboardEvent("keydown", {
            key: "Enter",
            bubbles: true,
            cancelable: true,
        });

        const preventDefaultSpy = vi.spyOn(enterEvent, "preventDefault");

        textarea.dispatchEvent(enterEvent);

        expect(preventDefaultSpy).toHaveBeenCalled();
    });

    test("allows other keys to work normally", () => {
        const spaceEvent = new KeyboardEvent("keydown", {
            key: " ",
            bubbles: true,
            cancelable: true,
        });

        const preventDefaultSpy = vi.spyOn(spaceEvent, "preventDefault");

        textarea.dispatchEvent(spaceEvent);

        expect(preventDefaultSpy).not.toHaveBeenCalled();
    });

    test("allows Tab key to work normally", () => {
        const tabEvent = new KeyboardEvent("keydown", {
            key: "Tab",
            bubbles: true,
            cancelable: true,
        });

        const preventDefaultSpy = vi.spyOn(tabEvent, "preventDefault");

        textarea.dispatchEvent(tabEvent);

        expect(preventDefaultSpy).not.toHaveBeenCalled();
    });

    test("allows Escape key to work normally", () => {
        const escapeEvent = new KeyboardEvent("keydown", {
            key: "Escape",
            bubbles: true,
            cancelable: true,
        });

        const preventDefaultSpy = vi.spyOn(escapeEvent, "preventDefault");

        textarea.dispatchEvent(escapeEvent);

        expect(preventDefaultSpy).not.toHaveBeenCalled();
    });

    test("allows Backspace key to work normally", () => {
        const backspaceEvent = new KeyboardEvent("keydown", {
            key: "Backspace",
            bubbles: true,
            cancelable: true,
        });

        const preventDefaultSpy = vi.spyOn(backspaceEvent, "preventDefault");

        textarea.dispatchEvent(backspaceEvent);

        expect(preventDefaultSpy).not.toHaveBeenCalled();
    });
});
