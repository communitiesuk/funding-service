import re


def slugify(text: str) -> str:
    """
    Convert a string to a URL-friendly slug containing only lowercase alphanumeric characters and hyphens.
    :param text: The string to turn into a slug
    :return: The resulting slug

    For example:
        - "Hello World" -> "hello-world"
        - "Special #$@! Characters" -> "special-characters"
        - "ångström unicode" -> "ngstrm-unicode"
    """
    if not text:
        return ""
    # Remove non-alphanumeric characters except spaces
    text = re.sub(r"[^a-zA-Z0-9\s\-]", "", text)
    # Convert to lowercase

    text = text.lower()
    # Replace spaces (one or more) with a single hyphen
    text = re.sub(r"\s+", "-", text.strip())
    return text
