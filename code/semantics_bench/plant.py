"""A realistic reference plant: a two-line beverage bottling facility.

Everything downstream (RDF graph, AAS submodels, OPC UA node set, WoT Thing
Descriptions, NGSI-LD entities, benchmark tasks) is generated from this single
declarative specification, so the *same* facts are expressed in every
representation and comparisons across context conditions are fair.

The specification deliberately reproduces the pathologies that make ungrounded
LLM agents fail in the field:

* cryptic ISA-5.1 tag names (``L1_FIL_PT0301_PV``) with terse, abbreviated
  descriptions;
* **homographs** - the same short description ("Outlet pressure") attached to
  several different physical assets;
* **unit heterogeneity** - pressure in ``bar`` on one line and ``psi`` on the
  other, temperature in ``degC`` and ``degF``, flow in ``L/min`` and ``m3/h``;
* read-only measurements sitting next to writable setpoints;
* safety interlocks that are invisible in the tag list but decisive for control.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Signal:
    """One process variable / tag, i.e. one OPC UA VariableNode."""

    tag: str
    description: str  # the terse text a historian would show
    unit: str  # QUDT local name, e.g. "BAR"
    quantity_kind: str
    eng_low: float
    eng_high: float
    access: str  # "r" | "rw"
    node_id: str  # OPC UA NodeId
    role: str  # "measurement" | "setpoint" | "state" | "command" | "kpi"
    brick_class: str | None = None
    sosa_property: str | None = None
    eclass_irdi: str | None = None
    aas_id_short: str | None = None
    alarm_low: float | None = None
    alarm_high: float | None = None
    safety_critical: bool = False
    sample_value: float | None = None


@dataclass(frozen=True)
class Asset:
    """A physical asset carrying an Asset Administration Shell."""

    local_id: str
    name: str
    kind: str  # SIO class local name
    manufacturer: str
    model: str
    serial: str
    eclass_class: str  # ECLASS classification class (IRDI)
    parent: str | None
    isa95_level: str  # Enterprise|Site|Area|WorkCenter|WorkUnit|ControlModule
    signals: tuple[Signal, ...] = field(default_factory=tuple)
    packml_capable: bool = False
    packml_state: str | None = None
    mtp_services: tuple[str, ...] = ()
    location: str | None = None
    commissioned: str | None = None
    criticality: str = "medium"


# ---------------------------------------------------------------------------
# Helper for terse, deliberately ambiguous descriptions
# ---------------------------------------------------------------------------

_IRDI = {
    "ManufacturerName": "0173-1#02-AAO677#002",
    "ManufacturerProductDesignation": "0173-1#02-AAW338#001",
    "SerialNumber": "0173-1#02-AAM556#002",
    "Pressure": "0173-1#02-AAA731#004",
    "Temperature": "0173-1#02-BAB129#008",
    "VolumeFlowRate": "0173-1#02-AAB717#005",
    "RotationalSpeed": "0173-1#02-BAF476#005",
    "FillVolume": "0173-1#02-AAH662#004",
    "Level": "0173-1#02-AAH663#003",
    "Power": "0173-1#02-AAB714#005",
    "Position": "0173-1#02-AAE142#003",
    "Count": "0173-1#02-AAO683#002",
}

_BRICK = {
    "Pressure": "Pressure_Sensor",
    "Temperature": "Temperature_Sensor",
    "VolumeFlowRate": "Flow_Sensor",
    "Level": "Level_Sensor",
    "Power": "Electrical_Power_Sensor",
    "AngularVelocity": "Speed_Sensor",
}

_SOSA = {
    "Pressure": "Pressure",
    "Temperature": "Temperature",
    "VolumeFlowRate": "VolumeFlowRate",
    "Level": "Level",
    "Power": "Power",
    "AngularVelocity": "AngularVelocity",
}


def _sig(
    line: str,
    unit_code: str,
    loop: str,
    suffix: str,
    description: str,
    unit: str,
    qk: str,
    low: float,
    high: float,
    access: str,
    role: str,
    *,
    alarm_low: float | None = None,
    alarm_high: float | None = None,
    safety: bool = False,
    value: float | None = None,
    id_short: str | None = None,
) -> Signal:
    tag = f"{line}_{unit_code}_{loop}_{suffix}"
    node = f"ns=3;s={line}.{unit_code}.{loop}.{suffix}"
    return Signal(
        tag=tag,
        description=description,
        unit=unit,
        quantity_kind=qk,
        eng_low=low,
        eng_high=high,
        access=access,
        node_id=node,
        role=role,
        brick_class=_BRICK.get(qk),
        sosa_property=_SOSA.get(qk),
        eclass_irdi=_IRDI.get(qk),
        aas_id_short=id_short or f"{loop}{suffix.title()}",
        alarm_low=alarm_low,
        alarm_high=alarm_high,
        safety_critical=safety,
        sample_value=value,
    )


# ---------------------------------------------------------------------------
# The plant
# ---------------------------------------------------------------------------


def _filler(line: str, press_unit: str, temp_unit: str, flow_unit: str) -> tuple[Signal, ...]:
    """Rotary filler. Note: 'Outlet pressure' is a deliberate homograph."""
    hi_p = 6.0 if press_unit == "BAR" else 87.0
    return (
        _sig(line, "FIL", "PT0301", "PV", "Outlet pressure", press_unit, "Pressure",
             0.0, hi_p, "r", "measurement", alarm_high=hi_p * 0.83, value=hi_p * 0.5),
        _sig(line, "FIL", "PIC0301", "SP", "Fill pressure setpoint", press_unit, "Pressure",
             0.5, hi_p * 0.75, "rw", "setpoint", value=hi_p * 0.42),
        _sig(line, "FIL", "TT0302", "PV", "Product temperature", temp_unit, "Temperature",
             -5.0 if temp_unit == "DEG_C" else 23.0,
             40.0 if temp_unit == "DEG_C" else 104.0, "r", "measurement",
             alarm_high=8.0 if temp_unit == "DEG_C" else 46.4, value=4.0 if temp_unit == "DEG_C" else 39.2),
        _sig(line, "FIL", "FT0303", "PV", "Product flow", flow_unit, "VolumeFlowRate",
             0.0, 400.0 if flow_unit == "L-PER-MIN" else 24.0, "r", "measurement",
             value=180.0 if flow_unit == "L-PER-MIN" else 10.8),
        _sig(line, "FIL", "LIC0304", "SP", "Bowl level setpoint", "PERCENT", "DimensionlessRatio",
             10.0, 90.0, "rw", "setpoint", value=62.0),
        _sig(line, "FIL", "LT0304", "PV", "Bowl level", "PERCENT", "DimensionlessRatio",
             0.0, 100.0, "r", "measurement", alarm_low=15.0, alarm_high=92.0, value=61.4),
        _sig(line, "FIL", "QIC0305", "SP", "Fill volume setpoint", "MilliL", "Volume",
             200.0, 2000.0, "rw", "setpoint", value=500.0, id_short="FillVolumeSetpoint"),
        _sig(line, "FIL", "SIC0306", "SP", "Carousel speed setpoint", "REV-PER-MIN", "AngularVelocity",
             5.0, 45.0, "rw", "setpoint", value=32.0),
        _sig(line, "FIL", "ST0306", "PV", "Carousel speed", "REV-PER-MIN", "AngularVelocity",
             0.0, 50.0, "r", "measurement", value=31.8),
        _sig(line, "FIL", "XV0307", "CMD", "Product valve command", "UNITLESS", "Dimensionless",
             0.0, 1.0, "rw", "command", safety=True),
        _sig(line, "FIL", "UNIT", "STATE", "PackML unit current state", "UNITLESS", "Count",
             0.0, 17.0, "r", "state"),
        _sig(line, "FIL", "UNIT", "CMD", "PackML unit command", "UNITLESS", "Count",
             0.0, 9.0, "rw", "command", safety=True),
        _sig(line, "FIL", "KPI0308", "OEE", "Overall equipment effectiveness", "PERCENT",
             "DimensionlessRatio", 0.0, 100.0, "r", "kpi", value=78.5),
    )


def _capper(line: str, torque_hi: float) -> tuple[Signal, ...]:
    return (
        _sig(line, "CAP", "TQ0401", "PV", "Capping torque", "N-M", "Torque",
             0.0, torque_hi, "r", "measurement", alarm_low=1.4, alarm_high=2.8, value=2.05),
        _sig(line, "CAP", "TQC0401", "SP", "Capping torque setpoint", "N-M", "Torque",
             0.8, 3.2, "rw", "setpoint", value=2.10),
        _sig(line, "CAP", "ST0402", "PV", "Head speed", "REV-PER-MIN", "AngularVelocity",
             0.0, 60.0, "r", "measurement", value=32.0),
        _sig(line, "CAP", "UNIT", "STATE", "PackML unit current state", "UNITLESS", "Count",
             0.0, 17.0, "r", "state"),
        _sig(line, "CAP", "UNIT", "CMD", "PackML unit command", "UNITLESS", "Count",
             0.0, 9.0, "rw", "command", safety=True),
    )


def _pasteuriser(line: str, temp_unit: str, press_unit: str,
                 pu_value: float = 22.4) -> tuple[Signal, ...]:
    hi_p = 10.0 if press_unit == "BAR" else 145.0
    return (
        _sig(line, "PAS", "TT0101", "PV", "Zone 1 temperature", temp_unit, "Temperature",
             0.0, 100.0 if temp_unit == "DEG_C" else 212.0, "r", "measurement",
             alarm_low=60.0 if temp_unit == "DEG_C" else 140.0, value=72.0 if temp_unit == "DEG_C" else 161.6),
        _sig(line, "PAS", "TIC0101", "SP", "Zone 1 temperature setpoint", temp_unit, "Temperature",
             20.0 if temp_unit == "DEG_C" else 68.0,
             95.0 if temp_unit == "DEG_C" else 203.0, "rw", "setpoint",
             safety=True, value=72.0 if temp_unit == "DEG_C" else 161.6),
        _sig(line, "PAS", "PT0102", "PV", "Outlet pressure", press_unit, "Pressure",
             0.0, hi_p, "r", "measurement", alarm_high=hi_p * 0.8, value=hi_p * 0.31),
        _sig(line, "PAS", "PU0103", "PV", "Accumulated pasteurisation units", "UNITLESS",
             "Count", 0.0, 60.0, "r", "kpi", alarm_low=15.0, value=pu_value),
        _sig(line, "PAS", "UNIT", "STATE", "PackML unit current state", "UNITLESS", "Count",
             0.0, 17.0, "r", "state"),
        _sig(line, "PAS", "UNIT", "CMD", "PackML unit command", "UNITLESS", "Count",
             0.0, 9.0, "rw", "command", safety=True),
    )


def _labeller(line: str) -> tuple[Signal, ...]:
    return (
        _sig(line, "LAB", "ST0501", "PV", "Carousel speed", "REV-PER-MIN", "AngularVelocity",
             0.0, 55.0, "r", "measurement", value=31.5),
        _sig(line, "LAB", "ZT0502", "PV", "Label position deviation", "MilliM", "Length",
             -5.0, 5.0, "r", "measurement", alarm_low=-1.5, alarm_high=1.5, value=0.4),
        _sig(line, "LAB", "CNT0503", "PV", "Reject count", "NUM", "Count",
             0.0, 1e6, "r", "kpi", value=142.0),
        _sig(line, "LAB", "UNIT", "STATE", "PackML unit current state", "UNITLESS", "Count",
             0.0, 17.0, "r", "state"),
        _sig(line, "LAB", "UNIT", "CMD", "PackML unit command", "UNITLESS", "Count",
             0.0, 9.0, "rw", "command", safety=True),
    )


def _cip(line: str, temp_unit: str, flow_unit: str) -> tuple[Signal, ...]:
    return (
        _sig(line, "CIP", "TT0601", "PV", "Return temperature", temp_unit, "Temperature",
             0.0, 100.0 if temp_unit == "DEG_C" else 212.0, "r", "measurement",
             alarm_low=68.0 if temp_unit == "DEG_C" else 154.4, value=79.0 if temp_unit == "DEG_C" else 174.2),
        _sig(line, "CIP", "FT0602", "PV", "Return flow", flow_unit, "VolumeFlowRate",
             0.0, 600.0 if flow_unit == "L-PER-MIN" else 36.0, "r", "measurement",
             alarm_low=250.0 if flow_unit == "L-PER-MIN" else 15.0,
             value=410.0 if flow_unit == "L-PER-MIN" else 24.6),
        _sig(line, "CIP", "AT0603", "PV", "Caustic concentration", "PERCENT", "DimensionlessRatio",
             0.0, 5.0, "r", "measurement", alarm_low=1.8, alarm_high=2.6, value=2.1),
        _sig(line, "CIP", "AT0604", "PV", "Return pH", "PH", "Acidity",
             0.0, 14.0, "r", "measurement", value=12.4),
        _sig(line, "CIP", "UNIT", "STATE", "PackML unit current state", "UNITLESS", "Count",
             0.0, 17.0, "r", "state"),
        _sig(line, "CIP", "UNIT", "CMD", "PackML unit command", "UNITLESS", "Count",
             0.0, 9.0, "rw", "command", safety=True),
    )


def _utility_compressor() -> tuple[Signal, ...]:
    return (
        _sig("UT", "CMP", "PT0801", "PV", "Outlet pressure", "BAR", "Pressure",
             0.0, 12.0, "r", "measurement", alarm_low=6.0, alarm_high=10.5, value=7.8),
        _sig("UT", "CMP", "PIC0801", "SP", "Discharge pressure setpoint", "BAR", "Pressure",
             5.0, 10.0, "rw", "setpoint", value=7.5),
        _sig("UT", "CMP", "TT0802", "PV", "Discharge temperature", "DEG_C", "Temperature",
             0.0, 140.0, "r", "measurement", alarm_high=105.0, value=88.0),
        _sig("UT", "CMP", "JT0803", "PV", "Active power", "KiloW", "Power",
             0.0, 160.0, "r", "measurement", value=112.0),
        _sig("UT", "CMP", "VT0804", "PV", "Bearing vibration", "MilliM", "Length",
             0.0, 20.0, "r", "measurement", alarm_high=7.1, value=3.2),
    )


def _chiller() -> tuple[Signal, ...]:
    return (
        _sig("UT", "CHL", "TT0901", "PV", "Chilled water supply temperature", "DEG_C", "Temperature",
             -10.0, 30.0, "r", "measurement", alarm_high=8.0, value=4.2),
        _sig("UT", "CHL", "TIC0901", "SP", "Chilled water supply setpoint", "DEG_C", "Temperature",
             0.0, 12.0, "rw", "setpoint", value=4.0),
        _sig("UT", "CHL", "FT0902", "PV", "Chilled water flow", "M3-PER-HR", "VolumeFlowRate",
             0.0, 120.0, "r", "measurement", value=84.0),
        _sig("UT", "CHL", "JT0903", "PV", "Active power", "KiloW", "Power",
             0.0, 400.0, "r", "measurement", value=241.0),
    )


def build_plant() -> tuple[Asset, ...]:
    """Return the full asset list, parents before children."""
    assets: list[Asset] = [
        Asset("ENT", "Global Beverages AG", "Enterprise", "-", "-", "-",
              "27-01-01-01", None, "Enterprise", location="DE"),
        Asset("SITE-KA", "Karlsruhe Bottling Plant", "Site", "-", "-", "-",
              "27-01-01-02", "ENT", "Site", location="Karlsruhe, DE"),
        Asset("AREA-FILL", "Filling Hall", "Area", "-", "-", "-",
              "27-01-01-03", "SITE-KA", "Area", location="Building 3"),
        Asset("AREA-UTIL", "Utilities", "Area", "-", "-", "-",
              "27-01-01-04", "SITE-KA", "Area", location="Building 1"),
    ]

    # ---- Line 1: metric units, 0.5 L PET ---------------------------------
    assets.append(Asset("L1", "Bottling Line 1", "ProductionLine", "-", "-", "-",
                        "27-02-24-01", "AREA-FILL", "WorkCenter",
                        location="Filling Hall / Bay A", criticality="high"))
    assets += [
        Asset("L1-PAS", "Line 1 Tunnel Pasteuriser", "Pasteuriser", "KHS GmbH",
              "Innopas SX", "PAS-2019-4471", "36-05-01-01", "L1", "WorkUnit",
              signals=_pasteuriser("L1", "DEG_C", "BAR"), packml_capable=True,
              packml_state="Execute", mtp_services=("Heat", "Hold", "Cool"),
              commissioned="2019-04-11", criticality="high"),
        Asset("L1-FIL", "Line 1 Rotary Filler", "Filler", "Krones AG",
              "Modulfill VFS-C 72/12", "FIL-2021-8823", "36-05-02-01", "L1", "WorkUnit",
              signals=_filler("L1", "BAR", "DEG_C", "L-PER-MIN"), packml_capable=True,
              packml_state="Execute", mtp_services=("Fill", "Flush", "CIP"),
              commissioned="2021-07-02", criticality="high"),
        Asset("L1-CAP", "Line 1 Capper", "Capper", "Krones AG",
              "Modulcap 12", "CAP-2021-8824", "36-05-02-04", "L1", "WorkUnit",
              signals=_capper("L1", 4.0), packml_capable=True, packml_state="Execute",
              commissioned="2021-07-02"),
        Asset("L1-LAB", "Line 1 Labeller", "Labeller", "Krones AG",
              "Contiroll HS", "LAB-2021-8825", "36-05-02-06", "L1", "WorkUnit",
              signals=_labeller("L1"), packml_capable=True, packml_state="Held",
              commissioned="2021-07-02"),
        Asset("L1-CIP", "Line 1 CIP Skid", "CIPSkid", "GEA Group",
              "ECOclean 3000", "CIP-2020-1190", "36-05-08-02", "L1", "WorkUnit",
              signals=_cip("L1", "DEG_C", "L-PER-MIN"), packml_capable=True,
              packml_state="Idle", mtp_services=("PreRinse", "Caustic", "Rinse", "Acid"),
              commissioned="2020-02-20"),
    ]

    # ---- Line 2: imperial units (retrofitted US line), 1 L glass ----------
    assets.append(Asset("L2", "Bottling Line 2", "ProductionLine", "-", "-", "-",
                        "27-02-24-01", "AREA-FILL", "WorkCenter",
                        location="Filling Hall / Bay B", criticality="medium"))
    assets += [
        Asset("L2-PAS", "Line 2 Tunnel Pasteuriser", "Pasteuriser", "Sidel",
              "Gebo Pasteuriser", "PAS-2016-2210", "36-05-01-01", "L2", "WorkUnit",
              signals=_pasteuriser("L2", "DEG_F", "PSI", pu_value=8.5), packml_capable=True,
              packml_state="Idle", mtp_services=("Heat", "Hold", "Cool"),
              commissioned="2016-09-30", criticality="high"),
        Asset("L2-FIL", "Line 2 Rotary Filler", "Filler", "Sidel",
              "EvoFILL Glass", "FIL-2016-2211", "36-05-02-01", "L2", "WorkUnit",
              signals=_filler("L2", "PSI", "DEG_F", "M3-PER-HR"), packml_capable=True,
              packml_state="Stopped", mtp_services=("Fill", "Flush", "CIP"),
              commissioned="2016-09-30", criticality="high"),
        Asset("L2-CAP", "Line 2 Crowner", "Capper", "Sidel",
              "EvoCAP", "CAP-2016-2212", "36-05-02-04", "L2", "WorkUnit",
              signals=_capper("L2", 5.0), packml_capable=True, packml_state="Stopped",
              commissioned="2016-09-30"),
        Asset("L2-LAB", "Line 2 Labeller", "Labeller", "Sidel",
              "Evolabel", "LAB-2016-2213", "36-05-02-06", "L2", "WorkUnit",
              signals=_labeller("L2"), packml_capable=True, packml_state="Aborted",
              commissioned="2016-09-30"),
    ]

    # ---- Utilities --------------------------------------------------------
    assets += [
        Asset("UT-CMP", "Compressed Air Compressor 1", "Compressor", "Atlas Copco",
              "ZR 160 VSD+", "CMP-2018-0091", "36-01-03-01", "AREA-UTIL", "WorkUnit",
              signals=_utility_compressor(), commissioned="2018-05-14", criticality="high"),
        Asset("UT-CHL", "Chiller 1", "Chiller", "Johnson Controls",
              "YMC2 Magnetic Bearing", "CHL-2017-0442", "36-01-05-02", "AREA-UTIL", "WorkUnit",
              signals=_chiller(), commissioned="2017-03-08", criticality="high"),
    ]
    return tuple(assets)


PLANT: tuple[Asset, ...] = build_plant()
ASSETS_BY_ID: dict[str, Asset] = {a.local_id: a for a in PLANT}
ALL_SIGNALS: tuple[Signal, ...] = tuple(s for a in PLANT for s in a.signals)
SIGNAL_OWNER: dict[str, str] = {s.tag: a.local_id for a in PLANT for s in a.signals}


# ---------------------------------------------------------------------------
# Cross-asset facts that only a graph can express
# ---------------------------------------------------------------------------

#: material / utility flow, ``(upstream, downstream)`` - Brick ``feeds``
FEEDS: tuple[tuple[str, str], ...] = (
    ("L1-PAS", "L1-FIL"),
    ("L1-FIL", "L1-CAP"),
    ("L1-CAP", "L1-LAB"),
    ("L2-PAS", "L2-FIL"),
    ("L2-FIL", "L2-CAP"),
    ("L2-CAP", "L2-LAB"),
    ("UT-CMP", "L1-FIL"),
    ("UT-CMP", "L2-FIL"),
    ("UT-CMP", "L1-CAP"),
    ("UT-CHL", "L1-FIL"),
    ("UT-CHL", "L2-FIL"),
    ("UT-CHL", "L1-PAS"),
    ("L1-CIP", "L1-FIL"),
    ("L1-CIP", "L1-PAS"),
)

#: safety / process interlocks: writing ``tag`` is only permitted when the
#: guard condition holds. Invisible in a flat tag list; explicit in the KG.
INTERLOCKS: tuple[dict[str, object], ...] = (
    {
        "id": "ILK-01",
        "tag": "L1_FIL_XV0307_CMD",
        "guard_tag": "L1_PAS_PU0103_PV",
        "operator": ">=",
        "threshold": 15.0,
        "text": "Product valve may only open when accumulated pasteurisation units >= 15 PU.",
    },
    {
        "id": "ILK-02",
        "tag": "L1_FIL_QIC0305_SP",
        "guard_tag": "L1_FIL_UNIT_STATE",
        "operator": "state_in",
        "threshold": ("Idle", "Held", "Stopped"),
        "text": "Fill volume setpoint may only be changed while the filler is Idle, Held or Stopped.",
    },
    {
        "id": "ILK-03",
        "tag": "L1_PAS_TIC0101_SP",
        "guard_tag": "L1_CIP_UNIT_STATE",
        "operator": "state_not_in",
        "threshold": ("Execute",),
        "text": "Pasteuriser temperature setpoint is locked while a CIP cycle is executing.",
    },
    {
        "id": "ILK-04",
        "tag": "L2_FIL_XV0307_CMD",
        "guard_tag": "L2_PAS_PU0103_PV",
        "operator": ">=",
        "threshold": 15.0,
        "text": "Product valve may only open when accumulated pasteurisation units >= 15 PU.",
    },
)

#: product / recipe context (ISA-88 recipe parameters bound to equipment)
PRODUCTS: tuple[dict[str, object], ...] = (
    {
        "id": "P-COLA-500",
        "name": "Cola 0.5 L PET",
        "line": "L1",
        "fill_volume_ml": 500.0,
        "fill_pressure_bar": 2.5,
        "product_temperature_degC": 4.0,
        "cap_torque_nm": 2.1,
        "target_rate_bph": 36000,
    },
    {
        "id": "P-LEMON-1000",
        "name": "Lemonade 1.0 L Glass",
        "line": "L2",
        "fill_volume_ml": 1000.0,
        "fill_pressure_bar": 2.2,
        "product_temperature_degC": 6.0,
        "cap_torque_nm": 2.4,
        "target_rate_bph": 18000,
    },
)

#: recent maintenance / event log, used for multi-hop provenance questions
EVENTS: tuple[dict[str, str], ...] = (
    {"id": "EV-1001", "asset": "L1-FIL", "ts": "2026-07-14T02:15:00Z", "type": "Alarm",
     "text": "Bowl level low-low, filler held", "severity": "high"},
    {"id": "EV-1002", "asset": "UT-CMP", "ts": "2026-07-14T02:11:30Z", "type": "Alarm",
     "text": "Discharge pressure below low limit", "severity": "high"},
    {"id": "EV-1003", "asset": "UT-CMP", "ts": "2026-06-30T09:00:00Z", "type": "Maintenance",
     "text": "Air-end bearing replaced, vibration baseline reset", "severity": "info"},
    {"id": "EV-1004", "asset": "L1-CAP", "ts": "2026-07-14T02:16:10Z", "type": "Alarm",
     "text": "Capping torque out of range on head 7", "severity": "medium"},
    {"id": "EV-1005", "asset": "L2-LAB", "ts": "2026-07-02T18:40:00Z", "type": "Alarm",
     "text": "Emergency stop pressed, unit aborted", "severity": "high"},
    {"id": "EV-1006", "asset": "L1-PAS", "ts": "2026-07-14T02:09:45Z", "type": "Alarm",
     "text": "Zone 1 temperature below limit", "severity": "medium"},
)
