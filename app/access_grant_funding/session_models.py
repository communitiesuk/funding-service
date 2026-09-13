import enum
from collections.abc import Mapping
from typing import Any, Self
from uuid import UUID

from flask import session, url_for
from pydantic import BaseModel, Field, PrivateAttr, ValidationError, model_validator

from app.common.data.models_user import User
from app.common.exceptions import SessionJourneyRecoveryRedirect
from app.constants import (
    CHECK_YOUR_ANSWERS,
    SESSION_CREATE_ORGANISATION,
    SESSION_EMITTED_PUBLIC_SIGN_UP_METRICS,
    SESSION_MATCHED_ORGANISATION,
    SESSION_SIGNING_UP_FOR_COLLECTION_ID,
)


class CreateOrganisationPage(enum.StrEnum):
    """The endpoints of the create organisation journey, declared in journey order: navigation ranks pages by it."""

    TYPE = "create_organisation_type"
    LOCAL_AUTHORITY = "create_organisation_local_authority"
    NAME = "create_organisation_name"
    ALREADY_EXISTS = "create_organisation_already_exists"
    TEAM_MEMBERS = "create_organisation_allow_team_members"
    USER_NAME = "create_organisation_user_name"
    CHECK_YOUR_ANSWERS = "create_organisation_check_your_answers"
    ELIGIBLE_TO_APPLY = "eligible_to_apply"
    SIGN_UP_ROUTER = "public_sign_up_router"


class SignUpOrganisationType(enum.StrEnum):
    COMPANY = "COMPANY"
    CHARITY = "CHARITY"
    LOCAL_AUTHORITY = "LOCAL_AUTHORITY"
    OTHER = "OTHER"

    @property
    def label(self) -> str:
        """The radio label for this type, reused for the check-your-answers summary row so the two can't drift."""
        match self:
            case SignUpOrganisationType.COMPANY:
                return "Registered company"
            case SignUpOrganisationType.CHARITY:
                return "Charity"
            case SignUpOrganisationType.LOCAL_AUTHORITY:
                return "Local authority"
            case SignUpOrganisationType.OTHER:
                return "Other"


class SignUpSession(BaseModel):
    """State carried between the screens of a public sign up journey, in the signed session cookie."""

    collection_id: UUID

    def to_session_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)

    @classmethod
    def from_session(cls, *, collection_id: UUID, session_data: dict[str, Any]) -> Self | None:
        """Reads the session, returning None if it doesn't hold everything `cls` requires.

        Subclasses tighten the fields to say which answers a screen can't be shown without.
        """
        try:
            sign_up_session = cls.model_validate(session_data)
        except ValidationError:
            return None

        # pin to the current sign up, only one is valid at a time
        return sign_up_session if sign_up_session.collection_id == collection_id else None


class MatchedOrganisationSession(SignUpSession):
    """Only required when additional screens are needed during matching
    like asking for the users name
    """

    organisation_id: UUID


