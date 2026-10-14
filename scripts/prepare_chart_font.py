"""Download an official Google Fonts subset for the demo chart labels."""
from __future__ import annotations

import base64
import re
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parents[1]
FONT_DIR = ROOT / "assets" / "fonts"


def main() -> None:
    sources = [ROOT / "analysis_agent" / "semantic_layer.py", ROOT / "scripts" / "build_demo_data.py"]
    text = "".join(path.read_text(encoding="utf-8") for path in sources)
    characters = "".join(sorted(set(text + "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz%.,-+/() " ) - set("\r\n\t")))
    response = requests.get(
        "https://fonts.googleapis.com/css2",
        params={"family": "Noto Sans SC:wght@400", "text": characters},
        timeout=20,
    )
    response.raise_for_status()
    font_url = re.search(r"src: url\(([^)]+)\) format\('truetype'\)", response.text)
    if font_url is None:
        raise RuntimeError("Google Fonts did not return a TrueType font.")
    font_response = requests.get(font_url.group(1), timeout=20)
    font_response.raise_for_status()
    license_response = requests.get(
        "https://api.github.com/repos/google/fonts/contents/ofl/notosanssc/OFL.txt",
        timeout=20,
    )
    license_response.raise_for_status()
    license_bytes = base64.b64decode(license_response.json()["content"])
    FONT_DIR.mkdir(parents=True, exist_ok=True)
    (FONT_DIR / "NotoSansSC.ttf").write_bytes(font_response.content)
    (FONT_DIR / "OFL.txt").write_bytes(license_bytes)
    print(f"Prepared font: {len(font_response.content):,} bytes")


if __name__ == "__main__":
    main()
