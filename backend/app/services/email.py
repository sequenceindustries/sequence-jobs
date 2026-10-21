"""Email provider integrations (Resend, SendGrid, Mailgun).

Implements provider-independent EmailSender interface with adapters for multiple backends.
Each provider requires its API key to be configured via environment variables.
No email is sent until a provider is explicitly configured.
"""
from __future__ import annotations

import json
from typing import Optional

import requests

from ..config import Config


class EmailSender:
    """Interface for email providers."""

    def send(self, to: str, subject: str, body: str) -> None:
        """Send a plaintext email.

        Args:
            to: Recipient email address.
            subject: Email subject line.
            body: Plaintext email body.

        Raises:
            NotImplementedError: If not implemented by subclass.
            EmailError: If sending fails.
        """
        raise NotImplementedError


class NotConfigured(Exception):
    """Raised when no email provider is configured."""

    pass


class EmailError(Exception):
    """Raised when email sending fails."""

    pass


class NullSender(EmailSender):
    """No-op sender that raises NotConfigured. Used when no provider is set."""

    def send(self, to: str, subject: str, body: str) -> None:
        raise NotConfigured("No email provider configured. Set EMAIL_PROVIDER and EMAIL_API_KEY.")


class ResendSender(EmailSender):
    """Resend.com provider (https://resend.com).

    Free tier: 100 emails/day.
    Recommended for South Africa.

    Configuration:
        EMAIL_PROVIDER=resend
        EMAIL_API_KEY=<your-resend-api-key>
        EMAIL_FROM_ADDRESS=<your-sender-email@your-domain.com>
    """

    BASE_URL = "https://api.resend.com"

    def __init__(self, api_key: str, from_address: str):
        """Initialize Resend provider.

        Args:
            api_key: Resend API key from https://resend.com/api-keys
            from_address: Sender email address (must be verified in Resend)
        """
        self.api_key = api_key
        self.from_address = from_address

    def send(self, to: str, subject: str, body: str) -> None:
        """Send email via Resend API."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "from": self.from_address,
            "to": to,
            "subject": subject,
            "text": body,
        }
        try:
            resp = requests.post(
                f"{self.BASE_URL}/emails",
                json=payload,
                headers=headers,
                timeout=10,
            )
            resp.raise_for_status()
        except requests.exceptions.RequestException as e:
            msg = f"Resend send failed: {e}"
            if resp := getattr(e, "response", None):
                try:
                    details = resp.json()
                    msg = f"Resend send failed: {details.get('message', str(e))}"
                except Exception:
                    pass
            raise EmailError(msg) from e


class SendGridSender(EmailSender):
    """SendGrid provider (https://sendgrid.com).

    Free tier: 100 emails/day.

    Configuration:
        EMAIL_PROVIDER=sendgrid
        EMAIL_API_KEY=<your-sendgrid-api-key>
        EMAIL_FROM_ADDRESS=<your-sender-email@your-domain.com>
    """

    BASE_URL = "https://api.sendgrid.com/v3"

    def __init__(self, api_key: str, from_address: str):
        """Initialize SendGrid provider.

        Args:
            api_key: SendGrid API key from https://app.sendgrid.com/settings/api_keys
            from_address: Sender email address (must be verified in SendGrid)
        """
        self.api_key = api_key
        self.from_address = from_address

    def send(self, to: str, subject: str, body: str) -> None:
        """Send email via SendGrid API."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "personalizations": [{"to": [{"email": to}]}],
            "from": {"email": self.from_address},
            "subject": subject,
            "content": [{"type": "text/plain", "value": body}],
        }
        try:
            resp = requests.post(
                f"{self.BASE_URL}/mail/send",
                json=payload,
                headers=headers,
                timeout=10,
            )
            resp.raise_for_status()
        except requests.exceptions.RequestException as e:
            msg = f"SendGrid send failed: {e}"
            if resp := getattr(e, "response", None):
                try:
                    details = resp.json()
                    msg = f"SendGrid send failed: {details.get('message', str(e))}"
                except Exception:
                    pass
            raise EmailError(msg) from e


class MailgunSender(EmailSender):
    """Mailgun provider (https://mailgun.com).

    Free tier: 5,000 emails/month (166 emails/day average).

    Configuration:
        EMAIL_PROVIDER=mailgun
        EMAIL_API_KEY=<your-mailgun-api-key>
        EMAIL_FROM_ADDRESS=<your-sender-email@your-domain.com>
        EMAIL_MAILGUN_DOMAIN=<your-mailgun-domain>
    """

    def __init__(self, api_key: str, from_address: str, domain: str):
        """Initialize Mailgun provider.

        Args:
            api_key: Mailgun API key from https://app.mailgun.com/app/account/security/api_keys
            from_address: Sender email address (must be on your Mailgun domain)
            domain: Mailgun domain (e.g., 'mg.example.com')
        """
        self.api_key = api_key
        self.from_address = from_address
        self.domain = domain

    def send(self, to: str, subject: str, body: str) -> None:
        """Send email via Mailgun API."""
        url = f"https://api.mailgun.net/v3/{self.domain}/messages"
        try:
            resp = requests.post(
                url,
                auth=("api", self.api_key),
                data={
                    "from": self.from_address,
                    "to": to,
                    "subject": subject,
                    "text": body,
                },
                timeout=10,
            )
            resp.raise_for_status()
        except requests.exceptions.RequestException as e:
            msg = f"Mailgun send failed: {e}"
            if resp := getattr(e, "response", None):
                try:
                    details = resp.json()
                    msg = f"Mailgun send failed: {details.get('message', str(e))}"
                except Exception:
                    pass
            raise EmailError(msg) from e


def get_email_sender() -> EmailSender:
    """Factory function to create an EmailSender based on config.

    Returns:
        An EmailSender instance configured from environment variables.
        Returns NullSender if EMAIL_PROVIDER is not set or is 'none'.

    Environment variables:
        EMAIL_PROVIDER: 'resend', 'sendgrid', 'mailgun', or 'none' (default: 'none')
        EMAIL_API_KEY: API key for the selected provider
        EMAIL_FROM_ADDRESS: Sender email address
        EMAIL_MAILGUN_DOMAIN: (Mailgun only) Mailgun domain
    """
    provider = Config.EMAIL_PROVIDER or "none"

    if provider == "none":
        return NullSender()

    api_key = Config.EMAIL_API_KEY
    if not api_key:
        raise ValueError(f"EMAIL_API_KEY is required when EMAIL_PROVIDER={provider}")

    from_address = Config.EMAIL_FROM_ADDRESS
    if not from_address:
        raise ValueError("EMAIL_FROM_ADDRESS is required for email sending")

    if provider == "resend":
        return ResendSender(api_key, from_address)
    elif provider == "sendgrid":
        return SendGridSender(api_key, from_address)
    elif provider == "mailgun":
        domain = Config.EMAIL_MAILGUN_DOMAIN
        if not domain:
            raise ValueError("EMAIL_MAILGUN_DOMAIN is required for Mailgun provider")
        return MailgunSender(api_key, from_address, domain)
    else:
        raise ValueError(f"Unknown email provider: {provider}")
