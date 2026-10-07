"""Loads config.yaml and prompts.yaml from Model_Prompts_Config."""
import os
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]          # the Code/ folder
CONFIG_DIR = Path(os.environ.get("AIML_CONFIG_DIR", ROOT.parent / "Model_Prompts_Config"))


def _load(name):
    with open(CONFIG_DIR / name, encoding="utf-8") as f:
        return yaml.safe_load(f)


CFG = _load("config.yaml")
PROMPTS = _load("prompts.yaml")


def path(key):
    p = Path(CFG["paths"][key])
    p = p if p.is_absolute() else (ROOT / p)
    return p.resolve()
