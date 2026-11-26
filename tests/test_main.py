from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from icalendar import Calendar, Event

import main


def make_event(description: str, start: date | datetime, summary: str = "Course summary") -> Event:
    event = Event()
    event.add("summary", summary)
    event.add("description", description)
    event.add("dtstart", start)
    return event


def make_calendar(*events: Event) -> bytes:
    calendar = Calendar()
    for event in events:
        calendar.add_component(event)
    return calendar.to_ical()


def test_parse_exam_extracts_course_module_kind_and_local_start():
    start = datetime(2026, 6, 1, 9, tzinfo=timezone.utc)
    event = make_event(
        "SYSB23-26H\nModule A, skriftlig tentamen",
        start,
    )

    exam = main.parse_exam(event)

    assert exam == main.Exam(
        course="SYSB23",
        module="Module A",
        kind="skriftlig tentamen",
        start=start.astimezone(main.TZ),
    )


def test_parse_exam_uses_summary_when_description_has_no_course_code():
    event = make_event(
        "Module B, muntlig tentamen",
        datetime(2026, 6, 1, 9, tzinfo=timezone.utc),
        summary="Alternative course name",
    )

    exam = main.parse_exam(event)

    assert exam is not None
    assert exam.course == "Alternative course name"


@pytest.mark.parametrize(
    "event",
    [
        make_event(
            "Module A, föreläsning",
            datetime(2026, 6, 1, 9, tzinfo=timezone.utc),
        ),
        make_event("Module A, skriftlig tentamen", datetime(2026, 6, 1).date()),
    ],
)
def test_parse_exam_ignores_non_exams_and_all_day_events(event):
    assert main.parse_exam(event) is None


def test_timed_exams_deduplicates_and_sorts_by_start():
    later = make_event(
        "SYSB23-26H\nModule B, tentamen",
        datetime(2026, 6, 2, 9, tzinfo=timezone.utc),
    )
    earlier = make_event(
        "SYSB23-26H\nModule A, tentamen",
        datetime(2026, 6, 1, 9, tzinfo=timezone.utc),
    )

    exams = main.timed_exams(make_calendar(later, earlier, later))

    assert [exam.module for exam in exams] == ["Module A", "Module B"]


def test_registration_window_uses_three_two_and_one_week_offsets():
    start = datetime(2026, 6, 1, 9, tzinfo=main.TZ)

    assert main.registration_window(start) == (
        start - timedelta(weeks=3),
        start - timedelta(weeks=2),
        start - timedelta(weeks=1),
    )


@pytest.mark.parametrize(
    ("kind", "subject_text", "includes_close_date"),
    [
        ("opens", "Anmälan öppen", True),
        ("midway", "stänger om en vecka", True),
        ("closes", "stänger idag", False),
    ],
)
def test_build_email_escapes_module_name_and_formats_close_date(
    kind, subject_text, includes_close_date
):
    exam = main.Exam(
        course="SYSB23",
        module="<Module & A>",
        kind="tentamen",
        start=datetime(2026, 6, 1, 9, tzinfo=main.TZ),
    )
    closes = datetime(2026, 5, 25, 9, tzinfo=main.TZ)

    subject, body = main.build_email(kind, exam, closes)

    assert subject_text in subject
    assert "&lt;Module &amp; A&gt;" in body
    assert "<Module & A>" not in body
    assert ("25 maj 2026" in body) is includes_close_date


def test_send_reminder_creates_named_campaign(monkeypatch):
    exam = main.Exam(
        course="SYSB23",
        module="Module A",
        kind="tentamen",
        start=datetime(2026, 6, 1, 9, tzinfo=main.TZ),
    )
    closes = datetime(2026, 5, 25, 9, tzinfo=main.TZ)
    campaign = SimpleNamespace(id=42, name="opens|SYSB23|Module A|2026-06-01")
    create_campaign = Mock(return_value=campaign)
    monkeypatch.setattr(main.listmonk, "create_campaign", create_campaign)

    result = main.send_reminder("opens", exam, 7, set(), closes)

    assert result is campaign
    create_campaign.assert_called_once()
    kwargs = create_campaign.call_args.kwargs
    assert kwargs["name"] == campaign.name
    assert kwargs["list_ids"] == {7}
    assert kwargs["from_email"] == main.SENDER_EMAIL
    assert kwargs["content_type"] == "html"


def test_send_reminder_skips_existing_campaign(monkeypatch):
    exam = main.Exam(
        course="SYSB23",
        module="Module A",
        kind="tentamen",
        start=datetime(2026, 6, 1, 9, tzinfo=main.TZ),
    )
    name = f"opens|{exam.course}|{exam.module}|{exam.start.date()}"

    def unexpected_campaign_creation(**kwargs):
        pytest.fail("an existing campaign must not be recreated")

    monkeypatch.setattr(main.listmonk, "create_campaign", unexpected_campaign_creation)

    assert main.send_reminder("opens", exam, 7, {name}, exam.start) is None
