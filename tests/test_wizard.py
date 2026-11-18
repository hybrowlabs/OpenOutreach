"""What this host adds: one row of answers, and the environment both children read.

The questions themselves are this program's, but what they *mean* belongs to the children
and is tested there. What is tested here is only what neither child can do alone — hold a
person's answers between runs, and hand each child its own vocabulary of them.
"""
import pytest

from openoutreach import wizard
from openoutreach.config.models import SiteConfig

ANSWERS = dict(
    product_docs="A lead finder for small B2B teams.",
    campaign_target="Founders selling to other founders.",
    ai_model="anthropic:claude-sonnet-4-5-20250929",
    llm_api_key="sk-not-a-real-key",
    dataset_path="/data/people.csv",
    operator_name="Ada Lovelace",
    operator_email="ada@example.com",
    operator_country_code="us",
    mailbox_address="ada@example.com",
    mailbox_password="app-password",
)


@pytest.fixture
def configured(db):
    config = SiteConfig.load()
    for field, value in ANSWERS.items():
        setattr(config, field, value)
    config.save()
    return config


@pytest.fixture(autouse=True)
def _no_inherited_variables(monkeypatch):
    """A developer's own exports must not decide what a test sees."""
    import os

    prefixes = ("OPENOUTFIND_", "OUTSEND_", "OPENOUTREACH_")
    for name in [n for n in os.environ if n.startswith(prefixes)]:
        monkeypatch.delenv(name)


class TestTheExport:
    """One answer, two vocabularies — the only thing that knows both names."""

    def test_a_shared_answer_reaches_both_children_under_their_own_names(self, configured):
        environment = configured.export()

        assert environment["OPENOUTFIND_PRODUCT_DOCS"] == ANSWERS["product_docs"]
        assert environment["OUTSEND_PRODUCT_DOCS"] == ANSWERS["product_docs"]
        assert environment["OPENOUTFIND_LLM_API_KEY"] == environment["OUTSEND_LLM_API_KEY"]

    def test_the_suffixes_are_not_assumed_to_match(self, configured):
        """`OPERATOR_NAME` against a finder that signs nothing, and a shared
        `OPERATOR_COUNTRY` name both children happen to spell alike."""
        environment = configured.export()

        assert environment["OPENOUTFIND_OPERATOR_COUNTRY"] == "us"
        assert environment["OUTSEND_OPERATOR_COUNTRY"] == "us"
        assert environment["OUTSEND_OPERATOR_NAME"] == "Ada Lovelace"
        assert "OPENOUTFIND_OPERATOR_NAME" not in environment

    def test_a_blank_field_exports_nothing_rather_than_an_empty_value(self, configured):
        """Unset means *use your default* to a child; blank would override it with
        nothing — the sender's SMTP host is the case that bites."""
        environment = configured.export()

        assert "OUTSEND_SMTP_HOST" not in environment
        assert "OUTSEND_BOOKING_LINK" not in environment

    def test_a_boolean_exports_as_a_word(self, configured):
        environment = configured.export()

        assert environment["OPENOUTFIND_NEWSLETTER"] == "false"

    def test_no_legal_notice_flag_is_exported(self, configured):
        assert "OPENOUTFIND_ACCEPT_LEGAL_NOTICE" not in configured.export()


class TestApplyingIt:
    def test_the_answers_land_in_the_environment(self, configured):
        wizard.apply_to_environment(configured)

        import os
        assert os.environ["OPENOUTFIND_DATASET_PATH"] == "/data/people.csv"
        assert os.environ["OUTSEND_MAILBOX_PASSWORD"] == "app-password"

    def test_an_explicit_export_beats_the_stored_answer(self, configured, monkeypatch):
        """A variable set for this run was set on purpose; a stored answer quietly
        reverting it is the failure the children's own seeding rule prevents."""
        monkeypatch.setenv("OUTSEND_PRODUCT_DOCS", "What the unit file says.")

        wizard.apply_to_environment(configured)

        import os
        assert os.environ["OUTSEND_PRODUCT_DOCS"] == "What the unit file says."
        assert os.environ["OPENOUTFIND_PRODUCT_DOCS"] == ANSWERS["product_docs"]


