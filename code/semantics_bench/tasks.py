"""The task suite: 30 questions an industrial agent is actually asked.

Each task declares the *fact keys* that must be present in the context for the
question to be answerable at all.  Those keys are not a subjective judgement:
they are the atoms that the reference (symbolic) solver in
:mod:`semantics_bench.experiments` consumes to derive the gold answer.  A
context that lacks one of them cannot support a grounded answer - the model can
only guess.

``gold_tag`` marks the single tag the question is about, and is used by
Experiment E1 to measure entity grounding under homograph pressure.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import plant as P
from . import units as U
from .conditions import fact

CATEGORIES = {
    "GRD": "entity grounding / disambiguation",
    "UNI": "unit-correct reporting and conversion",
    "RNG": "limit and range reasoning",
    "TOP": "topology and impact analysis",
    "PRV": "provenance and root cause",
    "ACT": "action legality (behavioural model)",
    "SAF": "interlock and safety reasoning",
    "REC": "recipe / specification conformance",
}


@dataclass(frozen=True)
class Task:
    tid: str
    category: str
    question: str
    required: frozenset[str]
    gold_answer: str
    gold_tag: str | None = None
    distractors: tuple[str, ...] = ()
    note: str = ""


def _sig_facts(tag: str, *kinds: str) -> set[str]:
    out = set()
    for k in kinds:
        out.add(fact(k, tag, P.SIGNAL_OWNER[tag]) if k == "sig_of" else fact(k, tag))
    return out


def build_tasks() -> tuple[Task, ...]:
    T: list[Task] = []

    def add(tid, cat, q, required, gold, gold_tag=None, distractors=(), note=""):
        T.append(Task(tid, cat, q, frozenset(required), gold, gold_tag,
                      tuple(distractors), note))

    # ------------------------------------------------------------------ GRD
    add("GRD-01", "GRD",
        "What is the outlet pressure of the Line 1 filler right now?",
        _sig_facts("L1_FIL_PT0301_PV", "value", "unit", "sig_of"),
        "3.0 bar", "L1_FIL_PT0301_PV",
        ("L1_PAS_PT0102_PV", "L2_FIL_PT0301_PV", "L2_PAS_PT0102_PV", "UT_CMP_PT0801_PV"),
        "'Outlet pressure' is a homograph across five assets")
    add("GRD-02", "GRD",
        "What is the outlet pressure of the compressed air compressor?",
        _sig_facts("UT_CMP_PT0801_PV", "value", "unit", "sig_of"),
        "7.8 bar", "UT_CMP_PT0801_PV",
        ("L1_FIL_PT0301_PV", "L1_PAS_PT0102_PV"),
        "same description, different asset class")
    add("GRD-03", "GRD",
        "Give me the carousel speed of the Line 1 labeller.",
        _sig_facts("L1_LAB_ST0501_PV", "value", "unit", "sig_of"),
        "31.5 rpm", "L1_LAB_ST0501_PV",
        ("L1_FIL_ST0306_PV", "L2_LAB_ST0501_PV"),
        "'Carousel speed' exists on filler and labeller of both lines")
    add("GRD-04", "GRD",
        "What is the Line 2 pasteuriser zone 1 temperature?",
        _sig_facts("L2_PAS_TT0101_PV", "value", "unit", "sig_of"),
        "161.6 degF", "L2_PAS_TT0101_PV",
        ("L1_PAS_TT0101_PV",), "identical loop number on both lines")
    add("GRD-05", "GRD",
        "Report the bowl level of the filler on line 1.",
        _sig_facts("L1_FIL_LT0304_PV", "value", "unit", "sig_of"),
        "61.4 %", "L1_FIL_LT0304_PV",
        ("L1_FIL_LIC0304_SP",), "measurement vs. setpoint confusion")

    # ------------------------------------------------------------------ UNI
    add("UNI-01", "UNI",
        "Report the Line 2 pasteuriser zone 1 temperature in degrees Celsius.",
        _sig_facts("L2_PAS_TT0101_PV", "value", "unit", "sig_of")
        | {fact("dim", "DEG_F"), fact("conv", "DEG_F", "DEG_C")},
        "72.0 degC", "L2_PAS_TT0101_PV", (),
        "affine conversion; the tag is stored in degF")
    add("UNI-02", "UNI",
        "Which of the two filling lines currently runs the higher outlet pressure?",
        _sig_facts("L1_FIL_PT0301_PV", "value", "unit", "sig_of")
        | _sig_facts("L2_FIL_PT0301_PV", "value", "unit", "sig_of")
        | {fact("dim", "BAR"), fact("dim", "PSI"), fact("conv", "PSI", "BAR")},
        "Line 2 (43.5 psi = 3.0 bar) equals Line 1 (3.0 bar); they are the same",
        None, (), "cross-unit comparison, bar vs psi")
    add("UNI-03", "UNI",
        "Express the Line 1 filler product flow in cubic metres per hour.",
        _sig_facts("L1_FIL_FT0303_PV", "value", "unit", "sig_of")
        | {fact("conv", "L-PER-MIN", "M3-PER-HR"), fact("dim", "L-PER-MIN")},
        "10.8 m3/h", "L1_FIL_FT0303_PV", (), "linear conversion")
    add("UNI-04", "UNI",
        "Is the Line 2 filler outlet pressure above 3 bar?",
        _sig_facts("L2_FIL_PT0301_PV", "value", "unit", "sig_of")
        | {fact("dim", "PSI"), fact("conv", "PSI", "BAR")},
        "No - 43.5 psi = 3.0 bar, exactly at the threshold",
        "L2_FIL_PT0301_PV", (), "threshold stated in a foreign unit")
    add("UNI-05", "UNI",
        "What is the total electrical power drawn by the utilities area?",
        _sig_facts("UT_CMP_JT0803_PV", "value", "unit", "sig_of")
        | _sig_facts("UT_CHL_JT0903_PV", "value", "unit", "sig_of")
        | {fact("parent", "UT-CMP", "AREA-UTIL"), fact("parent", "UT-CHL", "AREA-UTIL")},
        "353 kW", None, (), "aggregation requires the ISA-95 membership relation")

    # ------------------------------------------------------------------ RNG
    add("RNG-01", "RNG",
        "Is 5 bar an acceptable value for the Line 1 filler fill pressure setpoint?",
        _sig_facts("L1_FIL_PIC0301_SP", "range", "unit", "access", "sig_of"),
        "No - the engineering range is 0.5 to 4.5 bar", "L1_FIL_PIC0301_SP")
    add("RNG-02", "RNG",
        "Can I write 250 kPa to the Line 1 filler fill pressure setpoint?",
        _sig_facts("L1_FIL_PIC0301_SP", "range", "unit", "access", "sig_of")
        | {fact("dim", "BAR"), fact("conv", "KiloPA", "BAR")},
        "Yes - 250 kPa = 2.5 bar, inside 0.5 to 4.5 bar", "L1_FIL_PIC0301_SP",
        (), "a flat range check in the stated unit would reject this")
    add("RNG-03", "RNG",
        "The Line 1 filler bowl level reads 61.4 %. Is any alarm limit exceeded?",
        _sig_facts("L1_FIL_LT0304_PV", "value", "alarm", "unit", "sig_of"),
        "No - limits are 15 % low and 92 % high", "L1_FIL_LT0304_PV")
    add("RNG-04", "RNG",
        "Which tags anywhere in the plant are currently outside their alarm limits?",
        {fact("value", s.tag) for s in P.ALL_SIGNALS if s.sample_value is not None}
        | {fact("alarm", s.tag) for s in P.ALL_SIGNALS
           if s.alarm_low is not None or s.alarm_high is not None}
        | {fact("sig_of", s.tag, P.SIGNAL_OWNER[s.tag]) for s in P.ALL_SIGNALS},
        "L2_PAS_PU0103_PV: 8.5 PU against a 15 PU low limit", None, (),
        "plant-wide sweep - the evidence cannot fit in any context window")
    add("RNG-05", "RNG",
        "May I write to the Line 1 filler outlet pressure tag?",
        _sig_facts("L1_FIL_PT0301_PV", "access", "role", "sig_of"),
        "No - PT0301.PV is a read-only measurement; write PIC0301.SP instead",
        "L1_FIL_PT0301_PV")

    # ------------------------------------------------------------------ TOP
    add("TOP-01", "TOP",
        "If compressor UT-CMP trips, which production units lose their air supply?",
        {fact("feeds", "UT-CMP", "L1-FIL"), fact("feeds", "UT-CMP", "L2-FIL"),
         fact("feeds", "UT-CMP", "L1-CAP"), fact("label", "UT-CMP")},
        "L1-FIL, L2-FIL and L1-CAP", None, (), "one-hop utility dependency")
    add("TOP-02", "TOP",
        "Which units are downstream of the Line 1 pasteuriser?",
        {fact("feeds", "L1-PAS", "L1-FIL"), fact("feeds", "L1-FIL", "L1-CAP"),
         fact("feeds", "L1-CAP", "L1-LAB")},
        "L1-FIL, then L1-CAP, then L1-LAB", None, (), "transitive closure")
    add("TOP-03", "TOP",
        "List every asset belonging to Bottling Line 1.",
        {fact("parent", a.local_id, "L1") for a in P.PLANT if a.parent == "L1"}
        | {fact("label", a.local_id) for a in P.PLANT if a.parent == "L1"},
        "L1-PAS, L1-FIL, L1-CAP, L1-LAB, L1-CIP", None, (), "mereology")
    add("TOP-04", "TOP",
        "Which chiller serves the Line 2 filler?",
        {fact("feeds", "UT-CHL", "L2-FIL"), fact("label", "UT-CHL")},
        "Chiller 1 (UT-CHL)", None, (), "cross-area dependency")
    add("TOP-05", "TOP",
        "Which line would be affected by taking Chiller 1 out of service, and which units?",
        {fact("feeds", "UT-CHL", "L1-FIL"), fact("feeds", "UT-CHL", "L2-FIL"),
         fact("feeds", "UT-CHL", "L1-PAS"),
         fact("parent", "L1-FIL", "L1"), fact("parent", "L2-FIL", "L2"),
         fact("parent", "L1-PAS", "L1")},
        "Both lines: L1-FIL, L1-PAS and L2-FIL", None, (),
        "join of the utility graph with the ISA-95 hierarchy")

    # ------------------------------------------------------------------ PRV
    add("PRV-01", "PRV",
        "Why did the Line 1 filler report a low bowl level at 02:15 on 14 July?",
        {fact("event", "EV-1001"), fact("event", "EV-1002"),
         fact("feeds", "UT-CMP", "L1-FIL"), fact("label", "UT-CMP")},
        "The compressor discharge-pressure alarm at 02:11:30 preceded it; "
        "UT-CMP feeds L1-FIL",
        None, (), "temporal ordering plus the utility dependency")
    add("PRV-02", "PRV",
        "How old is the reading you are quoting for the Line 1 filler bowl level?",
        _sig_facts("L1_FIL_LT0304_PV", "value", "time", "sig_of"),
        "Sampled 2026-07-14T02:20:00Z", "L1_FIL_LT0304_PV", (), "freshness")
    add("PRV-03", "PRV",
        "Has the compressor had maintenance in the last 60 days, and did it affect the vibration baseline?",
        {fact("event", "EV-1003"), fact("value", "UT_CMP_VT0804_PV"),
         fact("alarm", "UT_CMP_VT0804_PV"), fact("label", "UT-CMP")},
        "Yes - air-end bearing replaced 2026-06-30, vibration baseline reset; "
        "3.2 mm/s is below the 7.1 alarm", None, (), "event log plus limits")
    add("PRV-04", "PRV",
        "Which alarms fired upstream of the Line 1 capper in the five minutes "
        "before its torque alarm at 02:16?",
        {fact("event", e) for e in ("EV-1001", "EV-1002", "EV-1004", "EV-1006")}
        | {fact("label", "L1-CAP"), fact("feeds", "L1-FIL", "L1-CAP")},
        "EV-1006 (02:09:45), EV-1002 (02:11:30), EV-1001 (02:15:00)",
        None, (), "temporal window intersected with the upstream neighbourhood")

    # ------------------------------------------------------------------ ACT
    add("ACT-01", "ACT",
        "Can I start the Line 2 filler right now?",
        {fact("state", "L2-FIL"), fact("legalcmd", "L2-FIL"), fact("label", "L2-FIL")},
        "No - it is Stopped; issue Reset first, then Start", None, (),
        "PackML legality")
    add("ACT-02", "ACT",
        "What is the shortest command sequence to bring the Line 2 labeller into Execute?",
        {fact("state", "L2-LAB"), fact("legalcmd", "L2-LAB"), fact("label", "L2-LAB")},
        "Clear, Reset, Start (Aborted -> Stopped -> Idle -> Execute)", None, (),
        "planning over the state machine")
    add("ACT-03", "ACT",
        "Is it legal to send Unhold to the Line 1 CIP skid?",
        {fact("state", "L1-CIP"), fact("legalcmd", "L1-CIP"), fact("label", "L1-CIP")},
        "No - it is Idle; Unhold is only legal from Held", None, ())
    add("ACT-04", "ACT",
        "Which Line 1 units can accept a Start command without any preparatory step?",
        {fact("state", a.local_id) for a in P.PLANT
         if a.parent == "L1" and a.packml_state}
        | {fact("legalcmd", a.local_id) for a in P.PLANT
           if a.parent == "L1" and a.packml_state}
        | {fact("parent", a.local_id, "L1") for a in P.PLANT if a.parent == "L1"},
        "None - L1-PAS/FIL/CAP are already in Execute, L1-LAB is Held, L1-CIP is Idle "
        "(Idle does accept Start)", None, (), "sweep over the behavioural model")

    # ------------------------------------------------------------------ SAF
    add("SAF-01", "SAF",
        "May I change the Line 1 fill volume setpoint to 330 ml now?",
        _sig_facts("L1_FIL_QIC0305_SP", "range", "access", "unit", "interlock", "sig_of")
        | {fact("state", "L1-FIL")},
        "No - interlock ILK-02 requires the filler to be Idle, Held or Stopped; it is in Execute",
        "L1_FIL_QIC0305_SP", (), "explicit constraint model")
    add("SAF-02", "SAF",
        "Is it safe to open the Line 2 product valve?",
        {fact("interlock", "L2_FIL_XV0307_CMD"), fact("value", "L2_PAS_PU0103_PV"),
         fact("sig_of", "L2_FIL_XV0307_CMD", "L2-FIL")},
        "No - only 8.5 PU accumulated, the interlock requires at least 15 PU",
        "L2_FIL_XV0307_CMD", (), "guard evaluated against live data")
    add("SAF-03", "SAF",
        "Can the pasteuriser temperature setpoint on Line 1 be changed while CIP runs?",
        {fact("interlock", "L1_PAS_TIC0101_SP"), fact("state", "L1-CIP"),
         fact("sig_of", "L1_PAS_TIC0101_SP", "L1-PAS")},
        "Yes at present - the CIP skid is Idle, not Execute; the interlock would "
        "block it during a CIP cycle", "L1_PAS_TIC0101_SP")
    add("SAF-04", "SAF",
        "Which writable Line 1 tags are protected by an interlock?",
        {fact("interlock", str(i["tag"])) for i in P.INTERLOCKS
         if str(i["tag"]).startswith("L1_")}
        | {fact("access", str(i["tag"])) for i in P.INTERLOCKS
           if str(i["tag"]).startswith("L1_")},
        "L1_FIL_XV0307_CMD, L1_FIL_QIC0305_SP and L1_PAS_TIC0101_SP", None, ())

    # ------------------------------------------------------------------ REC
    add("REC-01", "REC",
        "Does the current Line 1 fill volume setpoint match the Cola 0.5 L recipe?",
        {fact("recipe", "P-COLA-500"), fact("value", "L1_FIL_QIC0305_SP"),
         fact("unit", "L1_FIL_QIC0305_SP"), fact("sig_of", "L1_FIL_QIC0305_SP", "L1-FIL")},
        "Yes - both are 500 ml", "L1_FIL_QIC0305_SP")
    add("REC-02", "REC",
        "Is the Line 1 capping torque setpoint within the Cola 0.5 L recipe specification?",
        {fact("recipe", "P-COLA-500"), fact("value", "L1_CAP_TQC0401_SP"),
         fact("unit", "L1_CAP_TQC0401_SP"), fact("sig_of", "L1_CAP_TQC0401_SP", "L1-CAP")},
        "Yes - 2.10 N.m against a 2.1 N.m recipe target", "L1_CAP_TQC0401_SP")
    add("REC-03", "REC",
        "For the Lemonade 1 L product, does the Line 2 fill pressure setpoint match the recipe?",
        {fact("recipe", "P-LEMON-1000"), fact("value", "L2_FIL_PIC0301_SP"),
         fact("unit", "L2_FIL_PIC0301_SP"), fact("sig_of", "L2_FIL_PIC0301_SP", "L2-FIL"),
         fact("dim", "PSI"), fact("conv", "PSI", "BAR")},
        "No - 36.5 psi = 2.52 bar against a 2.2 bar recipe target",
        "L2_FIL_PIC0301_SP", (), "recipe in bar, tag in psi")
    return tuple(T)


TASKS: tuple[Task, ...] = build_tasks()
TASKS_BY_ID: dict[str, Task] = {t.tid: t for t in TASKS}


def homograph_index() -> dict[str, list[str]]:
    """Descriptions shared by more than one tag - the disambiguation load."""
    idx: dict[str, list[str]] = {}
    for s in P.ALL_SIGNALS:
        idx.setdefault(s.description.lower(), []).append(s.tag)
    return {d: t for d, t in idx.items() if len(t) > 1}
