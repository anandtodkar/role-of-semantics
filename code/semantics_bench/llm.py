"""Optional adapter for running the task suite against a real language model.

Deliberately not used for any number in the paper: a single model's score would
date the results and would not support a claim about *representations*.  It
exists so that a reader with a model in hand can confirm the central prediction
--- that measured accuracy tracks, and never exceeds, the context-sufficiency
ceiling of :mod:`semantics_bench.experiments`.

Supported backends, selected by environment variable:

===================  =========================================================
``SEMBENCH_BACKEND`` behaviour
===================  =========================================================
``mock`` (default)   no network; answers only from the supplied context
``openai``           any OpenAI-compatible ``/v1/chat/completions`` endpoint
                     (``OPENAI_BASE_URL``, ``OPENAI_API_KEY``, ``SEMBENCH_MODEL``)
``ollama``           a local Ollama server (``OLLAMA_HOST``, ``SEMBENCH_MODEL``)
===================  =========================================================

Usage::

    from semantics_bench import llm, conditions as C, tasks as TK, retrieval as R
    backend = llm.get_backend()
    result  = llm.run_suite(backend, condition="C4")
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Protocol

from . import conditions as C
from . import retrieval as R
from . import tasks as TK
from . import validation as V
from .toolgen import write_tool_schema

SYSTEM_PROMPT = """You are an industrial plant assistant operating on a live
bottling line. You answer ONLY from the CONTEXT provided below.

Rules:
1. If the context does not contain a fact you need, reply exactly:
   INSUFFICIENT: <the fact you are missing>
2. Every numeric answer must carry a unit and name the tag it came from.
3. Never propose an action without checking access mode, engineering range,
   unit compatibility, interlocks and the current PackML state.
4. Do not infer asset membership from tag-name conventions; use the stated
   relations only."""


class Backend(Protocol):
    name: str

    def complete(self, system: str, user: str) -> str: ...


@dataclass
class MockBackend:
    """A reader that is perfect at reading and incapable of inventing.

    Reproduces the ceiling analysis end-to-end: it answers when the required
    facts are present and refuses otherwise.
    """

    name: str = "mock"
    _facts: set[str] = field(default_factory=set)
    _task: TK.Task | None = None

    def bind(self, task: TK.Task, facts: set[str]) -> None:
        self._task, self._facts = task, facts

    def complete(self, system: str, user: str) -> str:
        if self._task is None:
            return "INSUFFICIENT: no task bound"
        missing = set(self._task.required) - self._facts
        if missing:
            return "INSUFFICIENT: " + ", ".join(sorted(missing)[:3])
        return self._task.gold_answer


@dataclass
class HTTPBackend:
    name: str
    url: str
    model: str
    api_key: str | None = None
    timeout: int = 120
    header_style: str = "bearer"  # "bearer" (OpenAI/Ollama) | "azure" (api-key)
    temperature: float | None = 0.0
    send_model: bool = True  # Azure takes the deployment from the URL, not the body

    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self.api_key:
            if self.header_style == "azure":
                h["api-key"] = self.api_key
            else:
                h["Authorization"] = f"Bearer {self.api_key}"
        return h

    def _post(self, payload: dict) -> dict:
        req = urllib.request.Request(
            self.url, data=json.dumps(payload).encode("utf-8"),
            headers=self._headers(), method="POST")
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def complete(self, system: str, user: str) -> str:
        payload: dict = {"messages": [{"role": "system", "content": system},
                                      {"role": "user", "content": user}]}
        if self.send_model:
            payload["model"] = self.model
        if self.temperature is not None:
            payload["temperature"] = self.temperature
        try:
            body = self._post(payload)
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8")
            except Exception:
                pass
            # Some reasoning models reject temperature != 1; retry once without it.
            if "temperature" in detail and "temperature" in payload:
                payload.pop("temperature", None)
                try:
                    body = self._post(payload)
                except Exception as exc2:
                    return f"ERROR: {exc2}"
            else:
                return f"ERROR: HTTP {exc.code}: {detail[:300]}"
        except (urllib.error.URLError, TimeoutError) as exc:
            return f"ERROR: {exc}"
        if "choices" in body:
            msg = body["choices"][0].get("message", {})
            return msg.get("content") or ""
        return body.get("message", {}).get("content", json.dumps(body))


def load_dotenv(path: str | None = None) -> None:
    """Populate os.environ from a local .env file if present (no dependency).

    Looks for ``code/.env`` by default. Never overwrites a variable already set
    in the environment. The .env file is git-ignored and must never be committed:
    it is where the Azure/OpenAI API key lives on the local machine.
    """
    from pathlib import Path
    p = Path(path) if path else Path(__file__).resolve().parent.parent / ".env"
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        os.environ.setdefault(key, val)


def get_backend() -> Backend:
    kind = os.environ.get("SEMBENCH_BACKEND", "mock").lower()
    model = os.environ.get("SEMBENCH_MODEL", "gpt-4o-mini")
    if kind == "openai":
        base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        return HTTPBackend("openai", f"{base}/chat/completions", model,
                           os.environ.get("OPENAI_API_KEY"))
    if kind == "azure":
        endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT", "").rstrip("/")
        deployment = os.environ.get("AZURE_OPENAI_DEPLOYMENT", model)
        api_version = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")
        url = (f"{endpoint}/openai/deployments/{deployment}"
               f"/chat/completions?api-version={api_version}")
        return HTTPBackend(f"azure:{deployment}", url, deployment,
                           os.environ.get("AZURE_OPENAI_API_KEY"),
                           header_style="azure", send_model=False)
    if kind == "ollama":
        host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        return HTTPBackend("ollama", f"{host}/v1/chat/completions", model)
    return MockBackend()


def build_prompt(task: TK.Task, cond: C.Condition, budget: int = 6000) -> tuple[str, set[str], int]:
    els = R.retrieve(task.question, cond, 200)
    text, facts, tokens = C.build_context(els, cond, budget)
    prompt = (f"CONTEXT ({cond.label}, {tokens} tokens)\n"
              f"{'-' * 60}\n{text}\n{'-' * 60}\n\n"
              f"QUESTION: {task.question}\nANSWER:")
    return prompt, facts, tokens


def run_suite(backend: Backend, condition: str = "C4", budget: int = 6000) -> list[dict]:
    cond = C.BY_KEY[condition]
    out = []
    for task in TK.TASKS:
        prompt, facts, tokens = build_prompt(task, cond, budget)
        if isinstance(backend, MockBackend):
            backend.bind(task, facts)
        answer = backend.complete(SYSTEM_PROMPT, prompt)
        out.append({
            "task": task.tid, "category": task.category, "condition": condition,
            "tokens": tokens,
            "context_sufficient": not (set(task.required) - facts),
            "refused": answer.strip().startswith("INSUFFICIENT"),
            "answer": answer.strip()[:400],
            "gold": task.gold_answer,
        })
    return out


def action_tool_schema(condition: str = "C4", scope: str = "L1") -> dict:
    """The tool definition an agent would be given under a condition."""
    return write_tool_schema(condition, scope)


def validate_proposal(payload: dict) -> tuple[bool, list[str]]:
    """Validate a single proposed action with the full G4 stack.

    This is the function an MCP server would call before executing anything.
    """
    kind = {"write_setpoint": "write", "packml_command": "command",
            "answer": "answer"}.get(str(payload.get("action")), "write")
    case = V.Case("PROBE", kind, V.VALID, dict(payload))
    cases, _meta = V.evaluate([case])
    c = cases[0]
    return (not c.detected_by["G4"]), c.families.get("G4", [])
