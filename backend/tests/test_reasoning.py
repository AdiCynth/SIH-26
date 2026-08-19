import json

from app.scanners.base import RawFinding
from app import reasoning
from app.config import settings


def make(n=2):
    return [
        RawFinding(tool="semgrep", severity="high", file=f"a{i}.py", line=i,
                   message=f"issue {i}")
        for i in range(n)
    ]


class FakeOpenAI:
    def __init__(self, payload=None, error=None):
        self._payload, self._error = payload, error
        outer = self

        class Completions:
            def create(self, **kwargs):
                outer.last_kwargs = kwargs
                if outer._error:
                    raise outer._error
                message = type("M", (), {"content": json.dumps(outer._payload)})()
                choice = type("C", (), {"message": message})()
                return type("R", (), {"choices": [choice]})()

        self.chat = type("Chat", (), {"completions": Completions()})()


def test_returns_none_without_api_key(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "")
    assert reasoning.annotate(make()) is None


def test_annotates_each_finding(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")
    fake = FakeOpenAI({"annotations": [
        {"index": 0, "explanation": "Attackers run code.", "fix": "Drop eval."},
        {"index": 1, "explanation": "Shell injection.", "fix": "Pass a list."},
    ]})
    monkeypatch.setattr(reasoning, "_client", lambda: fake)

    result = reasoning.annotate(make())
    assert len(result) == 2
    assert result[0]["explanation"] == "Attackers run code."
    assert result[1]["fix"] == "Pass a list."


def test_api_error_returns_none(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")
    monkeypatch.setattr(reasoning, "_client", lambda: FakeOpenAI(error=RuntimeError("503")))
    assert reasoning.annotate(make()) is None


def test_missing_annotations_are_filled_with_blanks(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")
    fake = FakeOpenAI({"annotations": [
        {"index": 1, "explanation": "Only the second.", "fix": "Fix it."}
    ]})
    monkeypatch.setattr(reasoning, "_client", lambda: fake)

    result = reasoning.annotate(make())
    assert len(result) == 2
    assert result[0] == {"explanation": "", "fix": ""}
    assert result[1]["explanation"] == "Only the second."


def test_extra_annotations_are_discarded(monkeypatch):
    """The model must not be able to invent findings we never detected."""
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")
    fake = FakeOpenAI({"annotations": [
        {"index": 0, "explanation": "Real.", "fix": "Fix."},
        {"index": 1, "explanation": "Real.", "fix": "Fix."},
        {"index": 99, "explanation": "Invented.", "fix": "Nope."},
    ]})
    monkeypatch.setattr(reasoning, "_client", lambda: fake)

    result = reasoning.annotate(make())
    assert len(result) == 2
    assert all("Invented" not in r["explanation"] for r in result)


def test_empty_findings_short_circuits(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")
    assert reasoning.annotate([]) == []
