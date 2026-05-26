from flask_admin import Admin
from flask_sqlalchemy_lite import SQLAlchemy

from app.deliver_grant_funding.admin.entities import (
    PlatformAdminAuditEventView,
    PlatformAdminCollectionView,
    PlatformAdminGrantRecipientView,
    PlatformAdminGrantView,
    PlatformAdminInvitationView,
    PlatformAdminOrganisationView,
    PlatformAdminQuestionView,
    PlatformAdminSubmissionEventView,
    PlatformAdminSubmissionView,
    PlatformAdminUserRoleView,
    PlatformAdminUserView,
)
from app.deliver_grant_funding.admin.views import (
    PlatformAdminDataAnalysisView,
    PlatformAdminDeltaCertifiersView,
    PlatformAdminDeveloperToolsView,
    PlatformAdminReportingLifecycleView,
)


def register_admin_views(flask_admin: Admin, db_: SQLAlchemy) -> None:
    flask_admin.add_view(
        PlatformAdminReportingLifecycleView(
            name="Reporting lifecycle", endpoint="reporting_lifecycle", url="reporting-lifecycle"
        )
    )
    flask_admin.add_view(
        PlatformAdminDataAnalysisView(name="Data analysis", endpoint="data_analysis", url="data-analysis")
    )
    flask_admin.add_view(PlatformAdminDeltaCertifiersView(name="Certifiers", endpoint="certifiers", url="certifiers"))
    flask_admin.add_view(PlatformAdminSubmissionView(db_))
    flask_admin.add_view(PlatformAdminSubmissionEventView(db_))

    flask_admin.add_view(PlatformAdminUserView(db_))
    flask_admin.add_view(PlatformAdminUserRoleView(db_))
    flask_admin.add_view(PlatformAdminOrganisationView(db_))
    flask_admin.add_view(PlatformAdminGrantView(db_))
    flask_admin.add_view(PlatformAdminGrantRecipientView(db_))
    flask_admin.add_view(PlatformAdminCollectionView(db_))
    flask_admin.add_view(PlatformAdminQuestionView(db_))
    flask_admin.add_view(PlatformAdminInvitationView(db_))
    flask_admin.add_view(PlatformAdminAuditEventView(db_))

    flask_admin.add_view(
        PlatformAdminDeveloperToolsView(
            name="Developer tools", endpoint="developer_tools", url="developer-tools", category="Developer tools"
        )
    )