class TestWhatItAsksFor:
    def test_a_configured_install_is_asked_nothing(self, configured, monkeypatch):
        monkeypatch.setattr("sys.stdin.isatty", lambda: True)
        monkeypatch.setattr(wizard, "_ask", _refuse)
        monkeypatch.setattr(wizard, "_ask_secret", _refuse)

        wizard._ask_what_is_missing(configured)  # must not prompt

    def test_a_headless_install_is_told_which_variables_would_answer(self, db, monkeypatch):
        monkeypatch.setenv("OPENOUTREACH_ALLOW_SEND", "1")
        monkeypatch.setattr("sys.stdin.isatty", lambda: False)

        with pytest.raises(SystemExit) as raised:
            wizard._ask_what_is_missing(SiteConfig.load())

        message = str(raised.value)
        assert "OPENOUTFIND_PRODUCT_DOCS" in message
        assert "OUTSEND_MAILBOX_ADDRESS" in message
        assert "OPENOUTFIND_ACCEPT_LEGAL_NOTICE" not in message

    def test_a_find_only_install_is_never_asked_for_a_mailbox(self, db, monkeypatch):
        """The default: sending is off, so no mailbox and no operator are asked for, and the
        discovery sources are named instead of BetterContact."""
        monkeypatch.setattr("sys.stdin.isatty", lambda: False)

        with pytest.raises(SystemExit) as raised:
            wizard._ask_what_is_missing(SiteConfig.load())

        message = str(raised.value)
        assert "OUTSEND_MAILBOX_ADDRESS" not in message
        assert "OUTSEND_OPERATOR_EMAIL" not in message
        for variable in ("OPENOUTFIND_DATASET_PATH", "OPENOUTFIND_LEADOCEAN_API_KEY",
                         "OPENOUTFIND_LEADOCEAN_BASE_URL"):
            assert variable in message
        assert "BETTERCONTACT" not in message

    def test_a_find_only_install_is_ready_without_any_mailbox_answer(self, db, monkeypatch):
        config = SiteConfig.load()
        for field in ("product_docs", "ai_model", "llm_api_key", "dataset_path"):
            setattr(config, field, ANSWERS[field])
        monkeypatch.setattr("sys.stdin.isatty", lambda: False)

        wizard._ask_what_is_missing(config)  # must not raise or prompt

    def test_a_variable_already_exported_is_not_asked_for_again(self, db, monkeypatch):
        """Being told is being told, whichever way round it happened."""
        config = SiteConfig.load()
        for field, value in ANSWERS.items():
            if field != "dataset_path":
                setattr(config, field, value)
        monkeypatch.setenv("OPENOUTFIND_DATASET_PATH", "/from/the/unit/file.csv")
        monkeypatch.setattr("sys.stdin.isatty", lambda: False)

        wizard._ask_what_is_missing(config)  # must not raise


class TestTheLeadSource:
    """Where leads come from replaces BetterContact as the discovery question."""

    def test_the_new_answers_reach_the_finder_under_its_own_names(self, db):
        config = SiteConfig.load()
        config.discovery_provider = "leadocean+dataset"
        config.leadocean_api_key = "lo-not-a-real-key"
        config.leadocean_base_url = "https://ocean.example/api"
        config.dataset_path = "/data/people.csv"

        environment = config.export()

        assert environment["OPENOUTFIND_DISCOVERY_PROVIDER"] == "leadocean+dataset"
        assert environment["OPENOUTFIND_LEADOCEAN_API_KEY"] == "lo-not-a-real-key"
        assert environment["OPENOUTFIND_LEADOCEAN_BASE_URL"] == "https://ocean.example/api"
        assert environment["OPENOUTFIND_DATASET_PATH"] == "/data/people.csv"
        assert not any(name.startswith("OUTSEND_") and "OCEAN" in name for name in environment)

    @pytest.mark.parametrize("fields, answered", [
        ({"dataset_path": "/d.csv"}, True),
        ({"leadocean_api_key": "k", "leadocean_base_url": "https://x"}, True),
        ({"leadocean_api_key": "k"}, False),  # a key with no base URL cannot search
        ({}, False),
        ({"discovery_provider": "dataset", "leadocean_api_key": "k",
          "leadocean_base_url": "https://x"}, False),  # a chosen source must itself be complete
        ({"discovery_provider": "bettercontact", "bettercontact_api_key": "bc"}, True),
    ])
    def test_a_source_counts_only_when_it_is_complete(self, db, fields, answered):
        config = SiteConfig.load()
        for field, value in fields.items():
            setattr(config, field, value)

        assert wizard._discovery_answered(config) is answered

    def test_the_environment_alone_answers_the_question(self, db, monkeypatch):
        monkeypatch.setenv("OPENOUTFIND_DATASET_PATH", "/from/the/unit/file.csv")

        assert wizard._discovery_answered(SiteConfig.load()) is True


