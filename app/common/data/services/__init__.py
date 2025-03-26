from app.common.data.models import Grant
from app.extensions import db_request_session

def create_grant(name: str) -> None:
    session = db_request_session.request_session
    grant = Grant(name=name)
    session.add(grant)
    session.flush() # general principle of always flushing after adding something (how to encourage TBD)
