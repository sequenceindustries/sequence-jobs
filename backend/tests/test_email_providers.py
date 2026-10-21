"""Tests for email provider integrations."""
import os
from unittest.mock import Mock, patch, MagicMock

import pytest
import requests

from app.config import Config
from app.services.email import (
    ResendSender,
    SendGridSender,
    MailgunSender,
    NullSender,
    NotConfigured,
    EmailError,
    get_email_sender,
)


class TestNullSender:
    """Test the no-op NullSender."""

    def test_null_sender_raises_not_configured(self):
        sender = NullSender()
        with pytest.raises(NotConfigured) as exc:
            sender.send("test@example.com", "Test", "Body")
        assert "No email provider configured" in str(exc.value)


class TestResendSender:
    """Test Resend.com provider."""

    @patch("app.services.email.requests.post")
    def test_resend_send_success(self, mock_post):
        """Test successful email send with Resend."""
        mock_resp = Mock()
        mock_resp.json.return_value = {"id": "sent_123"}
        mock_post.return_value = mock_resp

        sender = ResendSender("test-key", "from@example.com")
        sender.send("to@example.com", "Test Subject", "Test body content")

        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args[0][0] == "https://api.resend.com/emails"
        assert call_args[1]["json"]["from"] == "from@example.com"
        assert call_args[1]["json"]["to"] == "to@example.com"
        assert call_args[1]["json"]["subject"] == "Test Subject"
        assert call_args[1]["json"]["text"] == "Test body content"
        assert "Bearer test-key" in call_args[1]["headers"]["Authorization"]

    @patch("app.services.email.requests.post")
    def test_resend_send_failure(self, mock_post):
        """Test error handling in Resend."""
        mock_resp = Mock()
        mock_resp.json.return_value = {"message": "Invalid API key"}
        mock_resp.raise_for_status.side_effect = requests.exceptions.HTTPError("401 Unauthorized")
        mock_post.return_value = mock_resp

        sender = ResendSender("invalid-key", "from@example.com")
        with pytest.raises(EmailError) as exc:
            sender.send("to@example.com", "Subject", "Body")
        assert "Resend send failed" in str(exc.value)

    @patch("app.services.email.requests.post")
    def test_resend_send_network_error(self, mock_post):
        """Test network error handling in Resend."""
        mock_post.side_effect = requests.exceptions.ConnectionError("Network unreachable")

        sender = ResendSender("test-key", "from@example.com")
        with pytest.raises(EmailError) as exc:
            sender.send("to@example.com", "Subject", "Body")
        assert "Resend send failed" in str(exc.value)


class TestSendGridSender:
    """Test SendGrid provider."""

    @patch("app.services.email.requests.post")
    def test_sendgrid_send_success(self, mock_post):
        """Test successful email send with SendGrid."""
        mock_resp = Mock()
        mock_post.return_value = mock_resp

        sender = SendGridSender("test-key", "from@example.com")
        sender.send("to@example.com", "Test Subject", "Test body")

        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args[0][0] == "https://api.sendgrid.com/v3/mail/send"
        payload = call_args[1]["json"]
        assert payload["from"]["email"] == "from@example.com"
        assert payload["personalizations"][0]["to"][0]["email"] == "to@example.com"
        assert payload["subject"] == "Test Subject"
        assert payload["content"][0]["value"] == "Test body"
        assert "Bearer test-key" in call_args[1]["headers"]["Authorization"]

    @patch("app.services.email.requests.post")
    def test_sendgrid_send_failure(self, mock_post):
        """Test error handling in SendGrid."""
        mock_resp = Mock()
        mock_resp.json.return_value = {"message": "Invalid email address"}
        mock_resp.raise_for_status.side_effect = requests.exceptions.HTTPError("400 Bad Request")
        mock_post.return_value = mock_resp

        sender = SendGridSender("test-key", "from@example.com")
        with pytest.raises(EmailError) as exc:
            sender.send("invalid@", "Subject", "Body")
        assert "SendGrid send failed" in str(exc.value)


class TestMailgunSender:
    """Test Mailgun provider."""

    @patch("app.services.email.requests.post")
    def test_mailgun_send_success(self, mock_post):
        """Test successful email send with Mailgun."""
        mock_resp = Mock()
        mock_post.return_value = mock_resp

        sender = MailgunSender("test-key", "from@example.com", "mg.example.com")
        sender.send("to@example.com", "Test Subject", "Test body")

        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args[0][0] == "https://api.mailgun.net/v3/mg.example.com/messages"
        assert call_args[1]["auth"] == ("api", "test-key")
        data = call_args[1]["data"]
        assert data["from"] == "from@example.com"
        assert data["to"] == "to@example.com"
        assert data["subject"] == "Test Subject"
        assert data["text"] == "Test body"

    @patch("app.services.email.requests.post")
    def test_mailgun_send_failure(self, mock_post):
        """Test error handling in Mailgun."""
        mock_resp = Mock()
        mock_resp.json.return_value = {"message": "Forbidden"}
        mock_resp.raise_for_status.side_effect = requests.exceptions.HTTPError("403 Forbidden")
        mock_post.return_value = mock_resp

        sender = MailgunSender("invalid-key", "from@example.com", "mg.example.com")
        with pytest.raises(EmailError) as exc:
            sender.send("to@example.com", "Subject", "Body")
        assert "Mailgun send failed" in str(exc.value)


