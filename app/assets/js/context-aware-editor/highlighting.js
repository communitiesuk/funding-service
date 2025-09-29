// Reference highlighting functionality
// Refactored from reference-overlay to work as part of combined editor

const REFERENCE_REGEX = /\(\([^)]+\)\)/g

const parseReferences = (text, mappings = null) => {
  const references = []
  let match

  while ((match = REFERENCE_REGEX.exec(text)) !== null) {
    const referenceContent = match[0].slice(2, -2) // Remove (( and ))

    // Determine if this reference is resolved/valid
    let isResolved = false
    if (mappings) {
      // In visible textarea: check if the human-readable content matches any mapping value
      // In hidden textarea: check if the reference ID exists as a mapping key

      // Check if this is a raw reference ID (key in mappings)
      if (mappings.has(referenceContent)) {
        isResolved = true
      } else {
        // Check if this human-readable text matches any mapping value
        for (const [id, humanText] of mappings.entries()) {
          if (humanText === match[0]) { // Compare full ((text)) format
            isResolved = true
            break
          }
        }
      }
    } else {
      // When no mappings provided, treat everything as unresolved
      isResolved = false
    }

    references.push({
      match: match[0],
      reference: referenceContent,
      start: match.index,
      end: match.index + match[0].length,
      isResolved: isResolved
    })
  }

  return references
}

const resolveReference = (reference, mappings) => {
  return mappings.get(reference) || null
}

const transformTextToHumanReadable = (text, mappings) => {
  let transformedText = text
  const references = parseReferences(text, mappings)

  // Process references in reverse order to maintain string positions
  references.reverse().forEach(ref => {
    const humanReadableText = resolveReference(ref.reference, mappings)

    if (humanReadableText) {
      // Extract the human-readable part (remove (( and )))
      const cleanText = humanReadableText.slice(2, -2)
      const replacement = `((${cleanText}))`
      transformedText = transformedText.substring(0, ref.start) + replacement + transformedText.substring(ref.end)
    }
  })

  return transformedText
}

const transformTextToRawReferences = (text, reverseMappings) => {
  let transformedText = text
  const references = parseReferences(text, reverseMappings)

  // Process references in reverse order to maintain string positions
  references.reverse().forEach(ref => {
    const referenceId = reverseMappings.get(ref.match)

    if (referenceId) {
      transformedText = transformedText.substring(0, ref.start) + referenceId + transformedText.substring(ref.end)
    }
  })

  return transformedText
}

const updateHighlightOverlay = (visibleTextarea, highlightOverlay, mappings) => {
  const text = visibleTextarea.value
  let highlightedHtml = text
  const references = parseReferences(text, mappings)

  // Process references in reverse order to maintain string positions
  references.reverse().forEach(ref => {
    if (ref.isResolved) {
      // Wrap valid references with highlight span
      const replacement = `<span class="app-context-aware-editor--valid-reference">${ref.match}</span>`
      highlightedHtml = highlightedHtml.substring(0, ref.start) + replacement + highlightedHtml.substring(ref.end)
    }
    // Invalid references remain unstyled (normal text)
  })

  // Escape HTML in text outside of our spans, but preserve our spans
  const parts = highlightedHtml.split(/(<span class="app-context-aware-editor--valid-reference">.*?<\/span>)/g)
  const escapedHtml = parts.map(part => {
    if (part.startsWith('<span class="app-context-aware-editor--valid-reference">')) {
      return part // Keep our highlight spans as-is
    } else {
      // Escape HTML in text content and convert newlines
      return part.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/\n/g, '<br>')
    }
  }).join('')

  highlightOverlay.innerHTML = escapedHtml

  // Sync scroll position
  highlightOverlay.scrollTop = visibleTextarea.scrollTop
  highlightOverlay.scrollLeft = visibleTextarea.scrollLeft
}

const getReferenceBoundaries = (text, mappings = null) => {
  const references = parseReferences(text, mappings)
  return references
    .filter(ref => ref.isResolved) // Only include resolved references
    .map(ref => ({ start: ref.start, end: ref.end }))
    .sort((a, b) => a.start - b.start)
}

