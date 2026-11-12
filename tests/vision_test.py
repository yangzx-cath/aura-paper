import base64
from pathlib import Path

from vision import _to_data_url

SAMPLE_JPG = (
    Path(__file__).resolve().parent.parent
    / "data"
    / "chicken_and_sunflower"
    / "01.jpg"
)


def test_jpeg_prefix_and_payload():
    url = _to_data_url(SAMPLE_JPG)

    header, _, payload = url.partition(",")
    assert header == "data:image/jpeg;base64"
    assert base64.b64decode(payload) == SAMPLE_JPG.read_bytes()


def test_png_uses_png_mime(tmp_path):
    target = tmp_path / "page.png"
    target.write_bytes(b"\x89PNG\r\n\x1a\nnot really a png")

    url = _to_data_url(target)

    assert url.startswith("data:image/png;base64,")


def test_unknown_suffix_falls_back_to_jpeg(tmp_path):
    target = tmp_path / "page.xyz"
    target.write_bytes(b"whatever")

    url = _to_data_url(target)

    assert url.startswith("data:image/jpeg;base64,")
