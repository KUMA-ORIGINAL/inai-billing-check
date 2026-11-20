import json
import re
import threading
import urllib.error
import urllib.request
from urllib.parse import quote

import pytest

from billcheck.server import make_server
from helpers import DATA_DIR


@pytest.fixture(scope="module")
def server():
    srv = make_server(DATA_DIR, port=0)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()
    srv.server_close()


def _get(url: str) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8")


def _post(url: str, body: bytes, filename: str = "billing.csv") -> tuple[int, str]:
    request = urllib.request.Request(url, data=body, method="POST", headers={"X-Filename": quote(filename)})
    return _get(request)


def _payload(page: str) -> dict:
    return json.loads(re.search(r'<script id="bill-data" type="application/json">(.*?)</script>', page, re.S).group(1))


def test_index_lists_profiles(server):
    status, page = _get(server + "/classic")
    assert status == 200
    names = [p["name"] for p in _payload(page)["profiles"]]
    assert names == ["Бабушка", "Папа", "Мама", "Сын, 15 лет", "Дочь, 19 лет"]
    assert "Детализация" in _payload(page)["how_to"]


def test_upload_billing_03(server):
    status, page = _post(server + "/api/analyze", (DATA_DIR / "billing_03.csv").read_bytes(), "billing_03.csv")
    assert status == 200
    data = _payload(page)
    assert data["overpay_text"] == "65,00" and "62626" in page
    assert data["profile"] == "Мама" and data["back_link"]["href"] == "/classic"
    assert "Эталон организаторов" in json.dumps(data["checklist"], ensure_ascii=False)


def test_upload_gives_report_url(server):
    request = urllib.request.Request(server + "/api/analyze", data=(DATA_DIR / "billing_03.csv").read_bytes(),
                                     method="POST", headers={"X-Filename": quote("billing_03.csv")})
    with urllib.request.urlopen(request, timeout=10) as response:
        url = response.headers["X-Report-Url"]
    assert re.fullmatch(r"/report/[0-9a-f]{32}", url)
    status, page = _get(server + url)
    assert status == 200 and _payload(page)["overpay_text"] == "65,00"
    assert _get(server + "/report/" + "0" * 32)[0] == 404


def test_error_keeps_original_name(server):
    status, text = _post(server + "/api/analyze", bytes([0x89, 0x50, 0x4E, 0x47, 0xFF, 0xFE]), "photo.png")
    assert status == 400 and "photo.png —" in json.loads(text)["error"]


def test_upload_bad_file(server):
    for body in (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\xff\xfe", b"", b"hello,world\n1,2\n"):
        status, text = _post(server + "/api/analyze", body, "picture.png")
        assert status == 400
        assert json.loads(text)["error"]
    assert _get(server + "/")[0] == 200  # сервер жив


def test_upload_too_large(server):
    status, text = _post(server + "/api/analyze", b"x" * (5 * 1024 * 1024 + 1))
    assert status == 413 and "5 МБ" in json.loads(text)["error"]


def test_profile_and_family(server):
    status, page = _get(server + "/profile/billing_03.csv")
    assert status == 200 and _payload(page)["back_link"]["href"] == "/family"
    status, page = _get(server + "/family")
    data = _payload(page)
    assert status == 200 and data["members"][0]["link"] == "/profile/billing_01.csv"
    assert data["self_check"]["found"] == 20


@pytest.mark.parametrize("path", ["/profile/../../etc/passwd", "/profile/billing_03_expected.json",
                                  "/profile/nope.csv", "/nothing"])
def test_unknown_paths(server, path):
    assert _get(server + path)[0] == 404


def _post_json(url: str, data) -> tuple[int, str]:
    body = json.dumps(data, ensure_ascii=False).encode("utf-8")
    return _get(urllib.request.Request(url, data=body, method="POST", headers={"Content-Type": "application/json"}))


def test_app_page_has_snapshot(server):
    status, page = _get(server + "/")
    assert status == 200 and "Акчам кайда?" in page
    embedded = re.search(r"window\.TAZA_SNAPSHOT=(.*?);</script>", page, re.S).group(1)
    assert json.loads(embedded)["members"][0]["name"] == "Гүлнара"


def test_api_health_and_demo(server):
    status, text = _get(server + "/api/health")
    assert status == 200 and json.loads(text)["ok"] is True
    status, text = _get(server + "/api/demo")
    demo = json.loads(text)
    assert status == 200 and len(demo["members"]) == 5 and demo["radar"]
    assert demo["members"][2]["report"]["summary"]["reclaimable_som"] == 65.0
    assert demo["members"][2]["content"].startswith("datetime,type")


def test_api_analyze_radar_explain_render(server):
    content = (DATA_DIR / "billing_03.csv").read_text(encoding="utf-8")
    status, text = _post_json(server + "/api/analyze", {"filename": "billing_03.csv", "content": content,
                                                        "settings": {"z_threshold": 3}})
    assert status == 200
    report = json.loads(text)["report"]
    assert report["summary"]["reclaimable_som"] == 65.0
    status, text = _post_json(server + "/api/radar", {"members": [{"name": "Мама", "report": report}]})
    assert status == 200 and {r["number"] for r in json.loads(text)["radar"]} >= {"53530", "62626"}
    status, text = _post_json(server + "/api/explain", {"anomaly": report["anomalies"][0], "lang": "ky"})
    assert status == 200 and json.loads(text)["source"] == "template"
    status, page = _post_json(server + "/api/render", {"report": report, "complaint": "Прошу вернуть"})
    assert status == 200 and "Прошу вернуть" in page and "<script" not in page


def test_api_errors_are_json(server):
    status, text = _post_json(server + "/api/analyze", {"filename": "a.csv", "content": "hello,world\n1,2\n"})
    assert status == 400 and json.loads(text)["error"]
    bad = urllib.request.Request(server + "/api/radar", data=b"{oops", method="POST",
                                 headers={"Content-Type": "application/json"})
    status, text = _get(bad)
    assert status == 400 and json.loads(text)["error"]
    assert _post_json(server + "/api/explain", {"lang": "ru"})[0] == 400
    assert _post_json(server + "/api/render", {})[0] == 400


def test_hosting_reads_port_and_host_from_env(monkeypatch):
    import analyze as cli
    monkeypatch.setenv("PORT", "10000")
    monkeypatch.setenv("HOST", "0.0.0.0")
    args = cli.build_parser().parse_args(["--serve"])
    assert (args.port, args.host) == (10000, "0.0.0.0")
    monkeypatch.delenv("PORT")
    monkeypatch.delenv("HOST")
    args = cli.build_parser().parse_args(["--serve"])
    assert (args.port, args.host) == (8000, "127.0.0.1")
    srv = make_server(DATA_DIR, port=0, host="0.0.0.0")
    try:
        assert srv.server_address[0] == "0.0.0.0"
    finally:
        srv.server_close()
