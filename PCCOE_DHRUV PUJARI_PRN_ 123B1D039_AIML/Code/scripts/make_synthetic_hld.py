"""
Generates the synthetic AUTOSAR-style HLD PDFs plus the ground-truth files used for evaluation.

    python scripts/make_synthetic_hld.py

Output (in ../Input_Data):
    hld_pdfs/*.pdf                  the documents
    gold_inventory.json             what is really written in each document (components, interfaces, signals)
    seeded_defects.json             findings the rule engine should report on the gold inventory
    expected_revision_diff.json     expected differences between DoorLock v1.0 and v1.1
    test_questions.json             question set with expected keywords and page numbers
    component_catalogue.csv, interface_list.csv

Some defects (undefined interface, orphan signal, unknown dependency) are written into the
documents on purpose so the checks can be measured. All content is invented.
"""
import copy
import csv
import json
import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (BaseDocTemplate, Frame, PageTemplate, Paragraph,
                                Spacer, Table, TableStyle, PageBreak)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import rules                                   # noqa: E402

OUT = Path(__file__).resolve().parents[2] / "Input_Data"


def comp(desc, ports, depends=()):
    return {"desc": desc, "ports": ports, "depends": list(depends)}


DOCS = {
    "DoorLock": {
        "title": "Door Lock Control System - High-Level Design",
        "version": "1.0",
        "purpose": "locking and unlocking of the four vehicle doors from the key fob, the interior switch and the vehicle speed",
        "components": {
            "Swc_DoorLockCtrl": comp(
                "Decides whether the doors must be locked or unlocked. It combines requests from the key fob receiver and the "
                "interior switch with the current vehicle speed, and enables speed-dependent auto lock above 10 km/h.",
                [("Rp_KeyFobReq", "required", "If_KeyFobRequest"), ("Rp_VehSpeed", "required", "If_VehSpeed"),
                 ("Pp_LockCmd", "provided", "If_DoorLockCmd")],
                ["Swc_VehSpeedProv", "Swc_KeyFobRx"]),
            "Swc_KeyFobRx": comp(
                "Receives the rolling-code message from the key fob, checks the counter window and forwards a validated request.",
                [("Pp_KeyFobReq", "provided", "If_KeyFobRequest")]),
            "Swc_VehSpeedProv": comp(
                "Provides the filtered vehicle speed that is calculated from the wheel speed signals of the brake ECU.",
                [("Pp_VehSpeed", "provided", "If_VehSpeed")]),
            "Swc_LockActuatorDrv": comp(
                "Drives the lock motor of each door, monitors the end stops and reports the actuator state back to the controller.",
                [("Rp_LockCmd", "required", "If_DoorLockCmd"), ("Pp_ActuatorStatus", "provided", "If_ActuatorStatus"),
                 ("Rp_AjarState", "required", "If_DoorAjar")],
                ["Swc_LockDiagMgr"]),
        },
        "interfaces": {
            "If_KeyFobRequest": ["LockRequest", "UnlockRequest", "PanicRequest"],
            "If_VehSpeed": ["VehSpeedKph", "VehSpeedValid"],
            "If_DoorLockCmd": ["LockTarget", "UnlockTarget", "Timeout"],
            "If_ActuatorStatus": ["MotorState", "EndStopReached"],
        },
        "signals": {
            "Sig_DoorLockState": ("Swc_LockActuatorDrv", ["Swc_DoorLockCtrl"]),
            "Sig_KeyFobValid": ("Swc_KeyFobRx", ["Swc_DoorLockCtrl"]),
            "Sig_VehSpeedKph": ("Swc_VehSpeedProv", ["Swc_DoorLockCtrl"]),
            "Sig_LockFaultFlag": ("Swc_LockActuatorDrv", []),
        },
        "flows": [
            ("Unlock by key fob", ["The key fob sends an unlock request.", "Swc_KeyFobRx validates the rolling code and sets Sig_KeyFobValid.",
                                   "Swc_DoorLockCtrl checks the vehicle speed and sends Pp_LockCmd.", "Swc_LockActuatorDrv moves the motor and reports Sig_DoorLockState."]),
            ("Speed dependent auto lock", ["Swc_VehSpeedProv publishes Sig_VehSpeedKph every 20 ms.", "When the speed stays above the threshold for 2 s, Swc_DoorLockCtrl requests a lock."]),
        ],
        "revisions": [("1.0", "2026-03-02", "Initial release")],
    },
    "WindowLift": {
        "title": "Window Lift System - High-Level Design",
        "version": "1.0",
        "purpose": "electric opening and closing of the front windows with one-touch operation and anti-pinch protection",
        "components": {
            "Swc_WindowLiftCtrl": comp(
                "Main controller. It converts the switch input into a motor command, supports one-touch up and down, and stops the motor when a pinch event is reported.",
                [("Rp_SwitchInput", "required", "If_WindowSwitch"), ("Rp_Position", "required", "If_WindowPosition"),
                 ("Pp_MotorCmd", "provided", "If_MotorCmd")],
                ["Swc_SwitchRx", "Swc_PositionSensor"]),
            "Swc_SwitchRx": comp("Reads the window switch, debounces it with a 30 ms filter and classifies short and long presses.",
                                 [("Pp_Switch", "provided", "If_WindowSwitch")]),
            "Swc_PositionSensor": comp("Counts Hall sensor pulses and calculates the window position in percent.",
                                       [("Pp_Position", "provided", "If_WindowPosition")]),
            "Swc_AntiPinchMon": comp("Watches the motor current while the window closes and raises a pinch event when the current slope is above the calibrated limit.",
                                     [("Rp_MotorCurrent", "required", "If_MotorCurrent"), ("Pp_PinchEvent", "provided", "If_PinchEvent")],
                                     ["Swc_WindowLiftCtrl"]),
        },
        "interfaces": {
            "If_WindowSwitch": ["SwitchState", "PressDuration"],
            "If_WindowPosition": ["PositionPct", "PositionValid"],
            "If_MotorCmd": ["Direction", "DutyCycle"],
            "If_PinchEvent": ["PinchDetected", "PinchPosition"],
        },
        "signals": {
            "Sig_WindowPosPct": ("Swc_PositionSensor", ["Swc_WindowLiftCtrl", "Swc_AntiPinchMon"]),
            "Sig_PinchDetected": ("Swc_AntiPinchMon", ["Swc_WindowLiftCtrl"]),
            "Sig_WindowSwitchCmd": ("Swc_SwitchRx", ["Swc_WindowLiftCtrl"]),
            "Sig_MotorDutyCycle": ("Swc_WindowLiftCtrl", ["Swc_MotorDriverHw"]),
        },
        "flows": [
            ("One-touch close", ["The driver presses the switch longer than 400 ms.", "Swc_SwitchRx reports a long press.",
                                 "Swc_WindowLiftCtrl closes the window until the end position or until Sig_PinchDetected is set."]),
        ],
        "revisions": [("1.0", "2026-03-10", "Initial release")],
    },
    "BatteryMonitor": {
        "title": "Battery Monitoring System - High-Level Design",
        "version": "1.0",
        "purpose": "monitoring of cell voltages and pack temperature and estimation of the state of charge for a 48 V battery pack",
        "components": {
            "Swc_BatMonMgr": comp("Top level manager. It collects voltage, temperature and state of charge and decides about warnings and derating requests.",
                                  [("Rp_CellVolt", "required", "If_CellVoltage"), ("Rp_PackTemp", "required", "If_PackTemp"),
                                   ("Pp_SocValue", "provided", "If_SocValue")],
                                  ["Swc_CellVoltAcq", "Swc_TempAcq"]),
            "Swc_CellVoltAcq": comp("Measures the voltage of each cell through the monitoring chip every 10 ms.", [("Pp_CellVolt", "provided", "If_CellVoltage")]),
            "Swc_TempAcq": comp("Reads the pack temperature sensors and removes implausible values.", [("Pp_PackTemp", "provided", "If_PackTemp")]),
            "Swc_SocEstimator": comp("Estimates state of charge from the cell voltage using a lookup table and coulomb counting.",
                                     [("Rp_CellVolt", "required", "If_CellVoltage"), ("Pp_Soc", "provided", "If_SocValue")],
                                     ["Swc_BatMonMgr"]),
        },
        "interfaces": {
            "If_CellVoltage": ["CellVoltMv", "CellIndex"],
            "If_PackTemp": ["TempDegC", "SensorId"],
            "If_SocValue": ["SocPercent", "SocValid"],
            "If_BalancingCmd": ["BalanceMask", "BalanceTime"],
        },
        "signals": {
            "Sig_SocPercent": ("Swc_SocEstimator", ["Swc_BatMonMgr"]),
            "Sig_PackTempC": ("Swc_TempAcq", ["Swc_BatMonMgr", "Swc_SocEstimator"]),
            "Sig_CellMinMv": ("Swc_CellVoltAcq", []),
            "Sig_BalancingActive": ("", ["Swc_BatMonMgr"]),
        },
        "flows": [
            ("Low voltage warning", ["Swc_CellVoltAcq publishes the cell voltages.", "Swc_BatMonMgr compares the minimum cell voltage with the warning threshold.",
                                     "A warning is raised if the value is below the threshold for 500 ms."]),
        ],
        "revisions": [("1.0", "2026-04-01", "Initial release")],
    },
    "WiperControl": {
        "title": "Wiper Control System - High-Level Design",
        "version": "1.0",
        "purpose": "front wiper control with intermittent mode and rain sensor based automatic mode",
        "components": {
            "Swc_WiperCtrl": comp("Selects the wiper speed from the stalk position and the rain level and requests the speed from the motor driver.",
                                  [("Rp_StalkPos", "required", "If_StalkPosition"), ("Rp_RainLevel", "required", "If_RainLevel"),
                                   ("Pp_WiperCmd", "provided", "If_WiperCmd")],
                                  ["Swc_StalkRx", "Swc_RainSensorRx"]),
            "Swc_StalkRx": comp("Decodes the wiper stalk position from the LIN frame of the steering column module.", [("Pp_StalkPos", "provided", "If_StalkPosition")]),
            "Swc_RainSensorRx": comp("Receives the rain intensity from the rain sensor and filters it over 1 s.", [("Pp_RainLevel", "provided", "If_RainLevel")]),
            "Swc_WiperMotorDrv": comp("Controls the wiper motor, detects the park position and reports it.",
                                      [("Rp_WiperCmd", "required", "If_WiperCmd"), ("Pp_ParkPos", "provided", "If_ParkPosition")],
                                      ["Swc_WiperCtrl", "Swc_WiperDiag"]),
        },
        "interfaces": {
            "If_StalkPosition": ["StalkState", "StalkValid"],
            "If_RainLevel": ["RainIntensity", "RainValid"],
            "If_WiperCmd": ["SpeedRequest", "ParkRequest"],
            "If_ParkPosition": ["ParkReached"],
        },
        "signals": {
            "Sig_WiperSpeedReq": ("Swc_WiperCtrl", ["Swc_WiperMotorDrv"]),
            "Sig_RainIntensity": ("Swc_RainSensorRx", ["Swc_WiperCtrl"]),
            "Sig_WiperParked": ("Swc_WiperMotorDrv", ["Swc_WiperCtrl"]),
            "Sig_StalkPos": ("Swc_StalkRx", ["Swc_WiperCtrl"]),
        },
        "flows": [
            ("Automatic wiping", ["Swc_RainSensorRx publishes Sig_RainIntensity.", "Swc_WiperCtrl maps the intensity to a speed step.", "Swc_WiperMotorDrv executes the request and reports Sig_WiperParked."]),
        ],
        "revisions": [("1.0", "2026-04-15", "Initial release")],
    },
}


