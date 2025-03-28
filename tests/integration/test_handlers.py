from flask import g
from sqlalchemy import select

from app.common.data.models import Grant


# this will likely be split out into different blueprints/ endpoints
def test_create_grant_handler(client, db):
    client.get("/grant")
    response = client.post(
        "/grant",
        data={"name": "My test grant", "csrf_token": g.csrf_token},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    # assert the grant is in the database and has been committed to the dataabse
    db.session.scalars(select(Grant).where(Grant.name == "My test grant")).one()
    assert response.status_code == 200
