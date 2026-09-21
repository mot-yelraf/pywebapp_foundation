"""Validate shipped icon formats and browser discovery.

Checks generated assets directly so missing package files and broken manifest
links fail without needing native mobile devices or image generation tools.
"""

import json
import struct
from pathlib import Path

from fastapi.testclient import TestClient

from app.app import create_app
from pwaf_foundation.config import RuntimeConfig

ICONS = Path(__file__).resolve().parents[1] / 'pwaf_foundation/static/icons'


def test_platform_icon_packages():
    for name, size in [('pwaf-apple-touch-icon.png', 180), ('pwaf-android-192.png', 192),
                       ('pwaf-android-512.png', 512), ('pwaf-android-maskable-512.png', 512),
                       ('pwaf-desktop-icon.png', 1024)]:
        png = (ICONS / name).read_bytes()
        assert png[:8] == b'\x89PNG\r\n\x1a\n'
        assert struct.unpack('>II', png[16:24]) == (size, size)
    assert (ICONS / 'pwaf-desktop-icon.ico').read_bytes()[:6] == struct.pack('<HHH', 0, 1, 6)
    icns = (ICONS / 'pwaf-desktop-icon.icns').read_bytes()
    assert icns[:4] == b'icns'
    assert struct.unpack('>I', icns[4:8])[0] == len(icns)
    assert len(list((ICONS / 'pwaf.iconset').glob('*.png'))) == 10
    catalog = json.loads((ICONS / 'AppIcon.appiconset/Contents.json').read_text())
    for item in catalog['images']:
        assert (ICONS / 'AppIcon.appiconset' / item['filename']).is_file()


def test_browser_icon_discovery(tmp_path):
    with TestClient(create_app(RuntimeConfig(data_dir=tmp_path)),
                    base_url='http://127.0.0.1:8191') as client:
        page = client.get('/').text
        assert 'rel="apple-touch-icon" sizes="180x180"' in page
        assert 'rel="manifest"' in page
        response = client.get('/static/foundation/manifest.webmanifest')
        assert response.status_code == 200
        for icon in response.json()['icons']:
            image = client.get('/static/foundation/' + icon['src'])
            assert image.status_code == 200
            assert image.headers['content-type'] == 'image/png'
