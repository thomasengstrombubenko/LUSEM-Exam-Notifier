# Contributing

Contributions are welcome, including bug fixes, documentation improvements,
and enhancements that are useful to other users of the notifier.

## Getting started

1. Fork the repository and clone your fork.
2. Create and activate a virtual environment:

   ```sh
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. Install dependencies:

   ```sh
   python -m pip install -r requirements.txt
   ```

4. Copy `.env.example` to `.env` and configure your own calendar and Listmonk
   instance. Never commit `.env`, credentials, private calendar URLs, or other
   secrets.

## Making a change

- Keep changes focused and consistent with the existing code style.
- Update the README or other relevant documentation when behavior or setup
  changes.
- For changes to reminder parsing or scheduling, check the relevant calendar
  format and date behavior, including the configured timezone.
- Before opening a pull request, install the development dependencies and run
  the checks:

  ```sh
  python -m pip install -r requirements-dev.txt
  python -m py_compile main.py
  python -m pytest
  ```

- Pull requests are also checked by GitHub Actions on Python 3.10 and the
  latest stable Python version. The workflow installs the project and
  development dependencies, compiles `main.py`, and runs the test suite.
- If your change can be tested safely against a test calendar or a test
  Listmonk instance, include the steps and results. Do not send test campaigns
  to real subscribers.

## Pull requests

Open a pull request from your fork and fill in the template below. Link related
issues where applicable, describe any behavior changes or configuration
requirements, and be clear about what you tested. If a section does not apply,
write “N/A”.

### Pull request template

**Summary**

<!-- What does this change do? -->

**Motivation / context**

<!-- Why is this change needed? Link related issues if applicable. -->

**Changes made**

<!-- List the important changes and note any behavior or configuration changes. -->

**Testing**

- [ ] `python -m py_compile main.py`
- [ ] Other checks (describe below), or explain why additional testing was not applicable.

<!-- Include commands, test data, and results. Do not include credentials or private URLs. -->

**Checklist**

- [ ] The change is focused and documented where needed.
- [ ] No secrets or personal data are included.
- [ ] I have not sent test campaigns to real subscribers.
