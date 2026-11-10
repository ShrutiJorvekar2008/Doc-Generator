"""Provider-switchable LLM client (free-tier friendly). LLM_PROVIDER = gemini | groq | openrouter | mock."""
import json
import re
import time
from .config import settings

DEFAULT_MODELS = {
    "gemini": "gemini-flash-latest",              # override with LLM_MODEL if Google renames/retires it
    "groq": "llama-3.3-70b-versatile",
    "openrouter": "meta-llama/llama-3.3-70b-instruct:free",
}


def extract_json(text: str) -> dict:
    """Parse a JSON object out of an LLM reply (handles ```json fences and chatter)."""
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < 0:
        raise ValueError("no JSON object in model output")
    return json.loads(text[start:end + 1])


class LLM:
    def __init__(self):
        self.provider = settings.LLM_PROVIDER
        self.model = settings.LLM_MODEL or DEFAULT_MODELS.get(self.provider, "")
        self._chat = None

    def _client(self):
        if self._chat is not None:
            return self._chat
        if self.provider == "gemini":
            from langchain_google_genai import ChatGoogleGenerativeAI
            self._chat = ChatGoogleGenerativeAI(model=self.model, google_api_key=settings.GOOGLE_API_KEY, temperature=0.2)
        elif self.provider == "groq":
            from langchain_groq import ChatGroq
            self._chat = ChatGroq(model=self.model, api_key=settings.GROQ_API_KEY, temperature=0.2)
        elif self.provider == "openrouter":
            from langchain_openai import ChatOpenAI
            self._chat = ChatOpenAI(model=self.model, api_key=settings.OPENROUTER_API_KEY,
                                    base_url="https://openrouter.ai/api/v1", temperature=0.2)
        else:
            raise RuntimeError(f"Unknown LLM_PROVIDER '{self.provider}'")
        return self._chat

    def complete(self, system: str, user: str, stage: str = "", ctx: dict | None = None) -> str:
        if self.provider == "mock":
            from .mock_llm import mock_complete
            return mock_complete(stage, ctx or {})
        from langchain_core.messages import SystemMessage, HumanMessage
        last = None
        for attempt in range(4):  # free tiers rate-limit (429): back off and retry
            try:
                out = self._client().invoke([SystemMessage(content=system), HumanMessage(content=user)])
                c = out.content
                return c if isinstance(c, str) else "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in c)
            except Exception as e:  # noqa: BLE001
                last = e
                if any(k in str(e).lower() for k in ("429", "rate", "quota", "resource_exhausted", "unavailable")):
                    time.sleep(2 ** attempt * 3)
                    continue
                raise
        raise RuntimeError(f"LLM rate limit / quota exhausted after retries: {last}")


_llm = None


def get_llm() -> LLM:
    global _llm
    if _llm is None:
        _llm = LLM()
    return _llm
