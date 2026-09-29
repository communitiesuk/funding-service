from app.deliver_grant_funding.admin.entities import PlatformAdminCollectionView


def test_collection_admin_form_includes_email_settings():
    assert "send_deadline_reminder_emails" in PlatformAdminCollectionView.form_columns
    assert "send_overdue_emails" in PlatformAdminCollectionView.form_columns
    assert PlatformAdminCollectionView.column_labels["send_deadline_reminder_emails"] == "Send deadline reminder emails"
    assert PlatformAdminCollectionView.column_labels["send_overdue_emails"] == "Send overdue emails"
