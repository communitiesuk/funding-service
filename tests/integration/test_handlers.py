from flask import g, url_for
from sqlalchemy import select

from app.common.data.models import Grant


# this will likely be split out into different blueprints/ endpoints
def test_create_grant_handler(client, db, db_session):
    url = url_for("platform.add_grant")
    client.get(url)
    response = client.post(
        url,
        data={"name": "My test grant", "csrf_token": g.csrf_token},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    # assert the grant is in the database and has been committed to the dataabse
    db.sessionmaker().scalars(select(Grant).where(Grant.name == "My test grant")).one()
    assert response.status_code == 302
