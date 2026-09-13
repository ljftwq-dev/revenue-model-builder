"""Tests for revenue_model.gate — state machine, resume, coverage."""
import pytest

from revenue_model.gate import (
    ANSWERED, GATE_DOCUMENTS, GateBook, default_document_options,
)


@pytest.fixture()
def book(tmp_path):
    b = GateBook(company="DemoCo", workdir=tmp_path)
    b.save()
    return b


class TestLifecycle:
    def test_ask_persists_waiting_gate(self, book, tmp_path):
        book.ask(GATE_DOCUMENTS, "missing Q3 call transcript",
                 default_document_options())
        reloaded = GateBook.load(tmp_path)
        g = reloaded.waiting()[0]
        assert g.gate == GATE_DOCUMENTS
        assert "search and judge yourself" in " ".join(g.options)

    def test_answer_records_authority_user(self, book):
        book.ask(GATE_DOCUMENTS, "q", default_document_options())
        book.answer(GATE_DOCUMENTS, "dropped the file(s) into the queue directory")
        g = [g for g in book.gates if g.gate == GATE_DOCUMENTS][0]
        assert g.status == ANSWERED and g.authority == "user"

    def test_delegation_maps_to_user_delegated(self, book):
        book.ask(GATE_DOCUMENTS, "q", default_document_options())
        book.answer(GATE_DOCUMENTS, "I don't know either — search and judge yourself")
        g = [g for g in book.gates if g.gate == GATE_DOCUMENTS][0]
        assert g.authority == "user-delegated"

    def test_answering_non_waiting_gate_rejected(self, book):
        with pytest.raises(ValueError, match="not waiting"):
            book.answer(GATE_DOCUMENTS, "x")

    def test_roundtrip_preserves_everything(self, book, tmp_path):
        book.ask("tags", "confirm segment tags", ["yes", "edit"])
        book.answer("tags", "yes")
        book.cover("call transcript", "absent-user-approved")
        book.cover("quarterly decks", "ok")
        reloaded = GateBook.load(tmp_path)
        assert reloaded.answered_answer("tags") == "yes"
        assert reloaded.absent_items() == {"call transcript":
                                           "absent-user-approved"}


class TestCoverage:
    def test_absent_items_loud(self, book):
        book.cover("a", "ok")
        book.cover("b", "absent")
        book.cover("c", "absent-user-approved")
        assert set(book.absent_items()) == {"b", "c"}
