"""Tag naming schemes: turning "the convention carries the semantics" into a test.

A historian export grounds surprisingly well because a tag mnemonic such as
``L1_FIL_PT0301_PV`` encodes the plant hierarchy for a reader who knows the
convention.  That capability is real, and it is why ungrounded pipelines
demonstrate well.  It is also unverifiable and entirely dependent on the
convention being (i) legible and (ii) truthful.

This module re-tags the reference plant under five schemes drawn from real
installations, holding every description, relation, unit and value constant.
Only the identifier strings change, so any difference in grounding accuracy is
attributable to the convention alone.

======================  =====================================================
scheme                  example, and where it comes from
======================  =====================================================
``mnemonic``            ``L1_FIL_PT0301_PV`` -- ISA-5.1 style; the baseline
``opaque``              ``AI_04213`` -- sequential I/O addressing, still the
                        norm in older DCS and PLC exports
``kks``                 ``=1LCA10CP001XQ01`` -- KKS/RDS-PP plant designation;
                        rigorous, machine-readable, and unreadable by an LLM
                        that has not been taught the code
``vendor``              ``Krones.Modulfill.Ch17.Value`` -- OEM browse paths
                        surfaced verbatim through a gateway
``inconsistent``        ``L2_PAS_PT0301_PV`` for a Line 1 filler point -- the
                        adversarial case: a plant where retrofits, mergers and
                        renumbering have left the convention *looking* correct
                        while pointing at the wrong asset
======================  =====================================================

The last scheme is the important one. A reader that trusts the mnemonic is not
merely uninformed; it is confidently misinformed, and nothing in the
representation contradicts it.
"""

from __future__ import annotations

import dataclasses
from contextlib import contextmanager
from typing import Callable, Iterator

from . import conditions as C
from . import plant as P
from . import retrieval as R

SCHEMES = ("mnemonic", "opaque", "kks", "vendor", "inconsistent")

SCHEME_LABEL = {
    "mnemonic": "ISA-5.1 mnemonic (baseline)",
    "opaque": "sequential I/O address",
    "kks": "KKS / RDS-PP designation",
    "vendor": "OEM browse path",
    "inconsistent": "mnemonic, but misleading",
}

SCHEME_EXAMPLE = {
    "mnemonic": "L1\\_FIL\\_PT0301\\_PV",
    "opaque": "AI\\_04213",
    "kks": "=1LCA10CP001XQ01",
    "vendor": "Krones.Modulfill.Ch17.Value",
    "inconsistent": "L2\\_PAS\\_PT0301\\_PV",
}

#: KKS system codes, assigned per asset kind (illustrative but well formed)
_KKS_SYSTEM = {
    "Pasteuriser": "LCA", "Filler": "LCB", "Capper": "LCC",
    "Labeller": "LCD", "CIPSkid": "LCE", "Compressor": "SCA",
    "Chiller": "SCB",
}
_KKS_FUNCTION = {
    "measurement": "XQ", "setpoint": "XW", "command": "XG",
    "state": "XS", "kpi": "XK",
}
_VENDOR_ROLE = {
    "measurement": "Value", "setpoint": "Setpoint", "command": "Command",
    "state": "State", "kpi": "Kpi",
}


def _split(tag: str) -> tuple[str, str, str, str]:
    line, unit, loop, suffix = tag.split("_", 3)
    return line, unit, loop, suffix


def _scheme_mnemonic(_plant: tuple[P.Asset, ...]) -> dict[str, str]:
    return {s.tag: s.tag for a in _plant for s in a.signals}


def _scheme_opaque(_plant: tuple[P.Asset, ...]) -> dict[str, str]:
    out: dict[str, str] = {}
    n = 4001
    for a in _plant:
        for s in a.signals:
            prefix = "AO" if s.access == "rw" else "AI"
            out[s.tag] = f"{prefix}_{n:05d}"
            n += 7  # sparse, as real I/O maps are
    return out


def _scheme_kks(_plant: tuple[P.Asset, ...]) -> dict[str, str]:
    out: dict[str, str] = {}
    counters: dict[str, int] = {}
    for a in _plant:
        system = _KKS_SYSTEM.get(a.kind, "XXX")
        unit_no = 20 if str(a.local_id).startswith("L2") else 10
        for s in a.signals:
            fn = _KKS_FUNCTION.get(s.role, "XQ")
            key = f"{system}{unit_no}{fn}"
            counters[key] = counters.get(key, 0) + 1
            out[s.tag] = f"={unit_no // 10}{system}{unit_no}CP{counters[key]:03d}{fn}01"
    return out


