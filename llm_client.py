from config import API_BASE_URL
from openai import OpenAI

# Centralized OpenAI API client initialization
client = OpenAI(base_url=API_BASE_URL, api_key="not-needed")


def get_llm_client() -> OpenAI:
  """Returns the centralized LLM client instance."""
  return client