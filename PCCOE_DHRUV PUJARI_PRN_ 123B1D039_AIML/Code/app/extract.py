"""LLM entity extraction with a grounding check and regex cross-check."""
import json
import re
from typing import List
from pydantic import BaseModel, Field, ValidationError
from . import llm
from .config import PROMPTS

# naming convention of the synthetic HLDs: Swc_ / If_ / Sig_
NAME_RE = {
    "components": re.compile(r"\bSwc_[A-Za-z0-9]+"),
    "interfaces": re.compile(r"\bIf_[A-Za-z0-9]+"),
    "signals": re.compile(r"\bSig_[A-Za-z0-9]+"),
}


class Port(BaseModel):
    name: str
    direction: str = ""
    interface: str = ""


class Component(BaseModel):
    name: str
    ports: List[Port] = Field(default_factory=list)
    depends_on: List[str] = Field(default_factory=list)


class Interface(BaseModel):
    name: str
    elements: List[str] = Field(default_factory=list)


class Signal(BaseModel):
    name: str
    producer: str = ""
    consumers: List[str] = Field(default_factory=list)


class ChunkEntities(BaseModel):
    components: List[Component] = Field(default_factory=list)
    interfaces: List[Interface] = Field(default_factory=list)
    signals: List[Signal] = Field(default_factory=list)


def empty_inventory():
    return {"components": {}, "interfaces": {}, "signals": {}}


def extract_chunk(chunk_text, section):
    """One LLM call. Returns (ChunkEntities, error_or_None)."""
    user = PROMPTS["extract_user"].format(section=section, text=chunk_text)
    try:
        raw = llm.chat(PROMPTS["extract_system"], user, json_mode=True)
        return ChunkEntities.model_validate(json.loads(raw)), None
    except (json.JSONDecodeError, ValidationError, KeyError) as e:
        return ChunkEntities(), str(e)[:200]


def _grounded(name, text):
    """Keep an entity only if its exact name is in the source chunk."""
    return bool(name) and name in text


def merge_into(inv, ents, chunk_text, page):
    dropped = 0
    for c in ents.components:
        if not _grounded(c.name, chunk_text):
            dropped += 1
            continue
        cur = inv["components"].setdefault(c.name, {"ports": [], "depends_on": [], "page": page})
        have = {(p["name"], p["interface"]) for p in cur["ports"]}
        for p in c.ports:
            if p.name and (p.name, p.interface) not in have and _grounded(p.name, chunk_text):
                cur["ports"].append(p.model_dump())
                have.add((p.name, p.interface))
        for d in c.depends_on:
            if _grounded(d, chunk_text) and d not in cur["depends_on"]:
                cur["depends_on"].append(d)
    for i in ents.interfaces:
        if not _grounded(i.name, chunk_text):
            dropped += 1
            continue
        cur = inv["interfaces"].setdefault(i.name, {"elements": [], "page": page})
        cur["elements"] = sorted(set(cur["elements"]) | {e for e in i.elements if _grounded(e, chunk_text)})
    for s in ents.signals:
        if not _grounded(s.name, chunk_text):
            dropped += 1
            continue
        cur = inv["signals"].setdefault(s.name, {"producer": "", "consumers": [], "page": page})
        if s.producer and _grounded(s.producer, chunk_text):
            cur["producer"] = s.producer
        cur["consumers"] = sorted(set(cur["consumers"]) | {c for c in s.consumers if _grounded(c, chunk_text)})
    return dropped


def regex_fill(inv, chunk_text, page):
    """Names the LLM missed but which follow the naming convention get added as bare entries."""
    added = 0
    for kind, rx in NAME_RE.items():
        for name in set(rx.findall(chunk_text)):
            if name not in inv[kind]:
                inv[kind][name] = {"page": page, "source": "regex"}
                if kind == "components":
                    inv[kind][name].update(ports=[], depends_on=[])
                if kind == "interfaces":
                    inv[kind][name].update(elements=[])
                if kind == "signals":
                    inv[kind][name].update(producer="", consumers=[])
                added += 1
    return added


def build_inventory(chunks, progress=None):
    """chunks: list of ingest.Chunk. Returns (inventory, stats)."""
    inv = empty_inventory()
    stats = {"llm_errors": 0, "dropped_ungrounded": 0, "regex_added": 0}
    for n, ch in enumerate(chunks):
        ents, err = extract_chunk(ch.text, ch.section)
        if err:
            stats["llm_errors"] += 1
        stats["dropped_ungrounded"] += merge_into(inv, ents, ch.text, ch.page)
        stats["regex_added"] += regex_fill(inv, ch.text, ch.page)
        if progress:
            progress(n + 1, len(chunks))
    return inv, stats
