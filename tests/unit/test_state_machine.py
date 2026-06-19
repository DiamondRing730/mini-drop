"""Unit tests for the task state machine (the spec's most safety-critical piece)."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.db import Base
from app.enums import TaskStatus
from app.state import InvalidTransition, record_initial, transition


@pytest.fixture()
def session():
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    yield s
    s.close()


def _new_task(session) -> models.Task:
    task = models.Task(tid="t1", target_pid=1, profiler_type="pyspy",
                       status=TaskStatus.PENDING.value, status_reason="created")
    session.add(task)
    session.flush()
    record_initial(session, task, "task created by user")
    session.commit()
    return task


def test_full_happy_path_records_every_edge(session):
    task = _new_task(session)
    transition(session, task, "RUNNING", "claimed by agent a1")
    transition(session, task, "UPLOADING", "collection finished")
    transition(session, task, "DONE", "artifact stored")
    session.commit()

    assert task.status == "DONE"
    assert task.begin_time is not None and task.end_time is not None
    rows = session.query(models.TaskStateTransition).order_by(models.TaskStateTransition.id).all()
    assert [r.to_status for r in rows] == ["PENDING", "RUNNING", "UPLOADING", "DONE"]
    # Every transition carries a non-empty reason (the spec's hard requirement).
    assert all(r.reason for r in rows)


def test_illegal_transition_is_rejected(session):
    task = _new_task(session)
    with pytest.raises(InvalidTransition):
        transition(session, task, "DONE", "skip ahead")  # PENDING -> DONE is illegal


def test_can_fail_from_running(session):
    task = _new_task(session)
    transition(session, task, "RUNNING", "claimed")
    transition(session, task, "FAILED", "agent offline")
    assert task.status == "FAILED"
    assert task.status_reason == "agent offline"


def test_no_transition_out_of_terminal(session):
    task = _new_task(session)
    transition(session, task, "FAILED", "bad pid")
    with pytest.raises(InvalidTransition):
        transition(session, task, "RUNNING", "retry in place")