def make_v11(spec):
    """Revision 1.1 of DoorLock: new component, one interface renamed, one signal removed, defect fixed."""
    s = copy.deepcopy(spec)
    s["version"] = "1.1"
    s["components"]["Swc_DoorAjarMon"] = comp("Monitors the door contacts and reports whether each door is closed.",
                                              [("Pp_AjarState", "provided", "If_DoorAjar")])
    s["interfaces"]["If_DoorAjar"] = ["DoorFL", "DoorFR", "DoorRL", "DoorRR"]
    # interface rename
    s["interfaces"]["If_DoorLockCmdV2"] = s["interfaces"].pop("If_DoorLockCmd") + ["RetryCount"]
    for c in s["components"].values():
        c["ports"] = [(p, d, "If_DoorLockCmdV2" if i == "If_DoorLockCmd" else i) for p, d, i in c["ports"]]
    s["components"]["Swc_LockActuatorDrv"]["depends"] = ["Swc_DoorAjarMon"]          # unknown dependency fixed
    del s["signals"]["Sig_LockFaultFlag"]
    s["signals"]["Sig_DoorAjar"] = ("Swc_DoorAjarMon", ["Swc_LockActuatorDrv"])
    s["revisions"] = spec["revisions"] + [("1.1", "2026-05-20", "Added door ajar monitor, renamed lock command interface, removed lock fault flag")]
    return s


