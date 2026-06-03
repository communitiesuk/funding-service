import threading

# Playwright's sync API runs an asyncio loop while it talks to chromium. Under gunicorn+gevent,
# multiple greenlets share an OS thread and asyncio's running-loop is thread-local, so concurrent
# PDF exports on one worker would observe each other's loop and Playwright would raise. Serialise
# PDF generation per worker. threading.Lock is monkey-patched by gevent into a greenlet-aware lock,
# so blocked greenlets cooperatively yield rather than block the OS thread.
pdf_export_lock = threading.Lock()
