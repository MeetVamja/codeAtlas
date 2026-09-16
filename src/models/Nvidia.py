import collections
import os
import threading
import time

import dotenv
import openai
from openai import OpenAI

from .Base import BaseModel

dotenv.load_dotenv()

NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"

# NVIDIA NIM's free tier caps at 40 requests/minute per API key, shared across
# all models. Stay a bit under that so normal latency jitter doesn't trip a 429.
_RATE_LIMIT_PER_MINUTE = 35
_call_times = collections.deque()
_rate_lock = threading.Lock()


def _throttle():
    with _rate_lock:
        now = time.monotonic()
        while _call_times and now - _call_times[0] > 60:
            _call_times.popleft()
        if len(_call_times) >= _RATE_LIMIT_PER_MINUTE:
            sleep_for = 60 - (now - _call_times[0]) + 0.1
        else:
            sleep_for = 0
        if sleep_for <= 0:
            _call_times.append(now)
    if sleep_for > 0:
        time.sleep(sleep_for)
        with _rate_lock:
            _call_times.append(time.monotonic())


class NvidiaModel(BaseModel):
    """
    NVIDIA NIM model interface. NVIDIA's API catalog (build.nvidia.com) exposes
    an OpenAI-compatible Chat Completions endpoint, so we reuse the `openai`
    client with a custom base_url.
    """

    def __init__(
        self,
        model_name=None,
        temperature=0,
        top_p=0.95,
        max_tokens=4096,
        **kwargs,
    ):
        api_key = os.getenv("NVIDIA_API_KEY")
        assert api_key is not None, "API Key must be provided as environment variable `NVIDIA_API_KEY`"

        self.client = OpenAI(base_url=NVIDIA_BASE_URL, api_key=api_key, timeout=120)
        self.model_params = {
            "model": model_name or os.getenv("NVIDIA_MODEL", "openai/gpt-oss-20b"),
            "temperature": temperature,
            "top_p": top_p,
            "max_tokens": max_tokens,
        }

    def prompt(self, processed_input: list):
        for attempt in range(6):
            _throttle()
            try:
                response = self.client.chat.completions.create(
                    messages=processed_input,
                    **self.model_params,
                )
                usage = response.usage
                return (
                    response.choices[0].message.content,
                    usage.prompt_tokens if usage else 0,
                    usage.completion_tokens if usage else 0,
                )
            except openai.RateLimitError as e:
                if attempt == 5:
                    raise
                retry_after = getattr(e.response, "headers", {}).get("retry-after")
                time.sleep(float(retry_after) if retry_after else 15 * (attempt + 1))
            except Exception:
                if attempt == 5:
                    raise
                time.sleep(2 ** attempt)

        raise RuntimeError("Unreachable")


class Nvidia(NvidiaModel):
    pass
