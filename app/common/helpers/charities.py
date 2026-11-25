import re

# each charity register's numbers, as they are written on the register
ENGLAND_AND_WALES_CHARITY_NUMBER = re.compile(r"[0-9]{6,7}")
SCOTLAND_CHARITY_NUMBER = re.compile(r"SC0[0-9]{5}")
NORTHERN_IRELAND_CHARITY_NUMBER = re.compile(r"NIC[0-9]{6}")


def clean_charity_number(charity_number: str) -> str:
    """Removes whitespace and upper-cases, without checking the format; a Scottish SC0 often typed as SCO is fixed."""
    charity_number = re.sub(r"\s", "", charity_number).upper()
    return re.sub(r"^SCO(?=[0-9]{5}$)", "SC0", charity_number)


def normalise_charity_number(charity_number: str) -> str:
    """The charity number as written on the register whose format it is in, or a ValueError if in none of them."""
    charity_number = clean_charity_number(charity_number)
    if not any(
        pattern.fullmatch(charity_number)
        for pattern in (ENGLAND_AND_WALES_CHARITY_NUMBER, SCOTLAND_CHARITY_NUMBER, NORTHERN_IRELAND_CHARITY_NUMBER)
    ):
        raise ValueError(
            "Charity number must be 6 or 7 digits (England and Wales), SC0 followed by 5 digits (Scotland), "
            "or NIC followed by 6 digits (Northern Ireland), for example 1234567, SC012345 or NIC123456"
        )
    return charity_number