class TestSendingIsOffUnlessSwitchedOn:
    @pytest.mark.parametrize("value, allowed", [
        (None, False), ("", False), ("0", False), ("no", False), ("false", False),
        ("1", True), ("true", True), ("YES", True), ("on", True)])
    def test_only_an_explicit_yes_allows_sending(self, monkeypatch, value, allowed):
        if value is not None:
            monkeypatch.setenv("OPENOUTREACH_ALLOW_SEND", value)

        assert wizard.sending_allowed() is allowed

    def test_the_sender_is_not_asked_whether_it_is_ready_when_sending_is_off(self, monkeypatch):
        """Its readiness check logs in to the mailbox: an outside connection."""
        called = []
        monkeypatch.setattr("openoutfind.core.readiness.check_ready", lambda: None)
        monkeypatch.setattr("openoutsend.first_run.check_ready",
                            lambda: called.append("sender"))

        wizard._check_children()
        assert called == []

        monkeypatch.setenv("OPENOUTREACH_ALLOW_SEND", "1")
        wizard._check_children()
        assert called == ["sender"]


class TestWritingEnvironmentAnswersBack:
    """An agent that answers by exporting, not typing, still gets remembered once."""

    def test_an_env_only_answer_is_present_on_the_saved_row(self, db, monkeypatch):
        config = SiteConfig.load()
        for field, value in ANSWERS.items():
            if field != "dataset_path":
                setattr(config, field, value)
        monkeypatch.setenv("OPENOUTFIND_DATASET_PATH", "/from/the/agent.csv")

        wizard._write_back_from_environment(config)

        assert config.dataset_path == "/from/the/agent.csv"

    def test_the_newsletter_is_written_back_too(self, db, monkeypatch):
        config = SiteConfig.load()
        for field, value in ANSWERS.items():
            setattr(config, field, value)
        monkeypatch.setenv("OPENOUTFIND_NEWSLETTER", "true")

        wizard._write_back_from_environment(config)

        assert config.newsletter is True

    def test_a_second_onboard_with_the_export_removed_does_not_ask_again(
        self, db, monkeypatch
    ):
        config = SiteConfig.load()
        for field, value in ANSWERS.items():
            if field != "dataset_path":
                setattr(config, field, value)
        monkeypatch.setenv("OPENOUTFIND_DATASET_PATH", "/from/the/agent.csv")
        wizard._write_back_from_environment(config)
        config.save()

        monkeypatch.delenv("OPENOUTFIND_DATASET_PATH")
        monkeypatch.setattr("sys.stdin.isatty", lambda: True)
        monkeypatch.setattr(wizard, "_ask", _refuse)
        monkeypatch.setattr(wizard, "_ask_secret", _refuse)

        wizard._ask_what_is_missing(SiteConfig.load())  # must not prompt

    def test_write_back_never_overrules_a_value_already_on_the_row(self, db, monkeypatch):
        config = SiteConfig.load()
        for field, value in ANSWERS.items():
            setattr(config, field, value)
        monkeypatch.setenv("OPENOUTFIND_DATASET_PATH", "/different/from/the/row.csv")

        wizard._write_back_from_environment(config)

        assert config.dataset_path == ANSWERS["dataset_path"]

    def test_apply_to_environment_still_lets_an_export_win_for_this_run(
        self, configured, monkeypatch
    ):
        """`apply_to_environment`'s `setdefault` is untouched by the write-back."""
        monkeypatch.setenv("OUTSEND_PRODUCT_DOCS", "What the unit file says.")

        wizard._write_back_from_environment(configured)
        wizard.apply_to_environment(configured)

        import os
        assert os.environ["OUTSEND_PRODUCT_DOCS"] == "What the unit file says."
        assert configured.product_docs == ANSWERS["product_docs"]


class TestTheNewsletterDefault:
    """Jurisdiction-aware: no opt-in-marketing law, no question."""

    def test_a_non_protected_country_auto_subscribes_without_asking(self, monkeypatch):
        monkeypatch.setattr(wizard, "_confirm", _refuse)

        assert wizard._newsletter_default(SiteConfig(operator_country_code="us")) is True

    def test_a_protected_country_still_asks(self, monkeypatch):
        monkeypatch.setattr(wizard, "_confirm", lambda question: True)

        assert wizard._newsletter_default(SiteConfig(operator_country_code="de")) is True


def _refuse(*args, **kwargs):
    raise AssertionError("asked a question this install had already answered")
