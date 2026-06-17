from flask import url_for

from app.common.data.types import CollectionStatusEnum, GrantStatusEnum


class TestListActiveGrants:
    endpoint = "deliver_grant_funding.api.list_active_grants"

    def test_returns_403_without_auth(self, anonymous_client):
        response = anonymous_client.get(url_for(self.endpoint))
        assert response.status_code == 403

    def test_returns_403_with_wrong_token(self, anonymous_client):
        response = anonymous_client.get(
            url_for(self.endpoint),
            headers={"Authorization": "Bearer wrong-token"},
        )
        assert response.status_code == 403

    def test_returns_empty_list_when_no_matching_grants(self, anonymous_client):
        response = anonymous_client.get(
            url_for(self.endpoint),
            headers={"Authorization": "Bearer insecure-local-token"},
        )
        assert response.status_code == 200
        assert response.json == {"grants": [{"id": "not-listed", "label": "An other grant not listed"}]}

    def test_returns_grant_with_open_collection(self, anonymous_client, factories):
        grant = factories.grant.create(status=GrantStatusEnum.LIVE, name="Open Grant", code="OG-001")
        factories.collection.create(grant=grant, status=CollectionStatusEnum.OPEN)

        response = anonymous_client.get(
            url_for(self.endpoint),
            headers={"Authorization": "Bearer insecure-local-token"},
        )
        assert response.status_code == 200
        assert response.json == {
            "grants": [
                {"id": "OG-001", "label": "Open Grant"},
                {"id": "not-listed", "label": "An other grant not listed"},
            ]
        }

    def test_returns_grant_with_closed_collection(self, anonymous_client, factories):
        grant = factories.grant.create(status=GrantStatusEnum.LIVE, name="Closed Grant", code="CG-001")
        factories.collection.create(grant=grant, status=CollectionStatusEnum.CLOSED)

        response = anonymous_client.get(
            url_for(self.endpoint),
            headers={"Authorization": "Bearer insecure-local-token"},
        )
        assert response.status_code == 200
        assert response.json == {
            "grants": [
                {"id": "CG-001", "label": "Closed Grant"},
                {"id": "not-listed", "label": "An other grant not listed"},
            ]
        }

    def test_excludes_scheduled_collection(self, anonymous_client, factories):
        grant = factories.grant.create(status=GrantStatusEnum.LIVE, name="Scheduled Grant", code="SG-001")
        factories.collection.create(grant=grant, status=CollectionStatusEnum.SCHEDULED)

        response = anonymous_client.get(
            url_for(self.endpoint),
            headers={"Authorization": "Bearer insecure-local-token"},
        )
        assert response.status_code == 200
        assert response.json == {"grants": [{"id": "not-listed", "label": "An other grant not listed"}]}

    def test_excludes_draft_grant(self, anonymous_client, factories):
        grant = factories.grant.create(status=GrantStatusEnum.DRAFT, name="Draft Grant", code="DG-001")
        factories.collection.create(grant=grant, status=CollectionStatusEnum.OPEN)

        response = anonymous_client.get(
            url_for(self.endpoint),
            headers={"Authorization": "Bearer insecure-local-token"},
        )
        assert response.status_code == 200
        assert response.json == {"grants": [{"id": "not-listed", "label": "An other grant not listed"}]}

    def test_excludes_grant_with_only_draft_collection(self, anonymous_client, factories):
        grant = factories.grant.create(status=GrantStatusEnum.LIVE, name="Draft Coll Grant", code="DC-001")
        factories.collection.create(grant=grant, status=CollectionStatusEnum.DRAFT)

        response = anonymous_client.get(
            url_for(self.endpoint),
            headers={"Authorization": "Bearer insecure-local-token"},
        )
        assert response.status_code == 200
        assert response.json == {"grants": [{"id": "not-listed", "label": "An other grant not listed"}]}
