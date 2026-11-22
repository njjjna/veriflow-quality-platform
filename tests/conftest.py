import pytest
from fastapi.testclient import TestClient
from app.main import create_app, PH
from app.models import User, Membership
from app.seed import new_id, make_project


@pytest.fixture()
def fx(tmp_path):
    app = create_app("sqlite:///" + str(tmp_path / "test.db"), mode="demo", upload_dir=str(tmp_path / "evidence"))
    user_ids = {}
    with app.state.SessionFactory() as db:
        for role in ("admin", "manager", "tester", "implementer", "approver", "viewer", "outsider"):
            u = User(id=new_id(), email=f"{role}@example.test", name=role,
                     password_hash=PH.hash(f"StrongPassword123!{role}"), is_admin=(role == "admin"))
            db.add(u)
            db.flush()
            user_ids[role] = u.id
        p = make_project(db, "Project Alpha", user_ids["admin"])
        q = make_project(db, "Project Beta", user_ids["admin"])
        for role in ("manager", "tester", "implementer", "approver", "viewer"):
            db.add(Membership(project_id=p.id, user_id=user_ids[role], role=role))
        db.add(Membership(project_id=q.id, user_id=user_ids["outsider"], role="manager"))
        db.commit()
        ids = (p.id, q.id)
    with TestClient(app) as client:
        yield {"app": app, "client": client, "ids": user_ids, "project": ids[0], "other_project": ids[1]}


def login(fx, role):
    client = fx["client"]
    r = client.post("/api/auth/login", json={"email": f"{role}@example.test", "password": f"StrongPassword123!{role}"})
    assert r.status_code == 200, r.text
    return {"X-CSRF-Token": r.json()["csrf_token"]}
