"""Thin wrapper around the local Ollama server. Nothing leaves the machine."""
import os
import requests
from .config import CFG


def chat(system, user, json_mode=False):
    c = CFG["llm"]
    body = {
        "model": c["model"],
        "stream": False,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "options": {"temperature": c["temperature"], "num_ctx": c["num_ctx"]},
    }
    if json_mode:
        body["format"] = "json"
    r = requests.post(f"{os.environ.get('OLLAMA_HOST', c['host'])}/api/chat", json=body, timeout=c["timeout_s"])
    r.raise_for_status()
    return r.json()["message"]["content"].strip()
