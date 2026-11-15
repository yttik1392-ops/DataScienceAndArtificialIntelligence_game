"""Run once: py -3.15 prepare_font.py
Download the open-licensed Nanum Gothic font directly from Google Fonts.
Font file is not bundled with this game source archive.
"""
from pathlib import Path
from urllib.request import Request, urlopen

url = "https://raw.githubusercontent.com/google/fonts/main/ofl/nanumgothic/NanumGothic-Regular.ttf"
out = Path(__file__).resolve().parent / "korean.ttf"
if out.is_file() and out.stat().st_size > 500_000:
    print("Already installed:", out)
else:
    print("Downloading Korean font from official Google Fonts...")
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=45) as response:
        data = response.read()
    if not (data[:4] in (b"\x00\x01\x00\x00", b"OTTO") and len(data) > 500_000):
        raise RuntimeError("Downloaded data is not a valid large TTF/OTF file")
    out.write_bytes(data)
    print("Done. Korean font saved:", out)
print("Now run: py -3.15 -m pygbag .")