const adjustCursorPosition = (textarea, newPosition, direction = 0, mappings = null) => {
  const text = textarea.value
  const boundaries = getReferenceBoundaries(text, mappings)

  for (const boundary of boundaries) {
    // If cursor is inside a reference, move to boundary
    if (newPosition > boundary.start && newPosition < boundary.end) {
      return direction >= 0 ? boundary.end : boundary.start
    }
    // If moving right and hitting start of reference, jump to end
    if (direction > 0 && newPosition === boundary.start) {
      return boundary.end
    }
    // If moving left and hitting end of reference, jump to start
    if (direction < 0 && newPosition === boundary.end) {
      return boundary.start
    }
  }

  return newPosition
}

// Helper function to delete text in a way that preserves undo history
const deleteTextPreservingUndo = (textarea, startPos, endPos) => {
  // Select the range to delete
  textarea.setSelectionRange(startPos, endPos)

  // Use execCommand if available (for older browsers), otherwise use newer approach
  if (document.execCommand) {
    document.execCommand('delete', false, null)
  } else {
    // Modern approach: dispatch a deleteContentBackward input event
    const inputEvent = new InputEvent('beforeinput', {
      inputType: 'deleteContentBackward',
      cancelable: true
    })

    if (textarea.dispatchEvent(inputEvent)) {
      // If the beforeinput event wasn't cancelled, perform the deletion
      textarea.setRangeText('', startPos, endPos, 'end')

      // Dispatch the input event to notify listeners
      textarea.dispatchEvent(new InputEvent('input', {
        inputType: 'deleteContentBackward'
      }))
    }
  }
}

const handleKeyDown = (textarea, event, mappings) => {
  const { key, shiftKey } = event
  const start = textarea.selectionStart
  const end = textarea.selectionEnd

  const boundaries = getReferenceBoundaries(textarea.value, mappings)

  switch (key) {
    case 'ArrowLeft':
    case 'ArrowRight': {
      if (start !== end && !shiftKey) return // Has selection, let default behavior handle it

      const direction = key === 'ArrowRight' ? 1 : -1
      const currentPos = key === 'ArrowRight' ? end : start
      const newPos = adjustCursorPosition(textarea, currentPos, direction, mappings)

      if (newPos !== currentPos) {
        event.preventDefault()
        if (shiftKey) {
          // Extend selection based on direction
          if (direction > 0) {
            // Moving right: extend from original start to new position
            textarea.setSelectionRange(start, newPos)
          } else {
            // Moving left: extend from new position to original end
            textarea.setSelectionRange(newPos, end)
          }
        } else {
          // Move cursor
          textarea.setSelectionRange(newPos, newPos)
        }
      }
      break
    }

    case 'Backspace': {
      if (start !== end) return // Has selection, let default behavior handle it

      // Check if we're at the end of a reference
      const refAtCursor = boundaries.find(b => start === b.end)
      if (refAtCursor) {
        event.preventDefault()
        // Delete entire reference using undo-friendly method
        deleteTextPreservingUndo(textarea, refAtCursor.start, refAtCursor.end)
      }
      break
    }

    case 'Delete': {
      if (start !== end) return // Has selection, let default behavior handle it

      // Check if we're at the start of a reference
      const refAtCursor = boundaries.find(b => start === b.start)
      if (refAtCursor) {
        event.preventDefault()
        // Delete entire reference using undo-friendly method
        deleteTextPreservingUndo(textarea, refAtCursor.start, refAtCursor.end)
      }
      break
    }

    case 'Home':
    case 'End': {
      // Allow normal home/end behavior
      break
    }
  }
}

const handleClick = (textarea, event, mappings) => {
  // Get click position
  const clickPosition = textarea.selectionStart
  const boundaries = getReferenceBoundaries(textarea.value, mappings)

  // Check if click is inside a reference
  const clickedRef = boundaries.find(b => clickPosition > b.start && clickPosition < b.end)
  if (clickedRef) {
    // Move cursor to nearest boundary
    const distToStart = clickPosition - clickedRef.start
    const distToEnd = clickedRef.end - clickPosition
    const newPos = distToStart <= distToEnd ? clickedRef.start : clickedRef.end

    setTimeout(() => {
      textarea.setSelectionRange(newPos, newPos)
    }, 0)
  }
}

