import os
import time

import anthropic
import dotenv

from .Base import BaseModel

dotenv.load_dotenv()


class ClaudeModel(BaseModel):
    """
    Anthropic Claude model interface, following the same `prompt` contract as
    OpenAIModel / Gemini: takes a list of {"role": "user", "content": ...}
    dicts and returns (text, prompt_tokens, completion_tokens).
    """

    def __init__(
        self,
        model_name=None,
        temperature=0,
        max_tokens=4096,
        **kwargs,
    ):
        api_key = os.getenv("ANTHROPIC_API_KEY")
        assert api_key is not None, "API Key must be provided as environment variable `ANTHROPIC_API_KEY`"

        self.client = anthropic.Anthropic(api_key=api_key)
        self.model_name = model_name or os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5")
        self.temperature = temperature
        self.max_tokens = max_tokens

    def prompt(self, processed_input: list):
        messages = [
            {"role": m["role"], "content": m["content"]}
            for m in processed_input
            if m["role"] != "system"
        ]
        system_prompts = [m["content"] for m in processed_input if m["role"] == "system"]
        system = "\n\n".join(system_prompts) if system_prompts else anthropic.NOT_GIVEN

        for attempt in range(5):
            try:
                response = self.client.messages.create(
                    model=self.model_name,
                    max_tokens=self.max_tokens,
                    temperature=self.temperature,
                    system=system,
                    messages=messages,
                )
                text = "".join(
                    block.text for block in response.content if block.type == "text"
                )
                return text, response.usage.input_tokens, response.usage.output_tokens
            except anthropic.APIStatusError as e:
                if attempt == 4:
                    raise
                time.sleep(2 ** attempt)

        raise RuntimeError("Unreachable")


class Claude(ClaudeModel):
    pass
