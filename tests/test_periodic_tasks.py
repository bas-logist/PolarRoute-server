"""Test periodic tasks managed by celery beat."""

from datetime import timedelta
from unittest import mock

import pytest
from django.utils import timezone
from django_celery_beat.models import IntervalSchedule, PeriodicTask
from django_celery_beat.schedulers import DatabaseScheduler

from polarrouteserver.celery import app
from polarrouteserver.route_api.tasks import my_test_task


def test_static_beat_schedule_is_valid():
    app.loader.import_default_modules()
    for name, entry in app.conf.beat_schedule.items():
        assert entry["task"] in app.tasks, f"{name}: {entry['task']} not registered"

@pytest.mark.django_db
def test_db_periodic_tasks_are_valid():
    # load fixture first if it defines periodic tasks, e.g.
    # call_command("loaddata", "your_fixture")
    app.loader.import_default_modules()
    for pt in PeriodicTask.objects.filter(enabled=True):
        assert pt.task in app.tasks, f"{pt.name}: {pt.task} not registered"

@pytest.mark.django_db
def test_scheduler_loads_task():
    every_10s = IntervalSchedule.objects.create(
        every=10, period=IntervalSchedule.SECONDS
    )
    PeriodicTask.objects.create(
        name="compat-test", task="route_api.tasks.my_test_task", interval=every_10s
    )
    scheduler = DatabaseScheduler(app=app)
    assert "compat-test" in scheduler.schedule

def test_due_task_is_sent(make_scheduler):
    every_10s = IntervalSchedule.objects.create(every=10, period=IntervalSchedule.SECONDS)
    PeriodicTask.objects.create(
        name="due-test",
        task="polarrouteserver.route_api.tasks.my_test_task",
        interval=every_10s,
        last_run_at=timezone.now() - timedelta(hours=1),
    )
    scheduler = make_scheduler()  # built after the rows exist, so it loads them
    with mock.patch.object(DatabaseScheduler, "apply_async") as sent:
        scheduler.tick()
    assert any(call.args[0].name == "due-test" for call in sent.call_args_list)


def test_roundtrip(celery_app, celery_worker):
    assert isinstance(my_test_task.delay().get(timeout=10), str)