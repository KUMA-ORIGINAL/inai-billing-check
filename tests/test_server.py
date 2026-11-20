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
    status, page = _get(server + "/")
    assert status == 200
    names = [p["name"] for p in _payload(page)["profiles"]]
    assert names == ["Я", "Папа", "Бабушка", "Мама", "Брат"]
    assert "Детализация" in _payload(page)["how_to"]


def test_upload_billing_03(server):
    status, page = _post(server + "/api/analyze", (DATA_DIR / "billing_03.csv").read_bytes(), "billing_03.csv")
    assert status == 200
    data = _payload(page)
    assert data["overpay_text"] == "65,00" and "62626" in page
    assert data["profile"] == "Бабушка" and data["back_link"]["href"] == "/"
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
