"""`run` finds and qualifies leads, and sends only when it is explicitly told to.

What the sender does with a cold deal — the opener, two follow-ups, the end — is the
sender's to test, and it does (`openoutsend/tests/test_cold_sequence.py`). This side owns
only the hand-off: `find --json` into a buffer, the sender's own ingest, then `send` — and,
in this fork, the guard in front of it: **by default `run` cannot send.**
"""
import json
from unittest.mock import patch

import pytest

from openoutreach import __main__ as cli

LEAD = {"lead_id": "lead-1", "email": "sam@example.com", "first_name": "Sam"}

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _sending_starts_off(monkeypatch):
    monkeypatch.delenv("OPENOUTREACH_ALLOW_SEND", raising=False)


def _find_one_lead(name, *args, stdout, **kwargs):
    """The finder's `find --json`, answering with one lead."""
    stdout.write(json.dumps(LEAD) + "\n")


def test_run_enrols_what_was_found_in_the_cold_sequence_and_sends(monkeypatch):
    from openoutsend.leads.models import Deal

    monkeypatch.setenv("OPENOUTREACH_ALLOW_SEND", "1")
    sent = []
    with patch("openoutreach.wizard.onboard"), \
            patch("django.core.management.call_command", side_effect=_find_one_lead), \
            patch.object(cli, "_send", side_effect=lambda rest: sent.append(rest) or 0):
        assert cli._run(["--send"]) == 0

    deal = Deal.objects.get(lead__email=LEAD["email"])
    assert (deal.sequence, deal.step) == ("cold", None)
    assert sent == [[]]


class TestRunCannotSendByDefault:
    """Fail on upstream, whose bare `run` found, enrolled and sent in one go."""

    def test_a_bare_run_finds_leads_and_hands_nothing_to_the_sender(self):
        from openoutsend.leads.models import Deal

        calls = []
        with patch("openoutreach.wizard.onboard"), \
                patch("django.core.management.call_command",
                      side_effect=lambda *a, **k: calls.append(a)), \
                patch.object(cli, "_send") as send:
            assert cli._run([]) == 0

        send.assert_not_called()
        assert Deal.objects.count() == 0
        # leads, not addresses: the `emails` unit buys from BetterContact
        assert calls == [("find", str(cli.DEFAULT_GOAL))]

    def test_run_with_a_goal_finds_that_many_and_still_sends_nothing(self):
        calls = []
        with patch("openoutreach.wizard.onboard"), \
                patch("django.core.management.call_command",
                      side_effect=lambda *a, **k: calls.append(a)), \
                patch.object(cli, "_send") as send:
            assert cli._run(["12"]) == 0

        send.assert_not_called()
        assert calls == [("find", "12")]

    def test_send_asked_for_without_the_switch_is_still_find_only(self, capsys):
        calls = []
        with patch("openoutreach.wizard.onboard"), \
                patch("django.core.management.call_command",
                      side_effect=lambda *a, **k: calls.append(a)), \
                patch.object(cli, "_send") as send:
            assert cli._run(["--send"]) == 0

        send.assert_not_called()
        assert calls == [("find", str(cli.DEFAULT_GOAL))]
        assert "OPENOUTREACH_ALLOW_SEND" in capsys.readouterr().err

    def test_the_switch_alone_does_not_send_without_the_flag(self, monkeypatch):
        """Two deliberate acts: the environment says sending is possible, the flag says
        this run should."""
        monkeypatch.setenv("OPENOUTREACH_ALLOW_SEND", "1")
        with patch("openoutreach.wizard.onboard"), \
                patch("django.core.management.call_command"), \
                patch.object(cli, "_send") as send:
            assert cli._run([]) == 0

        send.assert_not_called()

    def test_onboarding_in_the_default_mode_never_touches_the_mailbox(self, monkeypatch):
        """The sender's readiness check logs in to the mailbox; a find-only run has none."""
        reached = []
        monkeypatch.setattr("openoutfind.core.readiness.check_ready", lambda: None)
        monkeypatch.setattr("openoutsend.first_run.check_ready",
                            lambda: reached.append("mailbox login"))

        from openoutreach import wizard

        wizard._check_children()

        assert reached == []
