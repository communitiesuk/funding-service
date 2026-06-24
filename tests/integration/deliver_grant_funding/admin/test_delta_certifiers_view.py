import datetime
import zipfile
from io import BytesIO
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from app.common.data.types import OrganisationModeEnum, RoleEnum

FIXTURE_CSV = Path(__file__).resolve().parents[3] / "fixtures" / "s151-data-sample.csv"


@pytest.fixture
def delta_csv_path(app, monkeypatch):
    monkeypatch.setitem(app.config, "DELTA_S151_CSV_PATH_OR_KEY", str(FIXTURE_CSV))
    return FIXTURE_CSV


@pytest.fixture
def delta_test_data(factories, db_session):
    # The data here lines up with the FIXTURE_CSV data
    org_match = factories.organisation.create(external_id="E06000010", name="Matching Council")
    org_diff = factories.organisation.create(external_id="E06000011", name="Different Council")
    factories.organisation.create(external_id="E06000012", name="Empty Council")
    org_delegated = factories.organisation.create(external_id="E06000013", name="Delegated Council")

    match_certifier = factories.user.create(email="matching@example.gov.uk", name="Matt Match")
    match_deputy = factories.user.create(email="deputy@example.gov.uk", name="Daphne Deputy")
    local_only_certifier = factories.user.create(email="local-only@example.gov.uk", name="Lily Local")

    factories.user_role.create(user=match_certifier, permissions=[RoleEnum.CERTIFIER], organisation=org_match)
    factories.user_role.create(user=match_deputy, permissions=[RoleEnum.CERTIFIER], organisation=org_match)
    factories.user_role.create(user=local_only_certifier, permissions=[RoleEnum.CERTIFIER], organisation=org_diff)

    grant = factories.grant.create(name="Alpha grant")
    delegated_user = factories.user.create(email="delegated@example.gov.uk", name="Doris Delegated")
    fs_only_delegated_user = factories.user.create(email="fs-only-delegated@example.gov.uk", name="Fred FS-Only")
    factories.user_role.create(
        user=delegated_user, permissions=[RoleEnum.CERTIFIER], grant=grant, organisation=org_delegated
    )
    factories.user_role.create(
        user=fs_only_delegated_user, permissions=[RoleEnum.CERTIFIER], grant=grant, organisation=org_delegated
    )

    test_org = factories.organisation.create(
        external_id="E06000014", name="Test Mode Council", mode=OrganisationModeEnum.TEST
    )
    test_org_user = factories.user.create(email="test-org-user@example.gov.uk", name="Tina Test")
    factories.user_role.create(user=test_org_user, permissions=[RoleEnum.CERTIFIER], grant=grant, organisation=test_org)


@pytest.fixture
def page_soup(authenticated_platform_grant_lifecycle_manager_client, delta_csv_path, delta_test_data):
    response = authenticated_platform_grant_lifecycle_manager_client.get("/deliver/admin/delta-certifiers/")
    assert response.status_code == 200
    return BeautifulSoup(response.data, "html.parser")


def _rows_by_org(soup, panel_selector):
    panel = soup.select_one(panel_selector)
    assert panel is not None, f"Panel {panel_selector!r} not found"
    clusters: dict[str, list] = {}
    current_org: str | None = None
    for row in panel.select("tbody tr"):
        th = row.find("th", attrs={"scope": "row"})
        if th:
            current_org = th.get_text(strip=True)
            clusters[current_org] = []
        assert current_org is not None, "First row in a certifiers table must have a row-header"
        clusters[current_org].append(row)
    return clusters


