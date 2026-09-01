"""A QUDT-shaped unit and dimension calculus.

This module implements the part of QUDT that actually matters for grounding an
LLM agent: every unit carries (i) a *dimension vector* over the seven SI base
quantities and (ii) an affine conversion to the coherent SI unit, exactly as
``qudt:conversionMultiplier`` / ``qudt:conversionOffset`` do.  Two quantities may
only be compared, added, or substituted for one another when their dimension
vectors are equal - the single most common class of silent error in
LLM-generated industrial commands.

Dimension vector order: (L, M, T, I, Theta, N, J)
    L      length              metre
    M      mass                kilogram
    T      time                second
    I      electric current    ampere
    Theta  thermodynamic temp. kelvin
    N      amount of substance mole
    J      luminous intensity  candela
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

DIM_NAMES = ("L", "M", "T", "I", "Theta", "N", "J")
Dimension = tuple[int, int, int, int, int, int, int]

DIMENSIONLESS: Dimension = (0, 0, 0, 0, 0, 0, 0)


def dim(**kwargs: int) -> Dimension:
    return tuple(int(kwargs.get(name, 0)) for name in DIM_NAMES)  # type: ignore[return-value]


# --- Quantity kinds (subset of qudt:QuantityKind relevant to a bottling line) --
QUANTITY_KINDS: dict[str, Dimension] = {
    "Pressure": dim(L=-1, M=1, T=-2),
    "Temperature": dim(Theta=1),
    "Volume": dim(L=3),
    "VolumeFlowRate": dim(L=3, T=-1),
    "MassFlowRate": dim(M=1, T=-1),
    "Mass": dim(M=1),
    "Length": dim(L=1),
    "Time": dim(T=1),
    "AngularVelocity": dim(T=-1),
    "Frequency": dim(T=-1),
    "Power": dim(L=2, M=1, T=-3),
    "Energy": dim(L=2, M=1, T=-2),
    "Torque": dim(L=2, M=1, T=-2),
    "Voltage": dim(L=2, M=1, T=-3, I=-1),
    "ElectricCurrent": dim(I=1),
    "Dimensionless": DIMENSIONLESS,
    "DimensionlessRatio": DIMENSIONLESS,
    "Force": dim(L=1, M=1, T=-2),
    "Density": dim(L=-3, M=1),
    "Acidity": DIMENSIONLESS,  # pH
    "Count": DIMENSIONLESS,
}


@dataclass(frozen=True)
class Unit:
    """A unit of measure with a QUDT-compatible affine conversion to SI."""

    iri_local: str  # local name inside http://qudt.org/vocab/unit/
    symbol: str
    quantity_kind: str
    multiplier: float  # value_SI = value * multiplier + offset
    offset: float = 0.0
    aliases: tuple[str, ...] = ()

    @property
    def dimension(self) -> Dimension:
        return QUANTITY_KINDS[self.quantity_kind]

    def to_si(self, value: float) -> float:
        return value * self.multiplier + self.offset

    def from_si(self, value_si: float) -> float:
        return (value_si - self.offset) / self.multiplier


_UNIT_LIST: tuple[Unit, ...] = (
    # pressure
    Unit("PA", "Pa", "Pressure", 1.0, aliases=("pascal", "pascals")),
    Unit("KiloPA", "kPa", "Pressure", 1e3, aliases=("kilopascal",)),
    Unit("MegaPA", "MPa", "Pressure", 1e6, aliases=("megapascal",)),
    Unit("BAR", "bar", "Pressure", 1e5, aliases=("bars",)),
    Unit("MilliBAR", "mbar", "Pressure", 1e2, aliases=("millibar",)),
    Unit("PSI", "psi", "Pressure", 6894.757293168, aliases=("lbf/in2", "pounds per square inch")),
    # temperature (affine!)
    Unit("K", "K", "Temperature", 1.0, 0.0, aliases=("kelvin",)),
    Unit("DEG_C", "degC", "Temperature", 1.0, 273.15, aliases=("c", "celsius", "°c", "deg c")),
    Unit("DEG_F", "degF", "Temperature", 5.0 / 9.0, 255.372222222, aliases=("f", "fahrenheit", "°f")),
    # volume
    Unit("M3", "m3", "Volume", 1.0, aliases=("m^3", "cubic metre", "cubic meter")),
    Unit("L", "L", "Volume", 1e-3, aliases=("l", "litre", "liter", "litres", "liters")),
    Unit("MilliL", "mL", "Volume", 1e-6, aliases=("ml", "millilitre", "milliliter", "cl?")),
    Unit("CentiM3", "cm3", "Volume", 1e-6, aliases=("cc",)),
    # flow
    Unit("M3-PER-HR", "m3/h", "VolumeFlowRate", 1.0 / 3600.0, aliases=("m3/hr", "cubic metre per hour")),
    Unit("L-PER-MIN", "L/min", "VolumeFlowRate", 1e-3 / 60.0, aliases=("lpm", "l/min", "litres per minute")),
    Unit("L-PER-SEC", "L/s", "VolumeFlowRate", 1e-3, aliases=("lps", "l/s")),
    Unit("KiloGM-PER-HR", "kg/h", "MassFlowRate", 1.0 / 3600.0, aliases=("kg/hr",)),
    # mechanical / electrical
    Unit("REV-PER-MIN", "rpm", "AngularVelocity", 1.0 / 60.0, aliases=("r/min", "revolutions per minute")),
    Unit("HZ", "Hz", "Frequency", 1.0, aliases=("hertz",)),
    Unit("KiloW", "kW", "Power", 1e3, aliases=("kilowatt",)),
    Unit("W", "W", "Power", 1.0, aliases=("watt",)),
    Unit("N-M", "N.m", "Torque", 1.0, aliases=("nm", "n*m", "newton metre")),
    Unit("V", "V", "Voltage", 1.0, aliases=("volt",)),
    Unit("A", "A", "ElectricCurrent", 1.0, aliases=("amp", "ampere")),
    Unit("KiloGM", "kg", "Mass", 1.0, aliases=("kilogram",)),
    Unit("GM", "g", "Mass", 1e-3, aliases=("gram",)),
    Unit("MilliM", "mm", "Length", 1e-3, aliases=("millimetre", "millimeter")),
    Unit("M", "m", "Length", 1.0, aliases=("metre", "meter")),
    Unit("SEC", "s", "Time", 1.0, aliases=("sec", "second")),
    Unit("MIN", "min", "Time", 60.0, aliases=("minute",)),
    Unit("HR", "h", "Time", 3600.0, aliases=("hr", "hour")),
    # dimensionless
    Unit("PERCENT", "%", "DimensionlessRatio", 0.01, aliases=("percent", "pct")),
    Unit("UNITLESS", "1", "Dimensionless", 1.0, aliases=("none", "unitless", "-")),
    Unit("PH", "pH", "Acidity", 1.0, aliases=("ph",)),
    Unit("NUM", "#", "Count", 1.0, aliases=("count", "pcs", "bottles")),
)

BY_IRI: dict[str, Unit] = {u.iri_local: u for u in _UNIT_LIST}

_BY_TOKEN: dict[str, Unit] = {}
for _u in _UNIT_LIST:
    _BY_TOKEN[_u.symbol.lower()] = _u
    _BY_TOKEN[_u.iri_local.lower()] = _u
    for _a in _u.aliases:
        _BY_TOKEN.setdefault(_a.lower(), _u)


class DimensionError(ValueError):
    """Raised when two quantities of incompatible dimension are combined."""


def lookup(token: str) -> Unit | None:
    """Resolve a free-text unit token (``"bar"``, ``"psi"``, ``"DEG_C"``)."""
    if token is None:
        return None
    return _BY_TOKEN.get(str(token).strip().lower())


def compatible(a: str, b: str) -> bool:
    """True when two unit tokens share a dimension vector."""
    ua, ub = lookup(a), lookup(b)
    if ua is None or ub is None:
        return False
    return ua.dimension == ub.dimension


def convert(value: float, from_unit: str, to_unit: str) -> float:
    """Affine QUDT conversion; raises :class:`DimensionError` on mismatch."""
    ua, ub = lookup(from_unit), lookup(to_unit)
    if ua is None:
        raise DimensionError(f"unknown source unit {from_unit!r}")
    if ub is None:
        raise DimensionError(f"unknown target unit {to_unit!r}")
    if ua.dimension != ub.dimension:
        raise DimensionError(
            f"cannot convert {ua.symbol} ({ua.quantity_kind}, {ua.dimension}) "
            f"to {ub.symbol} ({ub.quantity_kind}, {ub.dimension})"
        )
    return ub.from_si(ua.to_si(value))


def format_dimension(d: Dimension) -> str:
    parts = [f"{n}^{e}" for n, e in zip(DIM_NAMES, d) if e]
    return ".".join(parts) if parts else "1"


def units_for(quantity_kind: str) -> Iterable[Unit]:
    return (u for u in _UNIT_LIST if u.quantity_kind == quantity_kind)
