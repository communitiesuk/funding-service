const textareaNoNewlines = (textArea) => {
    textArea.addEventListener('keydown', function(event) {
        if (event.key === 'Enter') {
            event.preventDefault();
        }
    });
}

export default textareaNoNewlines;
