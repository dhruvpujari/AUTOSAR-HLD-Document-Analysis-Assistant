"""Deterministic consistency checks and revision comparison. No LLM in here."""


def check_inventory(inv):
    """inv = {"components": {name: {ports, depends_on}}, "interfaces": {...}, "signals": {...}}"""
    f = []
    comps, ifaces, sigs = inv["components"], inv["interfaces"], inv["signals"]

    used_ifaces = set()
    for cname, c in comps.items():
        for p in c.get("ports", []):
            i = p.get("interface", "")
            if i:
                used_ifaces.add(i)
                if i not in ifaces:
                    f.append({"rule": "undefined_interface", "severity": "high", "entity": cname,
                              "message": f"Port {p['name']} of {cname} uses interface {i}, which is not defined in the document.",
                              "page": c.get("page")})
        for d in c.get("depends_on", []):
            if d not in comps:
                f.append({"rule": "unknown_dependency", "severity": "high", "entity": cname,
                          "message": f"{cname} depends on {d}, but no component with that name is described.",
                          "page": c.get("page")})

    for sname, s in sigs.items():
        prod, cons = s.get("producer", ""), s.get("consumers", [])
        if prod and not cons:
            f.append({"rule": "orphan_signal", "severity": "medium", "entity": sname,
                      "message": f"Signal {sname} is produced by {prod} but has no consumer.", "page": s.get("page")})
        if cons and not prod:
            f.append({"rule": "signal_without_producer", "severity": "medium", "entity": sname,
                      "message": f"Signal {sname} has consumers but no producer.", "page": s.get("page")})
        for who in ([prod] if prod else []) + cons:
            if who not in comps:
                f.append({"rule": "signal_unknown_component", "severity": "medium", "entity": sname,
                          "message": f"Signal {sname} refers to {who}, which is not a described component.",
                          "page": s.get("page")})

    for iname in ifaces:
        if iname not in used_ifaces:
            f.append({"rule": "unused_interface", "severity": "low", "entity": iname,
                      "message": f"Interface {iname} is defined but no port uses it.", "page": ifaces[iname].get("page")})
    return f


def compare_inventories(old, new):
    """Differences between two revisions of the same HLD."""
    out = []
    for kind in ("components", "interfaces", "signals"):
        o, n = set(old[kind]), set(new[kind])
        for name in sorted(n - o):
            out.append({"change": "added", "kind": kind, "name": name, "detail": ""})
        for name in sorted(o - n):
            out.append({"change": "removed", "kind": kind, "name": name, "detail": ""})
    for name in sorted(set(old["components"]) & set(new["components"])):
        op = {(p["name"], p.get("interface", "")) for p in old["components"][name].get("ports", [])}
        np_ = {(p["name"], p.get("interface", "")) for p in new["components"][name].get("ports", [])}
        for p in sorted(np_ - op):
            out.append({"change": "port_changed", "kind": "components", "name": name,
                        "detail": f"new/changed port {p[0]} -> {p[1]}"})
        for p in sorted(op - np_):
            out.append({"change": "port_changed", "kind": "components", "name": name,
                        "detail": f"old port {p[0]} -> {p[1]} no longer present"})
    for name in sorted(set(old["signals"]) & set(new["signals"])):
        if old["signals"][name].get("producer") != new["signals"][name].get("producer"):
            out.append({"change": "producer_changed", "kind": "signals", "name": name,
                        "detail": f"{old['signals'][name].get('producer')} -> {new['signals'][name].get('producer')}"})
    return out
