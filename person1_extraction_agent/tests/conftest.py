import os

# Force offline, deterministic mode for the whole test session.
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("STORAGE_BACKEND", "local")
