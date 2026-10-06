# PWAF icon assets

The PWAF mark is a mint geometric P supported by three blue foundation blocks on
a dark navy tile. It is original artwork for this project. Caelus was used as the
reference for platform formats and integration, not as the artwork source.

The editable master is `pwaf_foundation/static/icons/pwaf.svg`. All generated
files are shipped inside the Python package; runtime installations do not need
image-processing or browser automation dependencies.

| Target | Assets |
| --- | --- |
| Browser tabs | SVG, 32px PNG, and 16/32/48px multi-image favicon ICO |
| macOS | 1024px PNG, multi-resolution ICNS, and complete `pwaf.iconset` (16–512 points at 1x/2x) |
| iOS home screen | Opaque 180px Apple touch PNG, linked from every default page |
| iOS app packaging | `AppIcon.appiconset` with an opaque 1024px universal source and `Contents.json` |
| Android home screen | 192px and 512px PNGs plus a separate opaque 512px maskable icon |
| Windows packaging | Multi-resolution 16/32/48/64/128/256px ICO |

The Android maskable foreground fits inside the central safe circle while the
background fills the full square. iOS assets have no pre-rounded transparent
corners; the platform applies its own mask.

The default page includes favicon, Apple touch, and web manifest links and shows
the mark in the sidebar. The macOS pywebview launcher sets the running application's
Dock/app-switcher icon. Desktop installs use ICNS/ICO/PNG assets for
[per-user native launchers](installation.md#native-launchers-and-application-name).
Mobile assets and a manifest do not provide offline behavior or a native mobile app.
Actual iOS/Android launcher rendering and Xcode import have not been tested.

## Regenerate or replace

Edit the SVG, then run with development dependencies and Playwright Chromium:

```sh
.venv/bin/python scripts/generate_icons.py
```

Generated files are committed alongside their source. Derived apps should replace
the artwork, manifest identity/colors, and platform names together. A custom base
template can override browser icon links; the desktop icon lives at
`static/icons/pwaf-desktop-icon.png` relative to the foundation package.

Run `pytest tests/test_icons.py` for asset-format and HTTP-discovery checks.

## Derived-application customization

Follow [the README procedure](../README.md#give-your-cloned-app-its-own-icons) in the
cloned app. These are the currently wired locations:

| Location | What to update |
| --- | --- |
| `pwaf_foundation/static/icons/pwaf.svg` | Master artwork and accessible label |
| `scripts/generate_icons.py` | Source structure, output names, and app-catalog author metadata |
| `pwaf_foundation/static/manifest.webmanifest` | App identity, launch scope, colors, and relative Android icon URLs |
| `pwaf_foundation/templates/base.html` | Favicon, touch icon, manifest, sidebar logo, and theme color |
| `pwaf_foundation/desktop.py`, `set_macos_app_icon` | Runtime macOS Dock icon path |
| `pyproject.toml`, `[tool.setuptools.package-data]` | Inclusion of web assets, nested iconsets, and app catalogs |
| `tests/test_icons.py` | Asset names, dimensions, formats, and web-discovery checks |

The easiest path replaces artwork in the clone while retaining these asset names.
The generator expects a 512×512 SVG with a direct child background rectangle and
foreground group. It changes that rectangle for full-bleed variants and scales the
foreground for the maskable icon; an unrelated SVG structure needs a generator
adaptation. For a new design, verify that the scaled mark actually fits inside the
Android safe circle rather than relying on the default scale factor alone.

For application-owned branding, put icons and a manifest in `app/static/` and a
custom base template in `app/templates/`, and register both directories in
`UIConfig`. Use the `app_static` route for those links. The default app package-data
patterns include nested static assets. Adapt the generator’s output directory
and set `icon_dir`/`icon_stem` in `app/identity.json`. The desktop entrypoint passes
`DesktopIdentity` to `launch_desktop`; native icon selection is independent of
`UIConfig`. Omitted identity retains the foundation artwork.

Renaming files is optional. When doing so, change all references in the table in one
reviewable update. Web manifest icon URLs are relative to the manifest location;
they must continue to resolve after moving it. Treat app identity (`id`) and launch
scope as deployment decisions rather than blindly replacing slashes with an app name.

Validate with the icon tests, a wheel-content inspection, browser checks, and an
installed desktop launch. Reinstall into the derived app's own destination to
update packaged assets. Close and reopen the native app; check cached favicons and
previously added home-screen shortcuts separately. Report platform checks that
remain unverified. Keep generic control glyphs unless the app explicitly replaces
the shared UI's visual style.
