"""Tests for Groq provider integration."""
import json
from unittest.mock import MagicMock, patch

import pytest

from app.ai.provider import AIGateway, AIUnavailable, AIOutputInvalid
from app.ai.providers.groq import GroqProvider


class TestGroqProvider:
    """Test Groq provider instantiation and API calls."""

    def test_groq_provider_requires_api_key(self):
        """Groq provider should raise if no API key is available."""
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(AIUnavailable, match="GROQ_API_KEY not set"):
                GroqProvider()

    def test_groq_provider_init_with_key(self):
        """Groq provider initializes with API key."""
        provider = GroqProvider(api_key="test-key-123")
        assert provider.api_key == "test-key-123"
        assert provider.name == "groq"
        assert provider.model == "mixtral-8x7b-32768"
        assert provider.price_per_mtok is not None

    def test_groq_provider_complete_success(self):
        """Test successful completion call to Groq."""
        provider = GroqProvider(api_key="test-key")
        mock_response = {
            "choices": [{"message": {"content": '{"result": "ok"}'}}],
            "usage": {"prompt_tokens": 50, "completion_tokens": 30},
        }

        with patch("app.ai.providers.groq.requests.post") as mock_post:
            mock_post.return_value.json.return_value = mock_response
            mock_post.return_value.raise_for_status = MagicMock()

            completion = provider.complete(
                system="You are a helpful assistant.",
                user="Hello",
                max_output_tokens=100,
                json_mode=True,
            )

            assert completion.text == '{"result": "ok"}'
            assert completion.model == "mixtral-8x7b-32768"
            assert completion.input_tokens == 50
            assert completion.output_tokens == 30
            assert mock_post.called

    def test_groq_provider_complete_network_error(self):
        """Test handling of network errors."""
        import requests as requests_module

        provider = GroqProvider(api_key="test-key")

        with patch("app.ai.providers.groq.requests.post") as mock_post:
            mock_post.side_effect = requests_module.ConnectionError("Connection timeout")

            with pytest.raises(AIUnavailable, match="Groq API error"):
                provider.complete(
                    system="You are helpful.",
                    user="Test",
                    max_output_tokens=100,
                )

    def test_ai_gateway_with_groq(self):
        """Test AIGateway initialization with Groq provider."""
        provider = GroqProvider(api_key="test-key")
        # Use a mock DB URL to avoid needing a real database for this test
        gateway = AIGateway("postgresql://dummy", provider, daily_budget_usd=10.0)

        assert gateway.provider.name == "groq"
        assert gateway.daily_budget_usd == 10.0

    def test_groq_provider_json_mode_request(self):
        """Verify that JSON mode is requested correctly."""
        provider = GroqProvider(api_key="test-key")
        mock_response = {
            "choices": [{"message": {"content": '{"status":"ok"}'}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }

        with patch("app.ai.providers.groq.requests.post") as mock_post:
            mock_post.return_value.json.return_value = mock_response
            mock_post.return_value.raise_for_status = MagicMock()

            provider.complete(
                system="Be concise.",
                user="Test prompt",
                max_output_tokens=50,
                json_mode=True,
            )

            # Check that the request payload includes response_format
            call_args = mock_post.call_args
            payload = call_args[1]["json"]
            assert "response_format" in payload
            assert payload["response_format"]["type"] == "json_object"

    def test_groq_provider_price_calculation(self):
        """Verify price per token is set correctly for Groq."""
        provider = GroqProvider(api_key="test-key")
        # Groq pricing: $0.27 per 1M tokens for both input and output
        assert provider.price_per_mtok == (0.27 / 1000, 0.27 / 1000)
