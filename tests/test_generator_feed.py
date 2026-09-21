"""Genera el sitio en un directorio temporal y verifica la página de mantenimientos."""
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def site(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("site")
    # Evita que ensure_images() re-extraiga imágenes hacia docs/ durante el test.
    keep = out / "assets" / "images" / "x"
    keep.mkdir(parents=True)
    (keep / "keep.txt").write_text("x", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "excel_migrator.py", "plantilla_sitio.xlsx", str(out)],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return out


def test_feed_page_has_controls_and_tabs_in_order(site):
    html = (site / "mantenimientos.html").read_text(encoding="utf-8")
    assert 'id="feed-list"' in html
    assert 'id="feed-search"' in html
    assert 'id="feed-more"' in html
    assert 'src="maintenance_feed.js"' in html
    assert 'href="maintenance_feed.css"' in html
    cats = re.findall(r'class="feed-tab[^"]*" role="tab" data-cat="(\w+)"', html)
    assert cats == ["TODOS", "EQUIPOS", "TANQUES", "INSTRUMENTOS"]


def test_feed_page_embeds_tag_index(site):
    html = (site / "mantenimientos.html").read_text(encoding="utf-8")
    match = re.search(r"window\.__TAG_INDEX__ = (\[.*?\]);\s*</script>", html, re.S)
    assert match, "falta window.__TAG_INDEX__"
    index = json.loads(match.group(1).replace("<\\/", "</"))
    assert len(index) == 42
    assert set(index[0]) == {"tag", "categoria", "servicio", "filename"}
    assert {e["categoria"] for e in index} <= {"EQUIPOS", "TANQUES", "INSTRUMENTOS"}


def test_static_assets_are_copied(site):
    assert (site / "maintenance_feed.js").is_file()
    assert (site / "maintenance_feed.css").is_file()


def test_sidebar_link_on_every_page_level(site):
    assert 'href="mantenimientos.html"' in (site / "index.html").read_text(encoding="utf-8")
    assert 'href="../mantenimientos.html"' in (site / "equipos" / "100-P-01A.html").read_text(encoding="utf-8")
    assert 'href="../mantenimientos.html"' in (site / "equipos" / "index.html").read_text(encoding="utf-8")


def test_home_has_feed_button(site):
    home = (site / "index.html").read_text(encoding="utf-8")
    assert 'class="home-feed-cta" href="mantenimientos.html"' in home


def test_feed_link_is_active_only_on_feed_page(site):
    assert "nav-link-feed active" in (site / "mantenimientos.html").read_text(encoding="utf-8")
    assert "nav-link-feed active" not in (site / "index.html").read_text(encoding="utf-8")