class TestDeltaCertifiersAdminAccess:
    @pytest.mark.parametrize(
        "client_fixture, expected_code",
        [
            ("authenticated_platform_admin_client", 200),
            ("authenticated_platform_grant_lifecycle_manager_client", 200),
            ("authenticated_platform_data_analyst_client", 403),
            ("authenticated_platform_member_client", 403),
            ("authenticated_grant_admin_client", 403),
            ("authenticated_grant_member_client", 403),
            ("authenticated_no_role_client", 403),
            ("anonymous_client", 302),
        ],
    )
    def test_page_access(self, client_fixture, expected_code, request, delta_csv_path):
        client = request.getfixturevalue(client_fixture)
        response = client.get("/deliver/admin/delta-certifiers/")
        assert response.status_code == expected_code


class TestCertifiersTable:
    expected_orgs = {"Delegated Council", "Different Council", "Empty Council", "Matching Council"}

    def test_lists_every_live_grant_recipient_org(self, page_soup):
        rows = _rows_by_org(page_soup, "#certifiers-by-organisation")
        assert set(rows) == self.expected_orgs

    def test_matching_council_in_sync_with_s151_before_deputy(self, page_soup):
        cells = _rows_by_org(page_soup, "#certifiers-by-organisation")["Matching Council"][0].find_all("td")
        delta_cell, fs_cell, status_cell = (c.get_text(" ", strip=True) for c in cells)

        assert "OK" in status_cell
        assert delta_cell.index("matching@example.gov.uk") < delta_cell.index("deputy@example.gov.uk")
        assert "matching@example.gov.uk" in fs_cell
        assert "deputy@example.gov.uk" in fs_cell

    def test_different_council_shows_mismatch_with_one_email_per_side(self, page_soup):
        cells = _rows_by_org(page_soup, "#certifiers-by-organisation")["Different Council"][0].find_all("td")
        delta_cell, fs_cell, status_cell = (c.get_text(" ", strip=True) for c in cells)

        assert "Out of sync" in status_cell
        assert "delta-only@example.gov.uk" in delta_cell
        assert "local-only@example.gov.uk" in fs_cell

    def test_empty_council_shows_mismatch_with_no_funding_service_certifiers(self, page_soup):
        cells = _rows_by_org(page_soup, "#certifiers-by-organisation")["Empty Council"][0].find_all("td")
        delta_cell, fs_cell, status_cell = (c.get_text(" ", strip=True) for c in cells)

        assert "Out of sync" in status_cell
        assert "empty-delta-only@example.gov.uk" in delta_cell
        assert fs_cell == "None"

    def test_delegated_council_in_sync_with_no_org_level_certifiers(self, page_soup):
        cells = _rows_by_org(page_soup, "#certifiers-by-organisation")["Delegated Council"][0].find_all("td")
        delta_cell, fs_cell, status_cell = (c.get_text(" ", strip=True) for c in cells)

        assert "OK" in status_cell
        assert delta_cell == "None"
        assert fs_cell == "None"


