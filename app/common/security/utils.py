from urllib.parse import urlsplit

from flask import current_app, request, url_for


def sanitise_redirect_url(url: str) -> str:
    safe_fallback_url = url_for("index")

    url_next = urlsplit(url)
    current_base_url = urlsplit(request.host_url)

    if (url_next.netloc or url_next.scheme) and url_next.netloc != current_base_url.netloc:
        current_app.logger.warning(
            "Attempt to redirect to unsafe URL %(bad_url)s; sanitised to %(safe_url)s",
            dict(bad_url=url, safe_url=safe_fallback_url),
        )
        return safe_fallback_url

    if url_next.scheme and url_next.scheme not in {"http", "https"}:
        current_app.logger.warning(
            "Attempt to redirect to URL with unexpected protocol %(bad_url)s; sanitised to %(safe_url)s",
            dict(bad_url=url, safe_url=safe_fallback_url),
        )
        return safe_fallback_url

    sanitised_url_next = url_next.path
    if url_next.query:
        sanitised_url_next += "?" + url_next.query

    return sanitised_url_next
