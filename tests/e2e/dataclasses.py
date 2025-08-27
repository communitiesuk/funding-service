from dataclasses import dataclass


@dataclass
class E2ETestUser:
    email_address: str


@dataclass
class GuidanceText:
    heading: str
    body_heading: str
    body_link_text: str
    body_link_url: str
    body_ul_items: list[str]
    body_ol_items: list[str]