# ----------------------------------------------------------------- PDF
class Doc(BaseDocTemplate):
    def __init__(self, fn, header, **kw):
        super().__init__(fn, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=22 * mm, bottomMargin=20 * mm, **kw)
        self.header, self.pages = header, {}
        fr = Frame(self.leftMargin, self.bottomMargin, self.width, self.height, id="n")
        self.addPageTemplates([PageTemplate(id="p", frames=[fr], onPage=self._decor)])

    def _decor(self, c, d):
        c.setFont("Helvetica", 8)
        c.drawString(20 * mm, A4[1] - 12 * mm, self.header)
        c.drawRightString(A4[0] - 20 * mm, A4[1] - 12 * mm, "Synthetic document - training use only")
        c.drawCentredString(A4[0] / 2, 10 * mm, f"Page {d.page}")

    def afterFlowable(self, fl):
        k = getattr(fl, "_key", None)
        if k:
            self.pages[k] = self.page


def table(rows, widths):
    t = Table(rows, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DDE6F3")),
                           ("GRID", (0, 0), (-1, -1), 0.5, colors.grey), ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                           ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return t


def build_pdf(name, spec):
    ss = getSampleStyleSheet()
    h1, h2, body = ss["Heading1"], ss["Heading2"], ParagraphStyle("b", parent=ss["BodyText"], fontSize=10, leading=14)
    cell = ParagraphStyle("c", parent=body, fontSize=8.5, leading=11)
    fn = OUT / "hld_pdfs" / f"HLD_{name}_v{spec['version']}.pdf"
    doc = Doc(str(fn), f"{spec['title']} | Version {spec['version']}")
    S = []

    def H(text, style, key=None):
        p = Paragraph(text, style)
        p._key = key
        S.append(p)

    P = lambda t: S.append(Paragraph(t, body))
    # cover
    S += [Spacer(1, 50 * mm), Paragraph(spec["title"], ss["Title"]), Spacer(1, 6 * mm),
          Paragraph(f"Document version {spec['version']}", body), Paragraph("Status: released for review", body), PageBreak()]
    H("1 Introduction", h1)
    P(f"This High-Level Design (HLD) describes the software architecture for {spec['purpose']}. It lists the software components, "
      "their ports and interfaces, the signals exchanged between them and the main functional flows.")
    P("The document is the reference for architects, developers, integrators and test engineers. Names of components, interfaces and signals "
      "are written exactly as they appear in the software architecture model.")
    H("1.1 Scope and assumptions", h2)
    P("The design covers the application layer only. Basic software, bootloader and network management are described in separate documents. "
      "All components run in the same ECU and communicate through the runtime environment (RTE) using sender-receiver ports.")
    P("It is assumed that every signal has exactly one producer. Each signal is refreshed in the cycle time given in the signal list.")
    H("1.2 Terms", h2)
    S.append(table([["Term", "Meaning"], ["SWC", "Software component, the smallest deployable unit of application software."],
                    ["Port", "Connection point of a component. Provided ports send data, required ports receive data."],
                    ["Interface", "Typed description of the data elements exchanged over a port."],
                    ["Signal", "Named data item with one producer and one or more consumers."],
                    ["RTE", "Runtime environment that connects the components."]], [30 * mm, 140 * mm]))
    S.append(PageBreak())

    H("2 Architecture Overview", h1)
    P(f"The system consists of {len(spec['components'])} software components. Each one has a clearly defined responsibility, and the "
      "dependencies between components are kept as small as possible. The following sections give the details of every component.")
    P("Components that provide data are placed close to the hardware abstraction, while controller components sit above them and make the decisions.")
    S.append(PageBreak())

    H("3 Software Components", h1)
    for i, (cname, c) in enumerate(spec["components"].items(), start=1):
        H(f"3.{i} {cname}", h2, ("comp", cname))
        P(c["desc"])
        P(f"{cname} has {len(c['ports'])} port(s). The ports and the interfaces they use are listed in the table below.")
        rows = [["Port", "Direction", "Interface"]] + [[p, d, i] for p, d, i in c["ports"]]
        S.append(table(rows, [60 * mm, 40 * mm, 70 * mm]))
        S.append(Spacer(1, 3 * mm))
        P("Dependencies: " + (", ".join(c["depends"]) if c["depends"] else "none") + ".")
        P("Error handling: invalid or missing input data leads to a safe default value and the component sets its own status to invalid. "
          "The status is available to the diagnostic manager.")
        S.append(Spacer(1, 4 * mm))
    S.append(PageBreak())

    H("4 Interfaces", h1, ("sec", "interfaces"))
    P("All interfaces are sender-receiver interfaces. The data elements of each interface are listed below.")
    S.append(table([["Interface", "Type", "Data elements"]] +
                   [[k, "Sender-Receiver", ", ".join(v)] for k, v in spec["interfaces"].items()], [50 * mm, 40 * mm, 80 * mm]))
    S.append(PageBreak())

    H("5 Signal List", h1, ("sec", "signals"))
    P("Producer and consumers of every signal are given in the table. A dash means that no consumer is defined.")
    rows = [["Signal", "Producer", "Consumers", "Cycle"]]
    for k, (prod, cons) in spec["signals"].items():
        rows.append([k, prod or "-", ", ".join(cons) if cons else "-", "20 ms"])
    S.append(table(rows, [45 * mm, 45 * mm, 60 * mm, 20 * mm]))
    S.append(PageBreak())

    H("6 Functional Flows", h1)
    for i, (t, steps) in enumerate(spec["flows"], start=1):
        H(f"6.{i} {t}", h2)
        for n, s in enumerate(steps, start=1):
            P(f"Step {n}: {s}")
    S.append(PageBreak())
    H("7 Revision History", h1)
    S.append(table([["Version", "Date", "Change"]] + [list(r) for r in spec["revisions"]], [25 * mm, 30 * mm, 115 * mm]))
    doc.build(S)
    return fn.name, doc.pages


def inventory_of(spec):
    comps = {n: {"ports": [{"name": p, "direction": d, "interface": i} for p, d, i in c["ports"]], "depends_on": c["depends"]}
             for n, c in spec["components"].items()}
    ifaces = {n: {"elements": e} for n, e in spec["interfaces"].items()}
    sigs = {n: {"producer": p, "consumers": c} for n, (p, c) in spec["signals"].items()}
    return {"components": comps, "interfaces": ifaces, "signals": sigs}


def main():
    (OUT / "hld_pdfs").mkdir(parents=True, exist_ok=True)
    specs = dict(DOCS)
    specs["DoorLock_rev"] = make_v11(DOCS["DoorLock"])
    gold, pages, questions = {}, {}, []
    for key, spec in specs.items():
        base = "DoorLock" if key == "DoorLock_rev" else key
        fname, pg = build_pdf(base, spec)
        gold[fname] = inventory_of(spec)
        pages[fname] = pg

    # questions come from the four v1.0 documents
    qid = 0
    for key, spec in DOCS.items():
        fname = f"HLD_{key}_v{spec['version']}.pdf"
        pg = pages[fname]
        for cname, c in list(spec["components"].items()):
            qid += 1
            p, _, i = c["ports"][0]
            questions.append({"id": qid, "type": "fact", "doc": fname, "page": pg[("comp", cname)],
                              "question": f"Which interface does port {p} of {cname} use?", "keywords": [i]})
            qid += 1
            questions.append({"id": qid, "type": "multi", "doc": fname, "page": pg[("comp", cname)],
                              "question": f"List the ports of {cname}.", "keywords": [x[0] for x in c["ports"]]})
        for sname, (prod, cons) in list(spec["signals"].items())[:2]:
            if prod:
                qid += 1
                questions.append({"id": qid, "type": "table", "doc": fname, "page": pg[("sec", "signals")],
                                  "question": f"Which component produces the signal {sname}?", "keywords": [prod]})
        iname, elems = list(spec["interfaces"].items())[0]
        qid += 1
        questions.append({"id": qid, "type": "table", "doc": fname, "page": pg[("sec", "interfaces")],
                          "question": f"What data elements does {iname} contain?", "keywords": elems})
        cname = next(n for n, c in spec["components"].items() if c["depends"])
        qid += 1
        questions.append({"id": qid, "type": "multi", "doc": fname, "page": pg[("comp", cname)],
                          "question": f"Which components does {cname} depend on?", "keywords": spec["components"][cname]["depends"]})
    for q in ["What is the CAN baud rate used by Swc_DoorLockCtrl?", "Which ASIL level is assigned to Sig_PinchDetected?",
              "What is the flash memory size of the ECU running Swc_BatMonMgr?", "Which supplier developed Swc_WiperCtrl?",
              "What is the worst case execution time of Swc_SocEstimator?", "Which AUTOSAR release is used by the Window Lift ECU?"]:
        qid += 1
        questions.append({"id": qid, "type": "not_found", "doc": "", "page": 0, "question": q, "keywords": []})

    findings = {f: rules.check_inventory(inv) for f, inv in gold.items()}
    diff = rules.compare_inventories(gold["HLD_DoorLock_v1.0.pdf"], gold["HLD_DoorLock_v1.1.pdf"])

    for fn, obj in (("gold_inventory.json", gold), ("seeded_defects.json", findings),
                    ("expected_revision_diff.json", diff), ("test_questions.json", questions)):
        (OUT / fn).write_text(json.dumps(obj, indent=2), encoding="utf-8")

    with open(OUT / "component_catalogue.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["document", "component", "port_count", "depends_on"])
        for fn, inv in gold.items():
            for n, c in inv["components"].items():
                w.writerow([fn, n, len(c["ports"]), ";".join(c["depends_on"])])
    with open(OUT / "interface_list.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["document", "interface", "elements"])
        for fn, inv in gold.items():
            for n, i in inv["interfaces"].items():
                w.writerow([fn, n, ";".join(i["elements"])])

    print(f"{len(gold)} PDFs, {len(questions)} questions, {sum(len(v) for v in findings.values())} findings, {len(diff)} diff items")


if __name__ == "__main__":
    main()
