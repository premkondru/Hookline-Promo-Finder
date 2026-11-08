from .base import LLMProvider, LLMResult, ProviderError


def make_provider(api_key: str | None, fake: bool = False) -> LLMProvider:
    if fake:
        from .fake import FakeProvider

        return FakeProvider()
    from .gemini import GeminiProvider

    return GeminiProvider(api_key or "")


__all__ = ["LLMProvider", "LLMResult", "ProviderError", "make_provider"]
