from flask_wtf import FlaskForm
from govuk_frontend_wtf.wtforms_widgets import GovSubmitInput
from wtforms import SubmitField


# TODO: move all forms used by developer pages into this module. Add some linting rule that prevents any other parts
#       of the app importing from the developers package.
class ConfirmDeletionForm(FlaskForm):
    confirm_deletion = SubmitField("Confirm deletion", widget=GovSubmitInput())


class BecomeGrantTeamMemberForm(FlaskForm):
    submit = SubmitField("Become grant team member", widget=GovSubmitInput())
