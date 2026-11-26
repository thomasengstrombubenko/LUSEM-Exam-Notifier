from dataclasses import dataclass
from datetime import datetime, timedelta
from dotenv import load_dotenv
from icalendar import Calendar, Event
from listmonk.models import Campaign
from pathlib import Path
from urllib.request import urlopen
from zoneinfo import ZoneInfo
import html, listmonk
import logging, sys, traceback
import os
import re

# Load settings from a .env file sitting next to this script. Using the script's
# own folder (not the current directory) means it also works when run by cron.
load_dotenv(Path(__file__).with_name(".env"))
# --- Environment variables ---

# ICS feed containing the university's exam calendar.
ICS_URL = os.environ.get("ICS_URL")

# Email links
GITHUB_URL = os.environ.get("GITHUB_URL", "")
LADOK_URL = os.environ.get("LADOK_URL", "")

# Listmonk variables
LISTMONK_USERNAME = os.environ.get("LISTMONK_USERNAME", "")
LISTMONK_PASSWORD = os.environ.get("LISTMONK_PASSWORD", "")
LISTMONK_URL = os.environ.get("LISTMONK_URL", "")
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "")

# Optional healthcheck endpoint; suffixes identify run, start, and failure pings.
HEALTHCHECK_URL = os.environ.get("HEALTHCHECK_URL", "")
LOG_DIR = Path(__file__).with_name("logs")
LOG_RETENTION_DAYS = 30
log = logging.getLogger("exam-notifier")

# Regular expressions
# Match an exam description line such as "Exam module, skriftlig tentamen".
EXAM_LINE_RE = re.compile(
    r"^(?P<module>.+?),[ \t]*(?P<kind>[^,.\n]*tentamen)[ \t]*$", re.I | re.M)
# Match course codes such as "SYSB23-26H" to associate exams with Listmonk lists.
CODE_RE = re.compile(r"^(?P<code>\w+?)-(?P<term>\d{2}[HV])\b", re.M)

# Timezone to follow
TIMEZONE = os.environ.get("TIMEZONE", "Europe/Stockholm")
TZ = ZoneInfo(TIMEZONE)

# --- Constants ---
MONTHS_SV = ["januari", "februari", "mars", "april", "maj", "juni", "juli", "augusti", "september", "oktober", "november", "december"]

# --- Classes ---
@dataclass(frozen=True) #frozen=True to make an exam hashable in a set
class Exam:
    course: str
    module: str
    kind: str
    start: datetime

# --- Exam functions ---


def parse_exam(ev: Event) -> Exam | None:
    """Convert an ICS event into an Exam, or ignore events that are not exams."""
    desc = str(ev.get("DESCRIPTION", ""))
    start = ev.decoded("DTSTART")
    m = EXAM_LINE_RE.search(desc)
    if not m or not isinstance(start, datetime):
        return None
    c = CODE_RE.search(desc)
    return Exam(
        course=c["code"] if c else str(ev.get("SUMMARY", "")),
        module=m["module"].strip(),
        kind=m["kind"].strip(),
        start=start.astimezone(TZ),
    )

def timed_exams(data: bytes) -> list[Exam]:
    """Parse the calendar, remove duplicate exams, and sort by exam start."""
    seen: set[Exam] = set()
    for ev in Calendar.from_ical(data).walk("VEVENT"):
        exam = parse_exam(ev)
        if exam:
            seen.add(exam)
    return sorted(seen, key=lambda e: e.start)

def registration_window(start, open_weeks=3, midway=2, close_weeks=1):
    """Calculate opening, midway reminder, and closing dates from the exam start."""
    return (
        start - timedelta(weeks=open_weeks),
        start - timedelta(weeks=midway),
        start - timedelta(weeks=close_weeks),
    )

# --- Email functions ---

def build_email(kind, exam, closes) -> tuple[str, str]:
    """Build the subject and HTML body for one of the registration stages."""
    if kind == "opens":
        subject = f"Anmälan öppen för tentamen i {exam.module}"
        body = f"""
    <p>Från och med idag kan du anmäla dig till tentamen i {html.escape(exam.module)}.
    Sista anmälningsdag är: <strong>{swedish_date(closes)}</strong>.</p>
    <p>Anmäl dig i <a href="{LADOK_URL}">Ladok</a></p>
    <p>Vill du se/bidra till källkoden för det här scriptet? Den finns här:
    <a href="{GITHUB_URL}">GitHub</a></p>
    <p>OBS: Alla datum är uträknade, dubbelkolla Ladok för korrekta uppgifter.</p>
    """
        return subject, body
    
    elif kind == "midway":
        subject = f"Anmälan för tentamen i {exam.module} stänger om en vecka"
        body=f"""
<p>Anmälan till tentamen i {html.escape(exam.module)} stänger om en vecka.
Sista anmälningsdag är: <strong>{swedish_date(closes)}</strong>.</p>
<p>Anmäl dig i <a href="{LADOK_URL}">Ladok</a></p>
<p>Vill du se/bidra till källkoden för det här scriptet? Den finns här:
<a href="{GITHUB_URL}">GitHub</a></p>
<p>OBS: Alla datum är uträknade, dubbelkolla Ladok för korrekta uppgifter.</p>
"""
        return subject, body
    
    elif kind == "closes":
        subject = f"Anmälan för tentamen i {exam.module} stänger idag"
        body=f"""
<p>Idag stänger anmälan för tentamen i {html.escape(exam.module)}, glöm inte att anmäla dig.</p>
<p>Anmäl dig i <a href="{LADOK_URL}">Ladok</a></p>
<p>Vill du se/bidra till källkoden för det här scriptet? Den finns här:
<a href="{GITHUB_URL}">GitHub</a></p>
<p>OBS: Alla datum är uträknade, dubbelkolla Ladok för korrekta uppgifter.</p>
"""        
        return subject, body

