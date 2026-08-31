from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from src.utils.llm_client import LiteLLMClient


def _fake_response(content, prompt_tokens, completion_tokens):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens),
    )


async def test_litellm_call_sums_cost_pair():
    client = LiteLLMClient()
    fake = _fake_response("ok", 1000, 500)
    with patch("src.utils.llm_client.litellm.acompletion", new=AsyncMock(return_value=fake)), \
         patch("src.utils.llm_client.litellm.cost_per_token", return_value=(0.00028, 0.00021)):
        result = await client._litellm_call(
            "deepseek/deepseek-chat", [{"role": "user", "content": "hi"}], None, {}, 0,
        )
    assert isinstance(result.estimated_cost_usd, float)
    assert result.estimated_cost_usd == 0.00028 + 0.00021
