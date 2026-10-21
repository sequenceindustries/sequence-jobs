"""Integration tests for email provider setup with alerts system."""
import os
from unittest.mock import patch, Mock

import pytest

from app.config import Config
from app.services.alerts import NotConfigured, EmailSender
from app.services.email import (
    get_email_sender,
    ResendSender,
    SendGridSender,
    MailgunSender,
    NullSender,
)


class TestEmailAlertsIntegration:
    """Test email system integration with alert system."""

    def test_alerts_imports_email_not_configured(self):
        """Verify alerts.py imports NotConfigured from email module."""
        # This test ensures the migration from alerts.py to email.py is complete
        from app.services.alerts import NotConfigured as AlertsNotConfigured
        from app.services.email import NotConfigured as EmailNotConfigured

        assert AlertsNotConfigured is EmailNotConfigured

    def test_alerts_imports_email_sender_interface(self):
        """Verify alerts.py uses EmailSender from email module."""
        from app.services.alerts import EmailSender as AlertsEmailSender
        from app.services.email import EmailSender as EmailEmailSender

        assert AlertsEmailSender is EmailEmailSender

    def test_null_sender_raises_not_configured(self):
        """Test that NullSender raises the correct exception."""
        sender = NullSender()
        with pytest.raises(NotConfigured):
            sender.send("test@example.com", "Subject", "Body")

    @patch.dict(os.environ, {"EMAIL_PROVIDER": "none"})
    def test_no_provider_returns_null_sender(self):
        """Test that no provider configuration returns NullSender."""
        with patch.object(Config, "EMAIL_PROVIDER", "none"):
            sender = get_email_sender()
            assert isinstance(sender, NullSender)

    @patch.dict(os.environ, {
        "EMAIL_PROVIDER": "resend",
        "EMAIL_API_KEY": "test-key",
        "EMAIL_FROM_ADDRESS": "test@example.com"
    })
    def test_resend_provider_configured(self):
        """Test Resend provider can be configured."""
        with patch.object(Config, "EMAIL_PROVIDER", "resend"), \
             patch.object(Config, "EMAIL_API_KEY", "test-key"), \
             patch.object(Config, "EMAIL_FROM_ADDRESS", "test@example.com"):
            sender = get_email_sender()
            assert isinstance(sender, ResendSender)
            assert sender.api_key == "test-key"
            assert sender.from_address == "test@example.com"

    @patch.dict(os.environ, {
        "EMAIL_PROVIDER": "sendgrid",
        "EMAIL_API_KEY": "test-key",
        "EMAIL_FROM_ADDRESS": "test@example.com"
    })
    def test_sendgrid_provider_configured(self):
        """Test SendGrid provider can be configured."""
        with patch.object(Config, "EMAIL_PROVIDER", "sendgrid"), \
             patch.object(Config, "EMAIL_API_KEY", "test-key"), \
             patch.object(Config, "EMAIL_FROM_ADDRESS", "test@example.com"):
            sender = get_email_sender()
            assert isinstance(sender, SendGridSender)
            assert sender.api_key == "test-key"
            assert sender.from_address == "test@example.com"

    @patch.dict(os.environ, {
        "EMAIL_PROVIDER": "mailgun",
        "EMAIL_API_KEY": "test-key",
        "EMAIL_FROM_ADDRESS": "test@example.com",
        "EMAIL_MAILGUN_DOMAIN": "mg.example.com"
    })
    def test_mailgun_provider_configured(self):
        """Test Mailgun provider can be configured."""
        with patch.object(Config, "EMAIL_PROVIDER", "mailgun"), \
             patch.object(Config, "EMAIL_API_KEY", "test-key"), \
             patch.object(Config, "EMAIL_FROM_ADDRESS", "test@example.com"), \
             patch.object(Config, "EMAIL_MAILGUN_DOMAIN", "mg.example.com"):
            sender = get_email_sender()
            assert isinstance(sender, MailgunSender)
            assert sender.api_key == "test-key"
            assert sender.from_address == "test@example.com"
            assert sender.domain == "mg.example.com"

    def test_all_email_senders_implement_interface(self):
        """Test that all sender implementations have the send method."""
        senders = [
            NullSender(),
            ResendSender("key", "from@test.com"),
            SendGridSender("key", "from@test.com"),
            MailgunSender("key", "from@test.com", "mg.test.com"),
        ]
        for sender in senders:
            assert hasattr(sender, "send")
            assert callable(sender.send)
            assert isinstance(sender, EmailSender)

    @patch("app.services.email.requests.post")
    def test_email_sending_flow(self, mock_post):
        """Test a complete email sending flow."""
        mock_resp = Mock()
        mock_post.return_value = mock_resp

        sender = ResendSender("test-key", "from@example.com")
        sender.send("to@example.com", "Test Subject", "Test Body")

        assert mock_post.called
        call_args = mock_post.call_args
        payload = call_args[1]["json"]
        assert payload["to"] == "to@example.com"
        assert payload["subject"] == "Test Subject"
        assert payload["text"] == "Test Body"

    def test_config_includes_email_settings(self):
        """Test that Config class has all required email settings."""
        assert hasattr(Config, "EMAIL_PROVIDER")
        assert hasattr(Config, "EMAIL_API_KEY")
        assert hasattr(Config, "EMAIL_FROM_ADDRESS")
        assert hasattr(Config, "EMAIL_MAILGUN_DOMAIN")

    def test_default_email_provider_is_none(self):
        """Test that email provider defaults to 'none' (disabled)."""
        with patch.dict(os.environ, {}, clear=False):
            # Remove EMAIL_PROVIDER if it exists
            os.environ.pop("EMAIL_PROVIDER", None)
            # Reload Config to get default
            from importlib import reload
            import app.config
            reload(app.config)
            assert app.config.Config.EMAIL_PROVIDER == "none"