class CreateOrganisationSession(SignUpSession):
    """A create organisation journey in progress, with nothing answered yet."""

    # which of the optional steps this user is asked is settled when the journey starts, so that
    # the screens along it don't each have to work it out from the user again
    needs_user_name: bool
    can_share_email_domain: bool

    organisation_type: SignUpOrganisationType | None = None
    name: str | None = None
    external_id: str | None = None
    # optional as only needed for users we don't have a name for on the model
    user_name: str | None = None
    # optional as only asked of users whose email domain isn't a shared provider
    allow_team_members: bool | None = None

    _page: CreateOrganisationPage = PrivateAttr()
    _grant_slug: str = PrivateAttr()
    _collection_slug: str = PrivateAttr()
    _from_check_your_answers: bool = PrivateAttr(default=False)

    @property
    def first_incomplete_page(self) -> CreateOrganisationPage:
        """The first applicable page still needing an answer.

        The local authority and check your answers pages are 'terminal' pages that collect nothing, so will always
        be 'incomplete' as part of the journey - making them the final page.
        """
        return next(page for page in self.pages if not self._is_answered(page))

    def _is_answered(self, page: CreateOrganisationPage) -> bool:
        """For a given page, check the session data and work out if it's been answered."""
        match page:
            case CreateOrganisationPage.TYPE:
                return self.organisation_type is not None
            case CreateOrganisationPage.NAME:
                return bool(self.name and self.external_id)
            case CreateOrganisationPage.TEAM_MEMBERS:
                return self.allow_team_members is not None
            case CreateOrganisationPage.USER_NAME:
                return bool(self.user_name)
            case _:
                return False

    @property
    def pages(self) -> list[CreateOrganisationPage]:
        """Work out the set of pages that should be visited by this session.

        This may change dynamically as the session develops.
        """
        if self.organisation_type == SignUpOrganisationType.LOCAL_AUTHORITY:
            return [CreateOrganisationPage.TYPE, CreateOrganisationPage.LOCAL_AUTHORITY]

        pages = [CreateOrganisationPage.TYPE, CreateOrganisationPage.NAME]

        if self.can_share_email_domain:
            pages.append(CreateOrganisationPage.TEAM_MEMBERS)

        if self.needs_user_name:
            pages.append(CreateOrganisationPage.USER_NAME)

        return [*pages, CreateOrganisationPage.CHECK_YOUR_ANSWERS]

    def _page_after(self, page: CreateOrganisationPage) -> CreateOrganisationPage | None:
        journey = list(CreateOrganisationPage)
        return next((candidate for candidate in self.pages if journey.index(candidate) > journey.index(page)), None)

    @property
    def _next_step(self) -> CreateOrganisationPage:
        next_step = self._page_after(self._page)
        if next_step is None:
            raise ValueError(f"{self._page} has no next input page")
        return next_step

    def page_url(self, page: CreateOrganisationPage, *, from_check_your_answers: bool | None = None) -> str:
        from_check_your_answers = (
            self._from_check_your_answers if from_check_your_answers is None else from_check_your_answers
        )
        return url_for(
            f"access_grant_funding.{page}",
            grant_slug=self._grant_slug,
            collection_slug=self._collection_slug,
            source=CHECK_YOUR_ANSWERS
            if from_check_your_answers
            and page
            not in (
                CreateOrganisationPage.CHECK_YOUR_ANSWERS,
                CreateOrganisationPage.ELIGIBLE_TO_APPLY,
                CreateOrganisationPage.SIGN_UP_ROUTER,
            )
            else None,
        )

    @property
    def next_page(self) -> str:
        """Next destination after a valid input submission; completion stays with its handler."""
        next_step = self._next_step
        if self._from_check_your_answers:
            next_step = self.first_incomplete_page
        return self.page_url(next_step)

    @property
    def previous_page(self) -> str:
        if self._page == CreateOrganisationPage.ALREADY_EXISTS:
            return self.page_url(CreateOrganisationPage.NAME)
        if (
            self._from_check_your_answers
            and self._page != CreateOrganisationPage.CHECK_YOUR_ANSWERS
            and self.first_incomplete_page == CreateOrganisationPage.CHECK_YOUR_ANSWERS
        ):
            return self.page_url(CreateOrganisationPage.CHECK_YOUR_ANSWERS)
        if self._page == CreateOrganisationPage.TYPE:
            return self.page_url(CreateOrganisationPage.ELIGIBLE_TO_APPLY)

        return self.page_url(self.pages[self.pages.index(self._page) - 1])

    def validate_for_page(
        self,
        page: CreateOrganisationPage,
        *,
        grant_slug: str,
        collection_slug: str,
        request_args: Mapping[str, str],
    ) -> None:
        """Bind this request's page and raise a recovery redirect if it cannot be visited."""
        self._page = page
        self._grant_slug = grant_slug
        self._collection_slug = collection_slug
        self._from_check_your_answers = request_args.get("source") == CHECK_YOUR_ANSWERS

        if page == CreateOrganisationPage.TYPE:
            return

        pages = self.pages
        answered_pages = pages.index(self.first_incomplete_page)
        if page == CreateOrganisationPage.ALREADY_EXISTS:
            # an interstitial off the name page, so only reachable once a name has been entered there
            if CreateOrganisationPage.NAME not in pages or answered_pages <= pages.index(CreateOrganisationPage.NAME):
                raise SessionJourneyRecoveryRedirect(self.page_url(CreateOrganisationPage.SIGN_UP_ROUTER))
            return
        if page not in pages:
            if page not in (CreateOrganisationPage.TEAM_MEMBERS, CreateOrganisationPage.USER_NAME):
                # a page for another type of organisation: choosing the type again leads to the right pages
                raise SessionJourneyRecoveryRedirect(self.page_url(CreateOrganisationPage.TYPE))
            # a step this user isn't asked: carry on to the next page that does apply, if this type has one
            next_step = self._page_after(page)
            if next_step is None or answered_pages < pages.index(next_step):
                raise SessionJourneyRecoveryRedirect(self.page_url(CreateOrganisationPage.SIGN_UP_ROUTER))
            raise SessionJourneyRecoveryRedirect(self.page_url(next_step))

        if answered_pages < pages.index(page):
            raise SessionJourneyRecoveryRedirect(self.page_url(CreateOrganisationPage.SIGN_UP_ROUTER))

    @classmethod
    def start(cls, *, collection_id: UUID, user: User) -> Self:
        return cls(
            collection_id=collection_id,
            needs_user_name=not user.name,
            can_share_email_domain=user.can_share_email_domain,
        )


class NamedCreateOrganisationSession(CreateOrganisationSession):
    organisation_type: SignUpOrganisationType
    name: str = Field(min_length=1)
    external_id: str = Field(min_length=1)


class CompleteCreateOrganisationSession(NamedCreateOrganisationSession):
    @model_validator(mode="after")
    def check_properties_that_can_be_skipped(self) -> Self:
        if self.first_incomplete_page != CreateOrganisationPage.CHECK_YOUR_ANSWERS:
            raise ValueError("All applicable organisation sign-up questions must be answered")
        return self


def start_public_sign_up(collection_id: UUID) -> None:
    """Begin (or restart) a public sign up, discarding any in-progress organisation set up.

    Only resets which metrics have already been emitted if this is a different collection to the one already in
    progress. Re-entering the same journey (eg. going back a page) shouldn't re-emit metrics it already has.
    """
    if session.get(SESSION_SIGNING_UP_FOR_COLLECTION_ID) != collection_id:
        session.pop(SESSION_EMITTED_PUBLIC_SIGN_UP_METRICS, None)
    session.pop(SESSION_CREATE_ORGANISATION, None)
    session.pop(SESSION_MATCHED_ORGANISATION, None)
    session[SESSION_SIGNING_UP_FOR_COLLECTION_ID] = collection_id


def clear_public_sign_up_session() -> UUID | None:
    session.pop(SESSION_CREATE_ORGANISATION, None)
    session.pop(SESSION_MATCHED_ORGANISATION, None)
    session.pop(SESSION_EMITTED_PUBLIC_SIGN_UP_METRICS, None)
    return session.pop(SESSION_SIGNING_UP_FOR_COLLECTION_ID, None)
