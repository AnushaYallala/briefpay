from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import sessionmaker

from app.models import Job
from app.services import jobs


@pytest.fixture()
def factory(db):
    return sessionmaker(bind=db.get_bind(), expire_on_commit=False)


@pytest.fixture(autouse=True)
def clean_handlers():
    saved = dict(jobs.HANDLERS)
    jobs.HANDLERS.clear()
    yield
    jobs.HANDLERS.clear()
    jobs.HANDLERS.update(saved)


def make(factory, type_="T", payload=None, **kw):
    s = factory()
    j = jobs.enqueue(s, type_, payload or {}, **kw)
    s.commit()
    jid = j.id
    s.close()
    return jid


def get(factory, jid):
    s = factory()
    try:
        return s.get(Job, jid)
    finally:
        s.close()


def test_job_runs_and_stores_result(factory):
    @jobs.register("T")
    def h(db, payload):
        return {"echo": payload["x"]}

    jid = make(factory, payload={"x": 7})
    assert jobs.run_one(factory) is True
    j = get(factory, jid)
    assert (j.state, j.result_json, j.last_error, j.attempts) == ("DONE", {"echo": 7}, None, 1)
    assert jobs.run_one(factory) is False  # nothing left


def test_failing_job_retries_with_backoff_then_fails(factory):
    jobs.register("T")(lambda db, p: (_ for _ in ()).throw(ValueError("boom")))
    jid = make(factory)
    for attempt in (1, 2):
        assert jobs.run_one(factory)
        j = get(factory, jid)
        assert j.state == "QUEUED" and j.attempts == attempt and "boom" in j.last_error
        assert j.run_after.replace(tzinfo=timezone.utc) > datetime.now(timezone.utc)
        assert jobs.run_one(factory) is False  # not due yet
        s = factory()
        s.get(Job, jid).run_after = datetime.now(timezone.utc) - timedelta(seconds=1)
        s.commit()
        s.close()
    assert jobs.run_one(factory)
    j = get(factory, jid)
    assert (j.state, j.attempts) == ("FAILED", jobs.MAX_ATTEMPTS)
    assert jobs.run_one(factory) is False


def test_failed_handler_work_is_rolled_back(factory):
    from app.models import User

    def h(db, p):
        db.add(User(email="x@y.z", display_name="X"))
        db.flush()
        raise RuntimeError("after write")

    jobs.register("T")(h)
    make(factory)
    jobs.run_one(factory)
    s = factory()
    assert s.query(User).count() == 0
    s.close()


def test_future_job_waits_and_unknown_type_fails(factory):
    jobs.register("T")(lambda db, p: None)
    make(factory, run_after=datetime.now(timezone.utc) + timedelta(hours=1))
    assert jobs.run_one(factory) is False
    jid = make(factory, type_="NOPE")
    s = factory()
    s.query(Job).filter(Job.type == "T").delete()
    s.commit()
    s.close()
    jobs.run_one(factory)
    assert "no handler" in get(factory, jid).last_error


def test_jobs_run_in_order(factory):
    seen = []
    jobs.register("T")(lambda db, p: seen.append(p["n"]))
    for n in (1, 2, 3):
        make(factory, payload={"n": n})
    while jobs.run_one(factory):
        pass
    assert seen == [1, 2, 3]


def test_running_jobs_are_requeued_after_a_crash(factory):
    jid = make(factory)
    s = factory()
    s.get(Job, jid).state = "RUNNING"
    s.commit()
    s.close()
    assert jobs.recover_stuck(factory) == 1
    assert get(factory, jid).state == "QUEUED"


def test_jobs_endpoint(client, db):
    j = jobs.enqueue(db, "T", {})
    j.state, j.result_json = "DONE", {"ok": True}
    db.commit()
    r = client.get(f"/api/jobs/{j.id}")
    assert r.status_code == 200
    assert r.json() == {"state": "DONE", "result": {"ok": True}, "error": None, "attempts": 0}
    r = client.get("/api/jobs/9999")
    assert r.status_code == 404 and r.json()["error"]["code"] == "JOB_NOT_FOUND"