def _scheme_vendor(_plant: tuple[P.Asset, ...]) -> dict[str, str]:
    out: dict[str, str] = {}
    counters: dict[str, int] = {}
    for a in _plant:
        maker = a.manufacturer.split()[0].replace(",", "") if a.manufacturer != "-" else "Gen"
        model = "".join(ch for ch in a.model.split()[0] if ch.isalnum()) or "Dev"
        for s in a.signals:
            counters[a.local_id] = counters.get(a.local_id, 0) + 1
            role = _VENDOR_ROLE.get(s.role, "Value")
            out[s.tag] = f"{maker}.{model}.Ch{counters[a.local_id]:02d}.{role}"
    return out


def _scheme_inconsistent(_plant: tuple[P.Asset, ...]) -> dict[str, str]:
    """Keep the mnemonic form, but attribute each point to the wrong asset.

    The prefix of every tag is rotated onto the next signal-bearing asset, so
    the convention remains syntactically perfect and semantically false. This is
    the post-merger plant, and it is common enough that most sites maintain a
    private cross-reference spreadsheet to survive it.
    """
    bearing = [a for a in _plant if a.signals]
    prefixes: list[tuple[str, str]] = []
    for a in bearing:
        line, unit, _loop, _sfx = _split(a.signals[0].tag)
        prefixes.append((line, unit))
    out: dict[str, str] = {}
    taken: set[str] = set()
    for i, a in enumerate(bearing):
        line, unit = prefixes[(i + 1) % len(prefixes)]
        for s in a.signals:
            _l, _u, loop, suffix = _split(s.tag)
            cand = f"{line}_{unit}_{loop}_{suffix}"
            bump = 0
            while cand in taken:
                bump += 1
                cand = f"{line}_{unit}_{loop}{chr(64 + bump)}_{suffix}"
            taken.add(cand)
            out[s.tag] = cand
    return out


_BUILDERS: dict[str, Callable[[tuple[P.Asset, ...]], dict[str, str]]] = {
    "mnemonic": _scheme_mnemonic,
    "opaque": _scheme_opaque,
    "kks": _scheme_kks,
    "vendor": _scheme_vendor,
    "inconsistent": _scheme_inconsistent,
}


def tag_map(scheme: str) -> dict[str, str]:
    """The old-tag to new-tag mapping for ``scheme``, computed on the base plant."""
    if scheme not in _BUILDERS:
        raise KeyError(f"unknown naming scheme {scheme!r}")
    mapping = _BUILDERS[scheme](_BASE_PLANT)
    if len(set(mapping.values())) != len(mapping):
        raise AssertionError(f"scheme {scheme!r} produced colliding tags")
    return mapping


# ---------------------------------------------------------------------------
# Applying a scheme
# ---------------------------------------------------------------------------

_BASE_PLANT: tuple[P.Asset, ...] = P.PLANT
_BASE_INTERLOCKS = P.INTERLOCKS


def _install(assets: tuple[P.Asset, ...], interlocks) -> None:
    """Swap the plant in place and rebuild every cache derived from it."""
    P.PLANT = assets
    P.ASSETS_BY_ID = {a.local_id: a for a in assets}
    P.ALL_SIGNALS = tuple(s for a in assets for s in a.signals)
    P.SIGNAL_OWNER = {s.tag: a.local_id for a in assets for s in a.signals}
    P.INTERLOCKS = interlocks
    C.ELEMENTS = C.all_elements()
    C.ELEMENT_BY_ID = {e.eid: e for e in C.ELEMENTS}
    R.ELEMENTS = C.ELEMENTS
    R.ELEMENT_BY_ID = C.ELEMENT_BY_ID
    R._LEX_CACHE.clear()
    R._DECODE_CACHE.clear()


def apply(scheme: str) -> dict[str, str]:
    """Re-tag the plant under ``scheme``; returns the tag map."""
    mapping = tag_map(scheme)
    assets = tuple(
        dataclasses.replace(
            a, signals=tuple(dataclasses.replace(s, tag=mapping[s.tag]) for s in a.signals))
        for a in _BASE_PLANT
    )
    interlocks = tuple(
        {**ilk, "tag": mapping[str(ilk["tag"])],
         "guard_tag": mapping[str(ilk["guard_tag"])]}
        for ilk in _BASE_INTERLOCKS
    )
    _install(assets, interlocks)
    return mapping


def restore() -> None:
    _install(_BASE_PLANT, _BASE_INTERLOCKS)


@contextmanager
def scheme(name: str) -> Iterator[dict[str, str]]:
    """Use a naming scheme for the duration of a block, then restore.

    ``node_id``, descriptions, units, ranges, relations, states, interlock
    semantics and observed values are untouched; only identifier strings move.
    """
    try:
        yield apply(name)
    finally:
        restore()