const handleDoubleClick = (textarea, event, mappings) => {
  const clickPosition = textarea.selectionStart
  const boundaries = getReferenceBoundaries(textarea.value, mappings)

  // Check if double-click is inside a reference
  const clickedRef = boundaries.find(b => clickPosition >= b.start && clickPosition <= b.end)
  if (clickedRef) {
    event.preventDefault()
    // Select entire reference
    textarea.setSelectionRange(clickedRef.start, clickedRef.end)
  }
}

/**
 * Creates the highlighting overlay and sets up reference highlighting
 * @param {HTMLElement} visibleTextarea - The visible textarea element
 * @param {HTMLElement} hiddenTextarea - The hidden textarea for form submission
 * @param {Map} mappings - Reference mappings (ID -> human text)
 * @param {Map} reverseMappings - Reverse mappings (human text -> ID)
 * @returns {Object} Object containing the highlighting overlay and sync function
 */
const createHighlighting = (visibleTextarea, hiddenTextarea, mappings, reverseMappings) => {
  // Create highlight overlay
  const highlightOverlay = document.createElement('div')
  highlightOverlay.classList.add('app-context-aware-editor__highlight-overlay')
  highlightOverlay.setAttribute('aria-hidden', 'true')

  // Transform initial content to human-readable
  const humanReadableText = transformTextToHumanReadable(hiddenTextarea.value, mappings)
  visibleTextarea.value = humanReadableText

  // Update highlight overlay initially
  updateHighlightOverlay(visibleTextarea, highlightOverlay, mappings)

  // Sync function to update hidden textarea and highlights
  const syncVisibleToHidden = () => {
    // Transform visible text back to raw references
    const rawText = transformTextToRawReferences(visibleTextarea.value, reverseMappings)
    hiddenTextarea.value = rawText

    // Trigger input event on hidden textarea to notify ajax-markdown-preview
    const inputEvent = new Event('input', { bubbles: true })
    hiddenTextarea.dispatchEvent(inputEvent)

    // Update highlight overlay
    updateHighlightOverlay(visibleTextarea, highlightOverlay, mappings)
  }

  // Add event listeners
  visibleTextarea.addEventListener('input', syncVisibleToHidden)

  // Add scroll sync for highlight overlay
  visibleTextarea.addEventListener('scroll', () => {
    highlightOverlay.scrollTop = visibleTextarea.scrollTop
    highlightOverlay.scrollLeft = visibleTextarea.scrollLeft
  })

  // Add atomic reference handling
  visibleTextarea.addEventListener('keydown', (event) => handleKeyDown(visibleTextarea, event, mappings))
  visibleTextarea.addEventListener('click', (event) => handleClick(visibleTextarea, event, mappings))
  visibleTextarea.addEventListener('dblclick', (event) => handleDoubleClick(visibleTextarea, event, mappings))

  return {
    highlightOverlay,
    syncVisibleToHidden
  }
}

/**
 * Parses reference mappings from JSON string
 * @param {string} mappingData - JSON string of reference mappings
 * @returns {Object} Object containing mappings and reverseMappings Maps
 */
const parseReferenceMappings = (mappingData) => {
  let mappings = new Map()
  let reverseMappings = new Map()

  if (mappingData && mappingData.trim() !== '') {
    try {
      const parsed = JSON.parse(mappingData)
      // Convert object to Map
      if (typeof parsed === 'object' && parsed !== null) {
        mappings = new Map(Object.entries(parsed))

        // Build reverse mappings (human-readable -> reference ID)
        for (const [referenceId, humanReadableText] of mappings) {
          reverseMappings.set(humanReadableText, `((${referenceId}))`)
        }
      }
    } catch (error) {
      console.warn('Failed to parse reference mappings:', error, 'Data:', mappingData)
    }
  }

  return { mappings, reverseMappings }
}

export { createHighlighting, parseReferenceMappings }
