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
    PlatformAdminCollectionLifecycleView,
    PlatformAdminDataAnalysisView,
    PlatformAdminDeltaCertifiersView,
    PlatformAdminDeveloperToolsView,
)


def register_admin_views(flask_admin: Admin, db_: SQLAlchemy) -> None:
    flask_admin.add_view(
        PlatformAdminCollectionLifecycleView(
            name="Collection lifecycle", endpoint="collection_lifecycle", url="collection-lifecycle"
        )
    )
    flask_admin.add_view(
        PlatformAdminDataAnalysisView(name="Data analysis", endpoint="data_analysis", url="data-analysis")
    )
    flask_admin.add_view(
        PlatformAdminDeltaCertifiersView(name="Delta certifiers", endpoint="delta_certifiers", url="delta-certifiers")
    )
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
