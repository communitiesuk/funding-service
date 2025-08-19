import debounce from '../utils/debounce'

const store = {
  target: null,
  source: null,
  authenticityToken: null,
  csrfToken: null,
  liveRegion: null,
  i18n: null,
  errorArea: null
}

const setLoadingStatus = () => {
  store.liveRegion.setAttribute('aria-busy', 'true')
  store.target.innerHTML = `<p>${store.i18n.preview_loading}</p>`
}

const setFailureStatus = () => {
  store.target.innerHTML = `<p>${store.i18n.preview_error}</p>`
  const retryButton = document.createElement('button')
  retryButton.classList.add('govuk-button', 'govuk-button--secondary')
  retryButton.innerHTML = 'Retry preview'
  addEventListeners(retryButton, manuallyTriggerMarkdownPreview)
  store.target.appendChild(retryButton)
}

const triggerAjaxMarkdownPreview = async () => {
  try {
    if (store.endpoint) {
      const response = await window.fetch(store.endpoint, {
        method: 'POST',
        mode: 'same-origin',
        cache: 'no-cache',
        credentials: 'same-origin',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': store.csrfToken
        },
        redirect: 'follow',
        referrerPolicy: 'same-origin',
        body: JSON.stringify({
          markdown: store.source.value,
          authenticity_token: store.authenticityToken
        })
      })

      // insert the preview into the DOM
      const json = await response.json()
      store.target.innerHTML = json.preview_html
      if (json.errors.length > 0) {
        addErrorToField(json.errors[0])
        addErrorClass()
      } else {
        clearErrorsFromField()
        removeErrorClass()
      }
      addNotification('Preview updated.')
    } else {
      throw new Error('No endpoint set')
    }
  } catch {
    setFailureStatus()
    addNotification(store.i18n.preview_error)
  }
}

const manuallyTriggerMarkdownPreview = event => {
  event?.preventDefault()

  triggerAjaxMarkdownPreview()
}

const addEventListeners = (trigger, callback) => {
  trigger.addEventListener('click', callback)
}

// debounce the AJAX request so we don't hammer the server with one request per keystroke
const debouncedAjaxMarkdownPreview = debounce(() => {
  triggerAjaxMarkdownPreview()
}, 1000)

const inputEventListener = () => {
  setLoadingStatus()
  return debouncedAjaxMarkdownPreview()
}

const addLiveRegion = () => {
  const liveRegion = document.createElement('div')
  liveRegion.setAttribute('role', 'status')
  liveRegion.classList.add('app-markdown-editor__notification-area')
  store.liveRegion = liveRegion
  store.source.after(liveRegion)
}

const addNotification = text => {
  store.liveRegion.setAttribute('aria-busy', 'false')
  store.liveRegion.innerHTML = text
  setTimeout(() => {
    store.liveRegion.innerHTML = ''
  }, 5000)
}

const createErrorArea = () => {
  // Use existing error area if there's a server side error present on the field
  store.errorArea =
    store.source
      .closest('.govuk-form-group')
      ?.querySelector('.govuk-error-message') ?? document.createElement('p')
  store.errorArea.classList.add(
    'govuk-error-message',
    'app-markdown-editor__error-message'
  )
  store.source.closest('.govuk-form-group').prepend(store.errorArea)
  setAriaAttributesForError()
}

const setAriaAttributesForError = () => {
  if (!store.errorArea.getAttribute('id')) {
    const id = `${store.source.getAttribute('id')}-error`
    store.errorArea.setAttribute('id', id)
    store.source.setAttribute(
      'aria-describedby',
      `${id} ${store.source.getAttribute('aria-describedby')}`
    )
  }
  store.errorArea.setAttribute('aria-live', 'polite')
}

const addErrorToField = error => {
  if (!store.errorArea) createErrorArea()
  store.errorArea.innerHTML = `<span class="govuk-visually-hidden">Error:</span> ${error}`
}

const clearErrorsFromField = () => {
  if (!store.errorArea) createErrorArea()
  store.errorArea.innerHTML = ''
}

const addErrorClass = () => {
  store.source
    .closest('.govuk-form-group')
    ?.classList.add('govuk-form-group--error')
  store.source.classList.add('govuk-textarea--error')
}

const removeErrorClass = () => {
  store.source
    .closest('.govuk-form-group--error')
    ?.classList.remove('govuk-form-group--error')
  store.source.classList.remove('govuk-textarea--error')
}

/**
 * Submits markdown held in the source element to the endpoint when the source changes, and replaces the target element's content with the result of the request.
 * @param {HTMLElement} target - The element where the markdown preview should be rendered.
 * @param {HTMLElement} source - The element which contains the raw markdown for conversion.
 * @param {string} endpoint - The URL for the endpoint that renders the markdown.
 * @param {Object} i18n - An object containing translations for the component.
 */
const ajaxMarkdownPreview = (target, source, endpoint, i18n) => {
  store.target = target
  store.source = source
  store.endpoint = endpoint
  store.i18n = i18n
  store.authenticityToken = document.querySelector(
    'input[name="authenticity_token"]'
  )?.value
  store.csrfToken = document
    .querySelector('meta[name="csrf-token"]')
    ?.getAttribute('content')

  addLiveRegion()
  createErrorArea()

  // run on page load
  setLoadingStatus()
  triggerAjaxMarkdownPreview()

  // run when the user types
  source.addEventListener('input', inputEventListener)
}

export default ajaxMarkdownPreview