class TestDelegatedCertifiersTable:
    expected_orgs = {"Delegated Council", "Different Council", "Empty Council", "Matching Council"}

    def test_lists_every_live_grant_recipient_org(self, page_soup):
        rows = _rows_by_org(page_soup, "#delegated-certifiers")
        assert set(rows) == self.expected_orgs

    def test_delegated_council_clusters_three_certifiers_under_one_org_header(self, page_soup):
        delegated = _rows_by_org(page_soup, "#delegated-certifiers")["Delegated Council"]
        assert len(delegated) == 3
        assert delegated[0].find("th").get("rowspan") == "3"

    def test_delta_only_certifier_shows_none_for_funding_service_grants(self, page_soup):
        delegated = _rows_by_org(page_soup, "#delegated-certifiers")["Delegated Council"]
        cells = delegated[0].find_all("td")
        certifier_cell, groups_cell, grants_cell = (c.get_text(" ", strip=True) for c in cells)

        assert "Dirk Deputy" in certifier_cell
        assert "delegated-deputy@example.gov.uk" in certifier_cell
        assert "grant-alpha" in groups_cell
        assert grants_cell == "None"

    def test_certifier_in_both_systems_shows_groups_and_grants(self, page_soup):
        delegated = _rows_by_org(page_soup, "#delegated-certifiers")["Delegated Council"]
        cells = delegated[1].find_all("td")
        certifier_cell, groups_cell, grants_cell = (c.get_text(" ", strip=True) for c in cells)

        assert "Doris Delegated" in certifier_cell
        assert "delegated@example.gov.uk" in certifier_cell
        assert "grant-alpha" in groups_cell
        assert "grant-beta" in groups_cell
        assert "Alpha grant" in grants_cell

    def test_funding_service_only_certifier_shows_none_for_delta_groups(self, page_soup):
        delegated = _rows_by_org(page_soup, "#delegated-certifiers")["Delegated Council"]
        cells = delegated[2].find_all("td")
        certifier_cell, groups_cell, grants_cell = (c.get_text(" ", strip=True) for c in cells)

        assert "Fred FS-Only" in certifier_cell
        assert "fs-only-delegated@example.gov.uk" in certifier_cell
        assert groups_cell == "None"
        assert "Alpha grant" in grants_cell

    @pytest.mark.parametrize("org_name", ["Different Council", "Empty Council", "Matching Council"])
    def test_orgs_without_delegated_entries_show_single_none_row(self, page_soup, org_name):
        rows = _rows_by_org(page_soup, "#delegated-certifiers")[org_name]
        assert len(rows) == 1
        cells = rows[0].find_all("td")
        assert [c.get_text(strip=True) for c in cells] == ["None", "None", "None"]


class TestExcludedData:
    @pytest.mark.parametrize(
        "excluded",
        [
            "test-org-user@example.gov.uk",
            "Test Mode Council",
            "not-approved@example.gov.uk",
            "not-enabled@example.gov.uk",
            "other@example.gov.uk",
        ],
    )
    def test_excluded_from_page(self, page_soup, excluded):
        assert excluded not in page_soup.get_text(" ", strip=True)


class TestCsvLoadFailure:
    def test_missing_csv_surfaces_to_caller(
        self, authenticated_platform_grant_lifecycle_manager_client, app, monkeypatch
    ):
        monkeypatch.setitem(app.config, "DELTA_S151_CSV_PATH_OR_KEY", "/nonexistent/path/s151-data.csv")
        with pytest.raises(FileNotFoundError):
            authenticated_platform_grant_lifecycle_manager_client.get("/deliver/admin/delta-certifiers/")


class TestS3ZipSource:
    def test_s3_uri_downloads_and_unzips_csv(
        self, authenticated_platform_grant_lifecycle_manager_client, app, monkeypatch, mocker, factories, db_session
    ):
        factories.organisation.create(external_id="E06000013", name="Delegated Council")

        zip_bytes = BytesIO()
        with zipfile.ZipFile(zip_bytes, mode="w") as archive:
            archive.write(FIXTURE_CSV, arcname="s151-data.csv")

        last_modified = datetime.datetime(2026, 5, 26, 9, 30, tzinfo=datetime.UTC)
        s3_client = mocker.MagicMock()
        s3_client.get_object.return_value = {
            "Body": BytesIO(zip_bytes.getvalue()),
            "LastModified": last_modified,
        }
        boto3_client_mock = mocker.patch("app.deliver_grant_funding.admin.views.boto3.client", return_value=s3_client)
        monkeypatch.setitem(app.config, "DELTA_S151_CSV_PATH_OR_KEY", "s3://delta-exports/s151/s151-data.zip")

        response = authenticated_platform_grant_lifecycle_manager_client.get("/deliver/admin/delta-certifiers/")

        assert response.status_code == 200
        boto3_client_mock.assert_called_once_with("s3")
        s3_client.get_object.assert_called_once_with(Bucket="delta-exports", Key="s151/s151-data.zip")
        body = response.get_data(as_text=True)
        assert "Delegated Council" in body
        assert "delegated@example.gov.uk" in body
        assert "Delta export was last updated on 26 May 2026 at 10:30am" in body
