from dataclasses import dataclass

# Fixture data standing in for real Companies House / Charity Commission lookups. This is a proof-of-concept branch
# for a demo; there is no external API integration here.


@dataclass(frozen=True)
class RegisteredOrganisation:
    reference_number: str
    name: str


_COMPANIES_HOUSE: dict[str, RegisteredOrganisation] = {
    "01234567": RegisteredOrganisation("01234567", "Northern Regeneration Partners Limited"),
    "08765432": RegisteredOrganisation("08765432", "Coastal Community Housing Limited"),
    "12345678": RegisteredOrganisation("12345678", "Green Futures Construction Limited"),
    "SC456789": RegisteredOrganisation("SC456789", "Clydeside Enterprise Company Limited"),
}

_CHARITY_COMMISSION: dict[str, RegisteredOrganisation] = {
    "1122334": RegisteredOrganisation("1122334", "The Riverside Youth Trust"),
    "209078": RegisteredOrganisation("209078", "Midlands Community Foundation"),
    "1155000": RegisteredOrganisation("1155000", "Homes for Everyone"),
    "1098765": RegisteredOrganisation("1098765", "Coastal Heritage Association"),
}

COMPANIES_HOUSE_REFERENCES: list[str] = list(_COMPANIES_HOUSE)
CHARITY_COMMISSION_REFERENCES: list[str] = list(_CHARITY_COMMISSION)


def _normalise(reference_number: str) -> str:
    return reference_number.strip().upper()


def lookup_company(reference_number: str) -> RegisteredOrganisation | None:
    return _COMPANIES_HOUSE.get(_normalise(reference_number))


def lookup_charity(reference_number: str) -> RegisteredOrganisation | None:
    return _CHARITY_COMMISSION.get(_normalise(reference_number))
