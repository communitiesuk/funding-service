// Context Aware Editor with optional toolbar and reference highlighting
// This is an adaptation of GOV.UK Form's markdown-editor-toolbar.
// This component can be enabled for a textarea. It can (optionally) show the GOV.UK Forms toolbar that allows inserting
// markdown headings/links/lists into the textarea. It then also takes a set of 'context', which is a Funding Service
// specific feature. The textarea will be progressively enhanced to convert context references to human-readable labels.
// For example, a reference like `q_UUID` might map to the question "How much funding do you want?". This context-aware
// editor will dynamically replace `((q_UUID))` with a highlighted `((funding requested))` token to help form
// designers understand the context they're inserting into their questions.
//
// This component is highly dynamic. It replaces the original textarea (t1) with a duplicate textarea (t2) that copies
// all the styles from the source. t1 is then hidden, and t2 is overlaid with a div that applies that allows
// highlighting to happen. t1 contains the raw data for submission to the form; t2 contains the user-friendly display
// text. A mapping of context references to human-readable labels must be defined for the component in a script with
// the `data-context` attribute. When a reference, eg ((q_UUID)) is found in t2, it is replaced with the human-readable
// label and highlighted for visual importance.

import { createToolbarForTextArea } from "./toolbar.js";
import { createHighlighting, parseReferenceMappings } from "./highlighting.js";

const store = {
    components: new Map(), // Map container -> component data
};

const createEditorStructure = (originalTextarea, container, wrapperClasses) => {
    // Create main wrapper
    const wrapper = document.createElement("div");
    wrapper.classList.add("app-context-aware-editor--wrapper");

    // Add any additional wrapper classes if specified in the template
    if (wrapperClasses) {
        const classArray = wrapperClasses
            .split(" ")
            .filter((cls) => cls.trim());
        classArray.forEach((cls) => wrapper.classList.add(cls));
    }

    // Create toolbar container (initially hidden)
    const toolbarContainer = document.createElement("div");
    toolbarContainer.classList.add(
        "app-context-aware-editor__toolbar-container",
    );
    toolbarContainer.style.display = "none";

    // Create editor container for the textarea and highlight overlay
    const editorContainer = document.createElement("div");
    editorContainer.classList.add("app-context-aware-editor__editor-container");

    // Create visible textarea (copy of original)
    const visibleTextarea = originalTextarea.cloneNode(true);
    visibleTextarea.classList.add("app-context-aware-editor__visible-textarea");

    // Remove conflicting attributes from visible textarea
    visibleTextarea.removeAttribute("data-context-aware-editor-target");
    originalTextarea.removeAttribute("data-module");

    // Ensure that form submissions submit the original (raw) textarea but anchors target the visible textarea (for eg
    // error summaries).
    originalTextarea.removeAttribute("id");
    visibleTextarea.removeAttribute("name");

    // Hide original textarea but keep it in form
    originalTextarea.style.display = "none";
    originalTextarea.setAttribute("aria-hidden", "true");

    // Build structure
    wrapper.appendChild(toolbarContainer);
    editorContainer.appendChild(visibleTextarea); // highlight overlay will be inserted before this
    wrapper.appendChild(editorContainer);

    // Insert wrapper after original textarea
    originalTextarea.parentNode.insertBefore(
        wrapper,
        originalTextarea.nextSibling,
    );

    return {
        wrapper,
        toolbarContainer,
        editorContainer,
        visibleTextarea,
    };
};

