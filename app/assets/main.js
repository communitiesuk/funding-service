import { initAll } from 'govuk-frontend'
initAll();

var MHCLG = window.MHCLG || {};
MHCLG.FSModules = MHCLG.FSModules || {};

MHCLG.fsModules = {
    find: function (container) {
        container = container || document.getElementsByTagName('body')[0];

        var modules;
        var moduleSelector = '[data-fs-module]';

        modules = container.querySelectorAll(moduleSelector);

        // Container could be a module too
        // if (container.is(moduleSelector)) {
        //     modules = modules.add(container);
        // }

        return modules;
    },

    start: function (container) {
        var modules = this.find(container);

        for (var i = 0, l = modules.length; i < l; i++) {
            var module;
            var element = modules[i];
            var type = camelCaseAndCapitalise(element.dataset.fsModule);
            var started = element.dataset.moduleStarted;

            if (typeof MHCLG.FSModules[type] === 'function' && !started) {
                module = new MHCLG.FSModules[type]();
                module.start(element);
                element.dataset.moduleStarted = "true";
            }
        }

        // eg selectable-table to SelectableTable
        function camelCaseAndCapitalise(string) {
            return capitaliseFirstLetter(camelCase(string));
        }

        // http://stackoverflow.com/questions/6660977/convert-hyphens-to-camel-case-camelcase
        function camelCase(string) {
            return string.replace(/-([a-z])/g, function (g) {
                return g.charAt(1).toUpperCase();
            });
        }

        // http://stackoverflow.com/questions/1026069/capitalize-the-first-letter-of-string-in-javascript
        function capitaliseFirstLetter(string) {
            return string.charAt(0).toUpperCase() + string.slice(1);
        }
    }
};

window.MHCLG = MHCLG;

(function (window) {
    "use strict";

    window.MHCLG.FSModules.GenerateQuestionName = function () {
        let debounceTimer;
        let lastRequestTime = 0;
        const RATE_LIMIT_MS = 1000; // Minimum 1 second between requests
        const DEBOUNCE_MS = 500; // Wait 500ms after blur event

        const makeApiCall = async (inputValue, targetElement, component, outputElement) => {
            // Rate limiting check
            const now = Date.now();
            if (now - lastRequestTime < RATE_LIMIT_MS) {
                return;
            }
            lastRequestTime = now;

            // Input validation
            if (!inputValue || inputValue.trim().length === 0) {
                // Remove loading class if no value to process
                targetElement.classList.remove('api-loading');
                return;
            }

            outputElement.disabled = true;

            // Collect form data if form ID is specified
            let formData = new FormData();
            const formId = component.dataset.fsModuleFormId;
            if (formId) {
                const form = document.getElementById(formId);
                if (form) {
                    const formDataObj = new FormData(form);
                    // Copy all form fields to our FormData object
                    for (let [key, value] of formDataObj.entries()) {
                        formData.append(key, value);
                    }
                } else {
                    console.warn(`Form with ID '${formId}' not found`);
                }
            }

            // Add the input value that triggered the API call
            formData.append('question', inputValue.trim());

            try {
                const response = await fetch('/developers/deliver/api/generate-question-name', {
                    method: 'POST',
                    headers: {
                        'X-Requested-With': 'XMLHttpRequest'
                    },
                    credentials: 'include', // Include cookies for authentication
                    body: formData
                });

                // Check if response is ok
                if (!response.ok) {
                    const errorText = await response.text();
                    throw new Error(`API Error ${response.status}: ${errorText}`);
                }

                // Try to parse as JSON, but handle non-JSON responses gracefully
                let data;
                const contentType = response.headers.get('content-type');
                if (contentType?.includes('application/json')) {
                    data = await response.json();
                } else {
                    // Handle non-JSON response (e.g., plain text)
                    const textResponse = await response.text();
                    data = { generatedName: textResponse };
                }

                // Validate response structure (only for JSON responses)
                if (contentType?.includes('application/json') && (!data || typeof data !== 'object')) {
                    throw new Error('Invalid response data structure');
                }

                // Update target element or related field
                if (data.name && outputElement) {
                    outputElement.value = data.name;
                }

            } catch (error) {
                console.error('Failed to generate question name:', error);

                // Optional: Show user feedback
                // You could show a toast notification or inline error here

            } finally {
                // Re-enable the output element
                if (outputElement) {
                    outputElement.disabled = false;

                    // Get element's bounding rectangle
                    const rect = outputElement.getBoundingClientRect();

                    // Get viewport dimensions
                    const viewportWidth = window.innerWidth;
                    const viewportHeight = window.innerHeight;

                    // Calculate normalized coordinates (0-1)
                    const normalizedX = (rect.left + rect.width / 2) / viewportWidth;
                    const normalizedY = (rect.top + rect.height / 2) / viewportHeight;

                    const origin = {
                        x: Math.max(0, Math.min(1, normalizedX)), // Clamp between 0-1
                        y: Math.max(0, Math.min(1, normalizedY))  // Clamp between 0-1
                    };

                }
            }
        };

        this.start = function (component) {
            const targetComponent = document.getElementById(component.dataset.fsModuleTargetInputId);

            if (!targetComponent) {
                console.error('Target input element not found:', component.dataset.fsModuleTargetInputId);
                return;
            }

            // Main blur event handler with debouncing
            targetComponent.addEventListener('blur', (e) => {
                const inputValue = e.target.value;

                // Clear any existing debounce timer
                clearTimeout(debounceTimer);

                // Get the output element
                const outputElement = document.getElementById(
                    component.dataset.fsModuleTargetOutputId
                );

                // Don't proceed if output already has a value
                if (outputElement && outputElement.value && outputElement.value.trim().length > 0) {
                    return;
                }

                // If no valid input, return
                if (!inputValue || inputValue.trim().length === 0) {
                    return;
                }

                // Disable the output element immediately
                if (outputElement) {
                    outputElement.disabled = true;
                }

                // Debounce the API call
                debounceTimer = setTimeout(() => {
                    makeApiCall(inputValue, e.target, component, outputElement);
                }, DEBOUNCE_MS);
            });

            // Cleanup on page unload
            const cleanup = () => {
                clearTimeout(debounceTimer);
            };

            window.addEventListener('beforeunload', cleanup);

            // Store cleanup function for potential manual cleanup
            component._cleanup = cleanup;
        };
    };
})(window);

(() => {MHCLG.fsModules.start()})();
