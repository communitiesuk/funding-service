class RedirectException(Exception):
    def __init__(self, url: str) -> None:
        self.url = url