class TestGetEmailSender:
    """Test the get_email_sender factory function."""

    @patch.dict(os.environ, {"EMAIL_PROVIDER": "none"})
    def test_get_null_sender_when_none(self):
        """Test that NullSender is returned when EMAIL_PROVIDER=none."""
        # Need to reload Config to pick up env var change
        with patch.object(Config, "EMAIL_PROVIDER", "none"):
            sender = get_email_sender()
            assert isinstance(sender, NullSender)

    @patch.dict(os.environ, {
        "EMAIL_PROVIDER": "resend",
        "EMAIL_API_KEY": "test-key",
        "EMAIL_FROM_ADDRESS": "from@example.com"
    })
    def test_get_resend_sender(self):
        """Test that ResendSender is returned when EMAIL_PROVIDER=resend."""
        with patch.object(Config, "EMAIL_PROVIDER", "resend"), \
             patch.object(Config, "EMAIL_API_KEY", "test-key"), \
             patch.object(Config, "EMAIL_FROM_ADDRESS", "from@example.com"):
            sender = get_email_sender()
            assert isinstance(sender, ResendSender)

    @patch.dict(os.environ, {
        "EMAIL_PROVIDER": "sendgrid",
        "EMAIL_API_KEY": "test-key",
        "EMAIL_FROM_ADDRESS": "from@example.com"
    })
    def test_get_sendgrid_sender(self):
        """Test that SendGridSender is returned when EMAIL_PROVIDER=sendgrid."""
        with patch.object(Config, "EMAIL_PROVIDER", "sendgrid"), \
             patch.object(Config, "EMAIL_API_KEY", "test-key"), \
             patch.object(Config, "EMAIL_FROM_ADDRESS", "from@example.com"):
            sender = get_email_sender()
            assert isinstance(sender, SendGridSender)

    @patch.dict(os.environ, {
        "EMAIL_PROVIDER": "mailgun",
        "EMAIL_API_KEY": "test-key",
        "EMAIL_FROM_ADDRESS": "from@example.com",
        "EMAIL_MAILGUN_DOMAIN": "mg.example.com"
    })
    def test_get_mailgun_sender(self):
        """Test that MailgunSender is returned when EMAIL_PROVIDER=mailgun."""
        with patch.object(Config, "EMAIL_PROVIDER", "mailgun"), \
             patch.object(Config, "EMAIL_API_KEY", "test-key"), \
             patch.object(Config, "EMAIL_FROM_ADDRESS", "from@example.com"), \
             patch.object(Config, "EMAIL_MAILGUN_DOMAIN", "mg.example.com"):
            sender = get_email_sender()
            assert isinstance(sender, MailgunSender)

    def test_get_sender_fails_without_api_key(self):
        """Test that get_email_sender raises error if EMAIL_API_KEY is missing."""
        with patch.object(Config, "EMAIL_PROVIDER", "resend"), \
             patch.object(Config, "EMAIL_API_KEY", None):
            with pytest.raises(ValueError) as exc:
                get_email_sender()
            assert "EMAIL_API_KEY is required" in str(exc.value)

    def test_get_sender_fails_without_from_address(self):
        """Test that get_email_sender raises error if EMAIL_FROM_ADDRESS is missing."""
        with patch.object(Config, "EMAIL_PROVIDER", "resend"), \
             patch.object(Config, "EMAIL_API_KEY", "test-key"), \
             patch.object(Config, "EMAIL_FROM_ADDRESS", None):
            with pytest.raises(ValueError) as exc:
                get_email_sender()
            assert "EMAIL_FROM_ADDRESS is required" in str(exc.value)

    def test_get_sender_fails_with_unknown_provider(self):
        """Test that get_email_sender raises error for unknown provider."""
        with patch.object(Config, "EMAIL_PROVIDER", "unknown"), \
             patch.object(Config, "EMAIL_API_KEY", "test-key"), \
             patch.object(Config, "EMAIL_FROM_ADDRESS", "from@example.com"):
            with pytest.raises(ValueError) as exc:
                get_email_sender()
            assert "Unknown email provider" in str(exc.value)

    def test_get_mailgun_sender_fails_without_domain(self):
        """Test that Mailgun sender requires EMAIL_MAILGUN_DOMAIN."""
        with patch.object(Config, "EMAIL_PROVIDER", "mailgun"), \
             patch.object(Config, "EMAIL_API_KEY", "test-key"), \
             patch.object(Config, "EMAIL_FROM_ADDRESS", "from@example.com"), \
             patch.object(Config, "EMAIL_MAILGUN_DOMAIN", None):
            with pytest.raises(ValueError) as exc:
                get_email_sender()
            assert "EMAIL_MAILGUN_DOMAIN is required" in str(exc.value)
