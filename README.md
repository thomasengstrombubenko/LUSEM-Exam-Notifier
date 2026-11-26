# LUSEM Exam Notifier

A small scheduled Python script that reads exam events from an iCalendar (ICS)
feed and starts Listmonk email campaigns with reminders about exam registration.
The messages are sent on the calculated registration opening date, one week
before registration closes, and on the registration closing date. Dates use the
configured timezone (Europe/Stockholm by default).

## Use and contributions

You are welcome to fork this repository and run your own instance of the
notifier. Configure it with your own calendar feed and Listmonk account, and
verify the resulting reminders before relying on them. Contributions are also
welcome; see [CONTRIBUTING.md](CONTRIBUTING.md) for setup guidance and the
expected pull request details.

## Requirements

- Python 3.10 or later
- A Listmonk instance with an API account and one list per course code found in
  the calendar feed
- An ICS feed whose event descriptions contain exam information in a format
  recognized by the script

## Setup

1. Create and activate a virtual environment:

   ```sh
   python3 -m venv .venv
   source .venv/bin/activate
   ```

   On Windows, activate it with `.venv\Scripts\activate`.

2. Install the dependencies:

   ```sh
   python -m pip install -r requirements.txt
   ```

3. Copy `.env.example` to `.env` and set the feed URL, Listmonk credentials,
   sender email address, and email links. Keep `.env` private; it is ignored by
   Git.

4. Ensure Listmonk has a list for each course code used by the ICS feed. The
   course code is used to find the list that receives the reminder. The name of the list must match the course code exactly.

## Run

Run the notifier with:

```sh
python main.py
```

The script is intended to be run regularly by a scheduler such as cron or
systemd. It checks the feed each time it runs and starts campaigns only when a
reminder date matches the current date. Campaign names prevent the same
reminder from being started again on subsequent runs.

Logs are written to `logs/` and old log files are removed after 30 days.
`HEALTHCHECK_URL` is optional; when set, the script sends start, success, and
failure pings to that endpoint.

## Configuration

See `.env.example` for all supported environment variables. `ICS_URL`,
`LISTMONK_URL`, `LISTMONK_USERNAME`, `LISTMONK_PASSWORD`, and `SENDER_EMAIL`
must be configured. `TIMEZONE` defaults to `Europe/Stockholm`, `LOG_LEVEL`
defaults to `INFO`, and the other link and healthcheck settings are optional.

## Calendar format

Only events whose description contains an exam line ending in `tentamen` are
used. The script looks for a course code at the beginning of a description
line (for example, `SYSB23-26H`) and uses the event summary if no code is
found. Verify the calendar feed and the resulting campaign dates before
relying on them; the reminder dates are calculated from the event start date.

