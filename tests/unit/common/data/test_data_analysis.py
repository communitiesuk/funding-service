from app.common.data.interfaces.data_analysis import UserManagementEventCsvRow, UserManagementEventSource


def test_user_management_event_csv_row_headers_and_values_stay_in_field_order():
    row = UserManagementEventCsvRow(
        timestamp="timestamp",
        event="event",
        source=UserManagementEventSource.SELF_SERVE,
        grant_name="grant_name",
        grant_id="grant_id",
        grant_ggis_number="grant_ggis_number",
        organisation_name="organisation_name",
        organisation_id="organisation_id",
        organisation_external_id="organisation_external_id",
        pre_award_or_monitoring="pre_award_or_monitoring",
        actor_email="actor_email",
        permissions="permissions",
        invite_date="invite_date",
        accepted_date="accepted_date",
        unclaimed_invitation=1,
    )

    assert UserManagementEventCsvRow.csv_headers() == [
        "Timestamp",
        "Event",
        "Source",
        "Grant name",
        "Grant ID",
        "Grant GGIS number",
        "Organisation name",
        "Organisation ID",
        "Organisation external ID",
        "Pre-award or monitoring",
        "Actor email",
        "Permissions",
        "Invite date",
        "Accepted date",
        "Unclaimed invitation",
    ]
    assert row.as_csv_row() == [
        "timestamp",
        "event",
        "self-serve",
        "grant_name",
        "grant_id",
        "grant_ggis_number",
        "organisation_name",
        "organisation_id",
        "organisation_external_id",
        "pre_award_or_monitoring",
        "actor_email",
        "permissions",
        "invite_date",
        "accepted_date",
        1,
    ]
