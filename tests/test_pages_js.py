"""Встроенный JavaScript страниц разбирается без синтаксических ошибок (нужен node; без него тест пропускается)."""
import re
import shutil
import subprocess

import pytest

from billcheck.family import load_profiles
from billcheck.html import embed, render_family, render_report
from billcheck.pipeline import analyze
from helpers import DATA_DIR

NODE = shutil.which("node")


def _scripts(page: str) -> list[str]:
    return [s for s in re.findall(r"<script>(.*?)</script>", page, re.S)]


@pytest.mark.skipif(NODE is None, reason="node не установлен")
def test_pages_javascript_parses(tmp_path):
    results = [analyze(p) for p in sorted(DATA_DIR.glob("billing_0*.csv"))]
    pages = {"report": render_report(results[2], "Бабушка"),
             "family": render_family(results, load_profiles(DATA_DIR), ["#"] * 5, DATA_DIR),
             "upload": embed("upload.html", {"profiles": [], "limit_mb": 5})}
    for name, page in pages.items():
        for i, script in enumerate(_scripts(page)):
            path = tmp_path / f"{name}_{i}.js"
            path.write_text(script, encoding="utf-8")
            done = subprocess.run([NODE, "--check", str(path)], capture_output=True, text=True)
            assert done.returncode == 0, f"{name}: {done.stderr}"
        assert not re.search(r"^(const|let) (top|name|status|parent|self|length|origin)\b", page, re.M), \
            f"{name}: глобальное имя совпадает со свойством window"