const initializeContainer = (container) => {
    // Skip if already processed
    if (store.components.has(container)) return;

    // Find target textarea
    const originalTextarea = container.querySelector(
        "[data-context-aware-editor-target]",
    );
    if (!originalTextarea) {
        console.warn(
            "No textarea with data-context-aware-editor-target found in container",
        );
        return;
    }

    // Get configuration
    const toolbarEnabled =
        container.getAttribute("data-toolbar-enabled") === "true";
    const allowHeadings =
        container.getAttribute("data-allow-headings") === "true";
    const i18nData = container.getAttribute("data-i18n") || "{}";
    const referenceMappingsData =
        container.querySelector("[data-context]").textContent || "";
    const wrapperClasses = container.getAttribute("data-wrapper-classes") || "";

    let i18n = {};
    try {
        i18n = JSON.parse(i18nData);
    } catch (error) {
        console.warn("Failed to parse i18n data:", error);
    }

    // Parse reference mappings
    const { mappings, reverseMappings } = parseReferenceMappings(
        referenceMappingsData,
    );

    // Create editor structure
    const { wrapper, toolbarContainer, editorContainer, visibleTextarea } =
        createEditorStructure(originalTextarea, container, wrapperClasses);

    let toolbar = null;
    let highlighting = null;

    // Create toolbar if enabled
    if (toolbarEnabled) {
        toolbar = createToolbarForTextArea(
            visibleTextarea,
            i18n,
            allowHeadings,
        );
        toolbarContainer.appendChild(toolbar);
        toolbarContainer.style.display = "block";
    }

    // Create highlighting if reference mappings are provided
    highlighting = createHighlighting(
        visibleTextarea,
        originalTextarea,
        mappings,
        reverseMappings,
    );
    // Insert highlight overlay before visible textarea
    editorContainer.insertBefore(
        highlighting.highlightOverlay,
        visibleTextarea,
    );

    // Ensure overlay dimensions match the textarea
    const syncDimensions = () => {
        highlighting.highlightOverlay.style.width = `${visibleTextarea.offsetWidth}px`;
        highlighting.highlightOverlay.style.height = `${visibleTextarea.offsetHeight}px`;
    };

    // Initial sync
    syncDimensions();

    // Create ResizeObserver to keep overlay in sync
    const resizeObserver = new ResizeObserver((entries) => {
        for (let entry of entries) {
            if (entry.target === visibleTextarea) {
                syncDimensions();
            }
        }
    });
    resizeObserver.observe(visibleTextarea);

    // If toolbar is present, sync changes through both highlighting and toolbar
    if (toolbar) {
        const originalSyncFunction = highlighting.syncVisibleToHidden;
        // Override toolbar button callbacks to trigger highlighting sync
        const toolbarButtons = toolbar.querySelectorAll("button");
        toolbarButtons.forEach((button) => {
            button.addEventListener("click", () => {
                // Small delay to ensure text has been updated
                setTimeout(originalSyncFunction, 0);
            });
        });
    }

    // Store component data for cleanup
    store.components.set(container, {
        wrapper,
        originalTextarea,
        visibleTextarea,
        toolbar,
        highlighting,
    });
};

const cleanup = (container) => {
    const componentData = store.components.get(container);
    if (!componentData) return;

    const { wrapper, originalTextarea } = componentData;

    // Remove wrapper
    if (wrapper && wrapper.parentNode) {
        wrapper.parentNode.removeChild(wrapper);
    }

    // Restore original textarea
    originalTextarea.style.display = "";
    originalTextarea.removeAttribute("aria-hidden");

    // Clean up storage
    store.components.delete(container);
};

/**
 * Initializes combined markdown editor for containers with data-module="context-aware-editor"
 * @param {HTMLElement|NodeList} containers - Container elements or selector
 */
const combinedMarkdownEditor = (containers) => {
    if (!containers) {
        // Auto-initialize all containers with data-module="context-aware-editor"
        containers = document.querySelectorAll(
            '[data-module="context-aware-editor"]',
        );
    }

    if (containers.length !== undefined) {
        // Handle NodeList
        containers.forEach((container) => {
            initializeContainer(container);
        });
    } else {
        // Handle single container
        initializeContainer(containers);
    }
};

// Export both the main function and cleanup for testing
combinedMarkdownEditor.cleanup = cleanup;

export default combinedMarkdownEditor;
