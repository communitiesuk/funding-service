import random
from typing import Sequence

from app.common.data.models import Collection
from app.common.data.types import CollectionType


def generate_submission_reference(collection: Collection, avoid_references: Sequence[str] | None = None) -> str:
    # Removed letters and numbers where there could be confusion (eg 0 and O, B and 8, etc)
    # Removed all vowels to reduce the chance of forming real possibly-offensive words
    alphabet = "234679CDFGHJKLMNPQRTVWXYZ"

    grant_code = collection.grant.code

    limit = 100
    while limit:
        submission_code = "".join(random.choices(alphabet, k=6))

        match collection.type:
            case CollectionType.MONITORING_REPORT:
                fmt = "{grant_code}-R{submission_code}"

            case _:
                raise RuntimeError(f"Cannot generate reference for unknown submission type {collection.type}")

        reference = fmt.format(grant_code=grant_code, submission_code=submission_code)
        if not avoid_references or reference not in avoid_references:
            return reference

        limit -= 1

    raise RuntimeError("Could not generate a unique submission reference")
