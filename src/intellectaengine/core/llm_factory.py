"""Provider creation with injectable validated settings and safe failures."""

from langchain_core.language_models.chat_models import BaseChatModel

from intellectaengine.config.settings import AppSettings, settings
from intellectaengine.core.contracts import ApplicationError, ErrorCode


class LLMFactory:
    PROVIDER_LABELS = {
        "gemini": "Google Gemini",
        "groq": "Groq",
        "openai": "OpenAI",
        "ollama": "Ollama (Local)",
    }

    @classmethod
    def create(
        cls,
        provider: str,
        model: str | None = None,
        temperature: float = 0.3,
        streaming: bool = False,
        config: AppSettings | None = None,
    ) -> BaseChatModel:
        config = config or settings
        provider = provider.strip().lower()
        if provider not in cls.PROVIDER_LABELS:
            raise ApplicationError(ErrorCode.INVALID_CONFIGURATION)
        model = config.get_default_model(provider) if model is None else model.strip()
        if not model:
            raise ApplicationError(ErrorCode.INVALID_CONFIGURATION)
        key = {
            "gemini": config.google_api_key,
            "groq": config.groq_api_key,
            "openai": config.openai_api_key,
        }.get(provider)
        if key is not None and not key.strip():
            raise ApplicationError(ErrorCode.INVALID_CONFIGURATION)
        try:
            return cls._build(provider, model, temperature, streaming, config)
        except ApplicationError:
            raise
        except Exception:
            raise ApplicationError(ErrorCode.PROVIDER_FAILURE) from None

    @staticmethod
    def _build(provider, model, temperature, streaming, config):
        if provider == "gemini":
            from langchain_google_genai import ChatGoogleGenerativeAI

            return ChatGoogleGenerativeAI(
                model=model,
                google_api_key=config.google_api_key,
                temperature=temperature,
                streaming=streaming,
                convert_system_message_to_human=True,
            )
        if provider == "groq":
            from langchain_groq import ChatGroq

            return ChatGroq(
                model=model,
                api_key=config.groq_api_key,
                temperature=temperature,
                streaming=streaming,
            )
        if provider == "openai":
            from langchain_openai import ChatOpenAI

            return ChatOpenAI(
                model=model,
                api_key=config.openai_api_key,
                temperature=temperature,
                streaming=streaming,
            )
        from langchain_ollama import ChatOllama

        return ChatOllama(model=model, base_url=config.ollama_base_url, temperature=temperature)

    @classmethod
    def list_providers(cls) -> list[str]:
        return sorted(cls.PROVIDER_LABELS)
