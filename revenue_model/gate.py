"""The unified gate system (v0.21b): state on disk + --resume.

All gates — documents (Gate H), tags, stories — share one state machine.
A run that hits a waiting gate saves its state and returns; the analyst
answers (or delegates) out of band; `resume` writes the answers back with
their authority recorded and the pipeline continues. Because digestion is
page-cached, "continue" is cheap: re-running only pays for unseen pages.

The coverage checklist (Principle 0) lives in the same state file and is
rendered in the report at the same loudness as warnings.
"""
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

WAITING = "waiting"
ANSWERED = "answered"
PENDING = "pending"
CLEARED = "cleared"

# canonical gate names (documents = Gate H proper)
GATE_DOCUMENTS, GATE_TAGS, GATE_STORIES = "documents", "tags", "stories"

STATE_FILE = "state.json"


@dataclass
class Gate:
    gate: str
    status: str = PENDING
    ask: str = ""
    options: List[str] = field(default_factory=list)
    answer: Optional[str] = None
    authority: Optional[str] = None    # "user" | "user-delegated" | None


@dataclass
class GateBook:
    """state.json's shape + load/save. One workdir per (company, run)."""
    company: str
    stage: str = "start"
    gates: List[Gate] = field(default_factory=list)
    coverage: Dict[str, str] = field(default_factory=dict)
    workdir: Path = Path(".")

    # -- persistence -------------------------------------------------------
    @classmethod
    def load(cls, workdir: Path) -> "GateBook":
        p = Path(workdir) / STATE_FILE
        d = json.loads(p.read_text(encoding="utf-8"))
        gates = [Gate(**g) for g in d.pop("gates")]
        return cls(workdir=Path(workdir), gates=gates, **d)

    def save(self) -> Path:
        p = self.workdir / STATE_FILE
        p.parent.mkdir(parents=True, exist_ok=True)
        d = {k: v for k, v in asdict(self).items() if k != "workdir"}
        tmp = p.parent / f".{STATE_FILE}.tmp"
        tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        tmp.replace(p)
        return p

    # -- gate lifecycle ------------------------------------------------------
    def ask(self, gate_name: str, question: str, options: List[str]) -> None:
        """Register (or refresh) a waiting gate and persist state."""
        g = self._get(gate_name)
        g.status, g.ask, g.options = WAITING, question, list(options)
        g.answer, g.authority = None, None
        self.save()

    def answer(self, gate_name: str, answer: str,
               *, authority: str = "user") -> None:
        """Record the analyst's answer; 'I don't know either — search and
        judge yourself' maps to authority=user-delegated."""
        g = self._get(gate_name)
        if g.status != WAITING:
            raise ValueError(f"gate {gate_name!r} is {g.status}, not waiting")
        g.status, g.answer = ANSWERED, answer
        g.authority = ("user-delegated"
                       if "search and judge" in answer.lower() else authority)
        self.save()

    def _get(self, gate_name: str) -> Gate:
        for g in self.gates:
            if g.gate == gate_name:
                return g
        g = Gate(gate=gate_name)
        self.gates.append(g)
        return g

    # -- queries ----------------------------------------------------------
    def waiting(self) -> List[Gate]:
        return [g for g in self.gates if g.status == WAITING]

    def answered_answer(self, gate_name: str) -> Optional[str]:
        g = self._get(gate_name)
        return g.answer if g.status == ANSWERED else None

    # -- coverage (Principle 0) ---------------------------------------------
    def cover(self, item: str, status: str) -> None:
        """status: ok | present | absent | absent-user-approved.
        Persists immediately — the state file is the single source of
        truth; a crash mid-run must not lose coverage honesty."""
        self.coverage[item] = status
        self.save()

    def absent_items(self) -> Dict[str, str]:
        return {k: v for k, v in self.coverage.items()
                if v.startswith("absent")}


def default_document_options() -> List[str]:
    """The Gate H option set — the stop-and-ask protocol, verbatim."""
    return [
        "dropped the file(s) into the queue directory",
        "can't get it either — proceed on what exists",
        "I don't know either — search and judge yourself",
    ]
