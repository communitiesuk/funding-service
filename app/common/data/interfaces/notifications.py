from app.common.data.base import BaseModel
from app.extensions import db
from app.services.notify import NotificationReference


def resolve_notification_reference(reference: NotificationReference) -> BaseModel:
    """
    When certain emails are triggered by actions related to DB entities, we associate a reference with the email so
    that we can link it back to the related entity in GOV.UK Notify callbacks. For example, when users are invited
    to an Access grant funding team, we associate the email with the invitation in the DB. If email delivery fails,
    we get a callback from Notify containing the reference which lets us look up the original invitation and notify
    the person who created the invitation that delivery failed.

    This takes a GOV.UK Notification reference and returns the associated DB entity.
    """
    table = BaseModel.metadata.tables.get(reference.table_name)
    mapper = next(
        (mapper for mapper in BaseModel.registry.mappers if mapper.local_table is table and mapper.inherits is None),
        None,
    )
    if mapper is None:
        raise ValueError(f"Unknown table in notification reference: {reference.reference!r}")
    return db.session.get_one(mapper.class_, reference.id)
