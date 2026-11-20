"""Запуск для жюри не требует интернета: скрипты ничего не ставят, во время работы нужна только stdlib."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_run_scripts_install_nothing():
    for name in ("run.bat", "run.sh"):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert "pip install" not in text and "analyze.py" in text, name


def test_runtime_has_no_requirements():
    lines = [ln.strip() for ln in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()]
    assert not [ln for ln in lines if ln and not ln.startswith("#")]
    assert "pytest" in (ROOT / "requirements-dev.txt").read_text(encoding="utf-8")
