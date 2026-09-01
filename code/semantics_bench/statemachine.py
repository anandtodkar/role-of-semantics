"""The PackML (ISA-88 / OMAC) state machine as an executable behavioural model.

Information models such as OPC UA, the AAS and the MTP describe *structure*.
PackML contributes something an LLM agent needs just as badly: legal
*behaviour*.  Encoding the state machine explicitly turns "is this command
allowed right now?" from a plausibility judgement into a lookup.

States are grouped as in ISA-88 / PackML (ANSI/ISA-TR88.00.02):
    acting states     - transition automatically on state-complete (SC)
    wait states       - remain until an external command arrives
"""

from __future__ import annotations

from dataclasses import dataclass

WAIT_STATES = ("Stopped", "Idle", "Suspended", "Execute", "Held", "Complete", "Aborted")
ACTING_STATES = (
    "Clearing",
    "Starting",
    "Suspending",
    "Unsuspending",
    "Holding",
    "Unholding",
    "Stopping",
    "Aborting",
    "Resetting",
    "Completing",
)
STATES = tuple(sorted(set(WAIT_STATES + ACTING_STATES)))

COMMANDS = ("Reset", "Start", "Stop", "Hold", "Unhold", "Suspend", "Unsuspend", "Abort", "Clear")

#: command-driven transitions, ``(state, command) -> next state``
COMMAND_TRANSITIONS: dict[tuple[str, str], str] = {
    ("Aborted", "Clear"): "Clearing",
    ("Stopped", "Reset"): "Resetting",
    ("Complete", "Reset"): "Resetting",
    ("Idle", "Start"): "Starting",
    ("Execute", "Hold"): "Holding",
    ("Held", "Unhold"): "Unholding",
    ("Execute", "Suspend"): "Suspending",
    ("Suspended", "Unsuspend"): "Unsuspending",
}

#: state-complete transitions taken autonomously by the unit
SC_TRANSITIONS: dict[str, str] = {
    "Clearing": "Stopped",
    "Resetting": "Idle",
    "Starting": "Execute",
    "Holding": "Held",
    "Unholding": "Execute",
    "Suspending": "Suspended",
    "Unsuspending": "Execute",
    "Stopping": "Stopped",
    "Aborting": "Aborted",
    "Completing": "Complete",
}

#: ``Stop`` and ``Abort`` are accepted from every state except their own targets
_UNIVERSAL = {
    "Stop": ("Stopping", frozenset({"Stopped", "Stopping", "Aborted", "Aborting", "Clearing"})),
    "Abort": ("Aborting", frozenset({"Aborted", "Aborting"})),
}


@dataclass(frozen=True)
class TransitionResult:
    allowed: bool
    next_state: str | None
    reason: str


def legal_commands(state: str) -> tuple[str, ...]:
    """All commands accepted in ``state`` (the agent's legal action space)."""
    if state not in STATES:
        return ()
    out = [c for (s, c) in COMMAND_TRANSITIONS if s == state]
    for cmd, (_target, forbidden) in _UNIVERSAL.items():
        if state not in forbidden:
            out.append(cmd)
    return tuple(sorted(set(out)))


def step(state: str, command: str) -> TransitionResult:
    """Evaluate a command against the PackML state machine."""
    if state not in STATES:
        return TransitionResult(False, None, f"unknown state {state!r}")
    if command not in COMMANDS:
        return TransitionResult(False, None, f"unknown PackML command {command!r}")
    if command in _UNIVERSAL:
        target, forbidden = _UNIVERSAL[command]
        if state in forbidden:
            return TransitionResult(
                False, None, f"{command} is not accepted in state {state}"
            )
        return TransitionResult(True, target, f"{state} --{command}--> {target}")
    key = (state, command)
    if key in COMMAND_TRANSITIONS:
        target = COMMAND_TRANSITIONS[key]
        return TransitionResult(True, target, f"{state} --{command}--> {target}")
    return TransitionResult(
        False,
        None,
        f"{command} is illegal in state {state}; legal commands are "
        f"{', '.join(legal_commands(state))}",
    )


def settle(state: str, max_steps: int = 10) -> str:
    """Follow state-complete transitions until a wait state is reached."""
    seen = 0
    while state in SC_TRANSITIONS and seen < max_steps:
        state = SC_TRANSITIONS[state]
        seen += 1
    return state


def reachable(start: str, goal: str, max_depth: int = 12) -> list[str] | None:
    """Shortest command sequence from ``start`` to ``goal`` (BFS), or ``None``.

    Used to test whether an agent's proposed multi-step plan is realisable.
    """
    if start == goal:
        return []
    frontier: list[tuple[str, list[str]]] = [(start, [])]
    visited = {start}
    while frontier:
        state, path = frontier.pop(0)
        if len(path) >= max_depth:
            continue
        for cmd in legal_commands(state):
            res = step(state, cmd)
            if not res.allowed or res.next_state is None:
                continue
            nxt = settle(res.next_state)
            if nxt == goal:
                return path + [cmd]
            if nxt not in visited:
                visited.add(nxt)
                frontier.append((nxt, path + [cmd]))
    return None