def send_reminder(kind, exam, list_id, existing_names, closes):
    """Create a campaign unless this exact reminder was already scheduled."""
    # Only visible in Listmonk, not visible to list subscribers
    name = f"{kind}|{exam.course}|{exam.module}|{exam.start.date()}"
    if name in existing_names:
        return
    subject, body = build_email(kind, exam, closes)
    campaign = listmonk.create_campaign(
        name=name, subject=subject, body=body, content_type="html",
        list_ids={list_id}, from_email=SENDER_EMAIL
    )
    return campaign

# --- Logging ---

def setup_logging(now: datetime) -> None:
    """One log file per day (logs/2026-11-26.log for example). Runs on the same day append to it."""
    LOG_DIR.mkdir(exist_ok=True)
    log.setLevel(os.environ.get("LOG_LEVEL", "INFO").upper())
    formatter = logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", "%Y-%m-%d %H:%M:%S")
    # Keep timestamps in the configured timezone instead of the machine timezone.
    formatter.converter = lambda ts: datetime.fromtimestamp(ts, TZ).timetuple()  # timestamps in TZ
    for handler in (logging.FileHandler(LOG_DIR / f"{now:%Y-%m-%d}.log", encoding="utf-8"),
                    logging.StreamHandler()):
        handler.setFormatter(formatter)
        log.addHandler(handler)

def prune_old_logs(days: int) -> None:
    """Delete log files not modified for `days` days."""
    cutoff = datetime.now(TZ) - timedelta(days=days)
    for f in LOG_DIR.glob("*.log"):
        if datetime.fromtimestamp(f.stat().st_mtime, TZ) < cutoff:
            f.unlink()
            log.info("Deleted old log file %s", f.name)

def ping_healthcheck(suffix: str = "", message: str = "") -> None:
    """suffix: '' = success, '/start', '/fail'. A failed ping must never break the script."""
    if not HEALTHCHECK_URL:
        return
    try:
        data = message.encode("utf-8")[:10_000] if message else None    # giving data makes it a POST
        urlopen(HEALTHCHECK_URL + suffix, data=data, timeout=10)
    except Exception as e:
        log.warning("Healthcheck ping %r failed: %s", suffix or "success", e)

# --- Miscellaneous / helper functions ---
def swedish_date(d) -> str:
    """Convert a datetime to Swedish long date form, e.g. 1 januari 2024."""
    return f"{d.day} {MONTHS_SV[d.month - 1]} {d.year}"

def run() -> str:
    """Refresh the calendar and start only reminders due on the current date."""
    today = datetime.now(TZ)

    listmonk.set_url_base(LISTMONK_URL)
    if not listmonk.login(LISTMONK_USERNAME, LISTMONK_PASSWORD): # login() returns False silently
        raise RuntimeError("listmonk login failed (check the URL scheme and the API user/token)")

    exams = timed_exams(urlopen(ICS_URL, timeout=20).read())
    if not exams:
        raise RuntimeError("No exams parsed from the feed. Has the format changed?")
    upcoming = [e for e in exams if e.start > today]
    log.info("Feed: %d exams, %d upcoming", len(exams), len(upcoming))

    lists = {l.name: l.id for l in listmonk.lists()}
    existing = {c.name for c in listmonk.campaigns()}

    missing = {e.course for e in upcoming if e.course not in lists}
    for course in sorted(missing):
        log.warning("No listmonk list for course %s", course)

    started = 0
    for exam in upcoming:
        list_id = lists.get(exam.course)
        if list_id is None:
            continue
        opens, mid, closes = registration_window(exam.start)
        # A reminder is actionable only when one of its calculated dates is today.
        for kind, day in (("opens", opens), ("midway", mid), ("closes", closes)):
            if day.date() != today.date():
                continue
            campaign = send_reminder(kind, exam, list_id, existing, closes)
            if campaign is None:
                continue
            listmonk.start_campaign(campaign.id)
            existing.add(campaign.name)
            started += 1
            log.info("Started campaign %s (id=%d, list=%d)", campaign.name, campaign.id, list_id)

    return f"{len(exams)} exams, {started} campaigns started"

def main() -> None:
    setup_logging(datetime.now(TZ))
    prune_old_logs(LOG_RETENTION_DAYS)
    log.info("=== Run started ===")
    ping_healthcheck("/start")
    try:
        summary = run()
    except Exception:
        log.exception("Run failed")                       # message plus traceback
        ping_healthcheck("/fail", traceback.format_exc())
        sys.exit(1)                                       # non-zero exit code, so cron sees the failure
    log.info("=== Run finished: %s ===", summary)
    ping_healthcheck("", summary)
    
if __name__ == "__main__":
    main()
