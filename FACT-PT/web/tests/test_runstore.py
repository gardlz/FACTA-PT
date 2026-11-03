"""Finished runs on disk, shared by the website's processes and the worker."""

import os
from datetime import date
from pathlib import Path

import pytest

from app.runstore import RunStore
from app.schemas import ClaimInput, Question, RunResult


def execucao(run_id: str) -> RunResult:
    return RunResult(
        run_id=run_id,
        input=ClaimInput(claim="Uma claim suficientemente longa", claim_date=date(2025, 1, 2)),
        stages=[],
    )


def test_a_run_written_by_one_process_is_read_by_another(tmp_path):
    RunStore(8, tmp_path).put(execucao("abc123def456"))
    lido = RunStore(8, tmp_path).get("abc123def456")
    assert lido is not None and lido.input.claim == "Uma claim suficientemente longa"


def test_only_the_most_recent_runs_are_kept(tmp_path):
    store = RunStore(2, tmp_path)
    for run_id in ("aaaaaa000001", "aaaaaa000002", "aaaaaa000003"):
        store.put(execucao(run_id))
    assert sorted(p.stem for p in tmp_path.glob("*.json")) == ["aaaaaa000002", "aaaaaa000003"]
    assert RunStore(2, tmp_path).get("aaaaaa000001") is None


def test_an_identifier_that_is_not_a_run_id_never_reaches_the_disk(tmp_path):
    store = RunStore(8, tmp_path)
    store.put(execucao("../fora"))
    assert store.get("../fora") is None
    assert list(tmp_path.iterdir()) == []


def test_a_failed_write_leaves_nothing_behind(tmp_path, monkeypatch):
    store = RunStore(8, tmp_path)

    def falhar(self, destino):
        raise OSError("disco cheio")

    monkeypatch.setattr(Path, "replace", falhar)
    store.put(execucao("abc123def456"))
    monkeypatch.undo()
    assert list(tmp_path.iterdir()) == []
    assert store.get("abc123def456") is None


@pytest.mark.parametrize("conteudo", ["{nao e json", ""])
def test_an_unreadable_run_is_not_found(tmp_path, conteudo):
    (tmp_path / "abc123def456.json").write_text(conteudo, encoding="utf-8")
    assert RunStore(8, tmp_path).get("abc123def456") is None


def test_a_kept_verification_outlives_the_rolling_retention(tmp_path):
    store = RunStore(1, tmp_path)
    assert store.guardar(execucao("aaaaaa000001"))
    for run_id in ("aaaaaa000002", "aaaaaa000003"):
        store.put(execucao(run_id))
    lida = RunStore(1, tmp_path).guardada("aaaaaa000001")
    assert lida is not None and lida.saved_at is not None


def test_a_run_that_was_only_put_is_not_a_kept_verification(tmp_path):
    store = RunStore(8, tmp_path)
    store.put(execucao("abc123def456"))
    assert store.get("abc123def456") is not None
    assert store.guardada("abc123def456") is None
    assert RunStore(8, tmp_path).guardada("abc123def456") is None


def test_a_kept_verification_is_found_by_get_in_another_process(tmp_path):
    RunStore(8, tmp_path).guardar(execucao("abc123def456"))
    assert RunStore(8, tmp_path).get("abc123def456") is not None


def test_a_snapshot_cached_before_the_end_does_not_hide_the_kept_verification(tmp_path):
    """The website reads a run's documents from a mid-run snapshot, then the run finishes in the
    worker: the address must show the finished one."""
    escritor, leitor = RunStore(8, tmp_path), RunStore(8, tmp_path)
    escritor.put(execucao("abc123def456"))
    assert leitor.get("abc123def456").articles == []
    final = execucao("abc123def456")
    final.error = None
    final.questions = [Question(id="q1", index=1, text="Uma pergunta?")]
    escritor.guardar(final)
    assert [q.text for q in leitor.guardada("abc123def456").questions] == ["Uma pergunta?"]


def test_only_the_most_recent_kept_verifications_are_pruned_when_capped(tmp_path):
    store = RunStore(8, tmp_path, guardadas=2)
    for i, run_id in enumerate(("aaaaaa000001", "aaaaaa000002", "aaaaaa000003")):
        store.guardar(execucao(run_id))
        os.utime(tmp_path / "guardadas" / f"{run_id}.json", (1000 + i, 1000 + i))
    store.guardar(execucao("aaaaaa000004"))
    assert sorted(p.stem for p in (tmp_path / "guardadas").glob("*.json")) == [
        "aaaaaa000003", "aaaaaa000004"]


def test_an_identifier_that_is_not_a_run_id_is_never_kept(tmp_path):
    store = RunStore(8, tmp_path)
    assert not store.guardar(execucao("../fora"))
    assert list(tmp_path.iterdir()) == []
