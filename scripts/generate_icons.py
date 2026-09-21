"""Generate PWAF platform icon packages from one editable SVG.

Uses the existing Playwright development dependency for rasterization and standard
library encoders for PNG-backed ICO/ICNS containers. Runtime needs no build tools.
"""

import json
import struct
from pathlib import Path
from xml.etree import ElementTree as ET

from playwright.sync_api import sync_playwright

ICONS = Path(__file__).resolve().parents[1] / 'pwaf_foundation/static/icons'
NS = 'http://www.w3.org/2000/svg'


def full_bleed(source: str, *, maskable: bool = False) -> str:
    """Remove transparent corners and keep maskable artwork inside its safe circle."""
    ET.register_namespace('', NS)
    root = ET.fromstring(source)
    background = root.find(f'{{{NS}}}rect')
    background.attrib.update(x='0', y='0', width='512', height='512', rx='0')
    if maskable:
        root.find(f'{{{NS}}}g').set('transform', 'translate(71.68 71.68) scale(.72)')
    return ET.tostring(root, encoding='unicode')


def ico(images: dict[int, bytes]) -> bytes:
    """Encode a multi-resolution icon with embedded PNG images."""
    header = struct.pack('<HHH', 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries, content = b'', b''
    for size, png in images.items():
        entries += struct.pack('<BBBBHHII', size % 256, size % 256, 0, 0,
                               1, 32, len(png), offset)
        content += png
        offset += len(png)
    return header + entries + content


def main() -> None:
    """Render web/mobile images, macOS iconset/ICNS, and Windows ICO files."""
    source = (ICONS / 'pwaf.svg').read_text()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(device_scale_factor=1)

            def render(svg, size):
                page.set_viewport_size({'width': size, 'height': size})
                page.set_content('<style>html,body{margin:0}svg{display:block;'
                                 'width:100vw;height:100vh}</style>' + svg)
                return page.screenshot(omit_background=True)

            sizes = (16, 32, 48, 64, 128, 256, 512, 1024)
            desktop = {size: render(source, size) for size in sizes}
            (ICONS / 'pwaf-desktop-icon.png').write_bytes(desktop[1024])
            (ICONS / 'pwaf-favicon-32.png').write_bytes(desktop[32])
            (ICONS / 'pwaf-favicon.ico').write_bytes(ico({n: desktop[n] for n in (16, 32, 48)}))
            (ICONS / 'pwaf-desktop-icon.ico').write_bytes(
                ico({n: desktop[n] for n in (16, 32, 48, 64, 128, 256)}))
            iconset = ICONS / 'pwaf.iconset'
            iconset.mkdir(exist_ok=True)
            for size in (16, 32, 128, 256, 512):
                for scale in (1, 2):
                    suffix = '@2x' if scale == 2 else ''
                    (iconset / f'icon_{size}x{size}{suffix}.png').write_bytes(desktop[size * scale])
            chunks = b''
            for tag, size in ((b'icp4', 16), (b'icp5', 32), (b'icp6', 64),
                              (b'ic07', 128), (b'ic08', 256), (b'ic09', 512),
                              (b'ic10', 1024), (b'ic11', 32), (b'ic12', 64),
                              (b'ic13', 256), (b'ic14', 512)):
                png = desktop[size]
                chunks += tag + struct.pack('>I', len(png) + 8) + png
            (ICONS / 'pwaf-desktop-icon.icns').write_bytes(
                b'icns' + struct.pack('>I', len(chunks) + 8) + chunks)
            for size in (192, 512):
                (ICONS / f'pwaf-android-{size}.png').write_bytes(render(source, size))
            (ICONS / 'pwaf-android-maskable-512.png').write_bytes(
                render(full_bleed(source, maskable=True), 512))
            (ICONS / 'pwaf-apple-touch-icon.png').write_bytes(render(full_bleed(source), 180))
            assets = ICONS / 'AppIcon.appiconset'
            assets.mkdir(exist_ok=True)
            (assets / 'pwaf-ios-1024.png').write_bytes(render(full_bleed(source), 1024))
            (assets / 'Contents.json').write_text(json.dumps({
                'images': [{'filename': 'pwaf-ios-1024.png', 'idiom': 'universal',
                            'platform': 'ios', 'size': '1024x1024'}],
                'info': {'author': 'PWAF', 'version': 1},
            }, indent=2) + '\n')
        finally:
            browser.close()


if __name__ == '__main__':
    main()
