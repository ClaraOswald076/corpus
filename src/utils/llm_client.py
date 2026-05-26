import hashlib
import time
import json
from dataclasses import dataclass, field
from typing import Any
import litellm
from src.core.config import settings


@dataclass
class LLMCallResult:
    content: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    estimated_cost_usd: float
    latency_ms: int
    retry_count: int = 0
    success: bool = True
    error_message: str = ""


@dataclass
class ModelPresetData:
    name: str
    litellm_model_string: str
    default_params: dict = field(default_factory=dict)
    api_key: str = ""


class LiteLLMClient:
    def __init__(self):
        litellm.drop_params = settings.litellm_drop_params
        self._cache: dict[str, LLMCallResult] = {}

    async def acompletion(
        self,
        messages: list[dict[str, str]],
        preset: ModelPresetData | None = None,
        model: str | None = None,
        api_key: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        system: str | None = None,
        max_retries: int | None = None,
        extra_params: dict[str, Any] | None = None,
    ) -> LLMCallResult:
        if preset:
            model_str = preset.litellm_model_string
            api_key = api_key or preset.api_key
            merged_params = {**preset.default_params, "temperature": temperature, "max_tokens": max_tokens}
        else:
            model_str = model or "openai/gpt-4o"
            merged_params = {"temperature": temperature, "max_tokens": max_tokens}

        if extra_params:
            merged_params.update(extra_params)

        if system:
            full_messages = [{"role": "system", "content": system}] + list(messages)
        else:
            full_messages = list(messages)

        max_retries = max_retries or settings.litellm_default_max_retries
        retry_delay = settings.litellm_default_retry_delay

        api_base = merged_params.pop("api_base", None)

        # Use OpenAI SDK directly for DeepSeek (avoids LiteLLM model-map issues)
        if api_base and "deepseek" in str(api_base):
            return await self._openai_completion(
                model_str=model_str, messages=full_messages, api_key=api_key,
                api_base=api_base, temperature=temperature, max_tokens=max_tokens,
                max_retries=max_retries, retry_delay=retry_delay, extra_params=merged_params,
            )

        last_error = ""
        for attempt in range(max_retries + 1):
            try:
                return await self._litellm_call(model_str, full_messages, api_key, merged_params, attempt)
            except Exception as e:
                last_error = str(e)
                if "not mapped" in last_error.lower() and "deepseek" in model_str.lower():
                    return await self._openai_completion(
                        model_str="deepseek-v4-pro", messages=full_messages, api_key=api_key,
                        api_base="https://api.deepseek.com", temperature=temperature,
                        max_tokens=max_tokens, max_retries=max_retries, retry_delay=retry_delay,
                        extra_params=merged_params,
                    )
                if attempt < max_retries:
                    await _async_sleep(retry_delay * (2 ** attempt))

        return LLMCallResult(
            content="", model=model_str, prompt_tokens=0, completion_tokens=0,
            total_tokens=0, estimated_cost_usd=0.0, latency_ms=0,
            retry_count=max_retries, success=False, error_message=last_error,
        )

    async def _litellm_call(self, model_str: str, messages: list, api_key: str | None, params: dict, attempt: int) -> LLMCallResult:
        start = time.perf_counter()
        response = await litellm.acompletion(
            model=model_str, messages=messages, api_key=api_key,
            timeout=settings.litellm_default_timeout, **params,
        )
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        usage = getattr(response, "usage", None)
        if usage:
            pt = getattr(usage, "prompt_tokens", 0)
            ct = getattr(usage, "completion_tokens", 0)
            tt = getattr(usage, "total_tokens", pt + ct)
        else:
            pt = ct = tt = 0
        cost = litellm.cost_per_token(model_str, pt, ct) if tt > 0 else 0.0
        return LLMCallResult(
            content=response.choices[0].message.content or "", model=model_str,
            prompt_tokens=pt, completion_tokens=ct, total_tokens=tt,
            estimated_cost_usd=cost, latency_ms=elapsed_ms, retry_count=attempt, success=True,
        )

    async def _openai_completion(self, model_str: str, messages: list, api_key: str | None,
                                  api_base: str, temperature: float, max_tokens: int,
                                  max_retries: int, retry_delay: float, extra_params: dict) -> LLMCallResult:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=api_key, base_url=api_base)
        real_model = model_str.split("/")[-1] if "/" in model_str else model_str

        last_error = ""
        for attempt in range(max_retries + 1):
            try:
                start = time.perf_counter()
                resp = await client.chat.completions.create(
                    model=real_model, messages=messages,
                    temperature=temperature, max_tokens=max_tokens,
                )
                elapsed_ms = int((time.perf_counter() - start) * 1000)
                usage = resp.usage
                pt = usage.prompt_tokens if usage else 0
                ct = usage.completion_tokens if usage else 0
                return LLMCallResult(
                    content=resp.choices[0].message.content or "", model=model_str,
                    prompt_tokens=pt, completion_tokens=ct, total_tokens=pt + ct,
                    estimated_cost_usd=0.0, latency_ms=elapsed_ms,
                    retry_count=attempt, success=True,
                )
            except Exception as e:
                last_error = str(e)
                if attempt < max_retries:
                    await _async_sleep(retry_delay * (2 ** attempt))

        return LLMCallResult(
            content="", model=model_str, prompt_tokens=0, completion_tokens=0,
            total_tokens=0, estimated_cost_usd=0.0, latency_ms=0,
            retry_count=max_retries, success=False, error_message=last_error,
        )

    def get_semantic_hash(self, messages: list[dict[str, str]]) -> str:
        content = json.dumps(messages, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def get_cached(self, semantic_hash: str) -> LLMCallResult | None:
        return self._cache.get(semantic_hash)

    def set_cache(self, semantic_hash: str, result: LLMCallResult):
        self._cache[semantic_hash] = result

    def clear_cache(self):
        self._cache.clear()

    @property
    def cache_size(self) -> int:
        return len(self._cache)


llm_client = LiteLLMClient()


async def _async_sleep(seconds: float):
    import asyncio
    await asyncio.sleep(seconds)
