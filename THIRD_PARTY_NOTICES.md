# Third-Party and Binary Notices

pywebapp_foundation source code is distributed under the BSD 2-Clause License in
[LICENSE](LICENSE). Dependencies, external tools, and contributed assets retain
their own applicable licenses and notices. This document identifies where to
maintain that information; it is not a complete inventory of every resolved
package or platform runtime.

## Python dependencies

| Dependency group | Source of dependency declarations | Purpose |
| --- | --- | --- |
| Runtime | `requirements.txt` | FastAPI, Uvicorn, Jinja2, Pydantic, and AnyIO |
| Optional desktop | `requirements-desktop.txt` | pywebview and its platform-dependent transitive dependencies |
| Development and verification | `requirements-test.txt`, included by `requirements-dev.txt` | pytest, coverage, HTTP testing, Ruff, build tooling, and Playwright |
| Build backend | `pyproject.toml` | setuptools |

These declarations use version ranges, not a complete pinned release inventory.
Transitive dependencies and resolved versions can differ by platform and release.
When distributing an installed runtime or bundled application, record the packages
actually included and retain their supplied license/copyright notices. Refer to
installed distribution metadata and upstream package materials rather than assuming
the foundation's license replaces dependency licenses.

## Platform runtimes and verification tools

pywebview uses native platform support such as WebKit/PyObjC on macOS, WebView2 on
Windows, or supported GTK/Qt backends on Linux. Which components are provided by the
OS, installed separately, or bundled depends on deployment. Document the components
actually distributed and retain their accompanying notices.

Playwright downloads a browser for development/verification when requested. That
browser is not part of the standard PWAF runtime installation. If distributing it
or other testing binaries separately, include their accompanying notices.

The optional deployment example uses a separately installed Caddy reverse proxy.
Caddy is not bundled or installed by the standard foundation installer. Record its
version and accompanying notices if a derived distribution includes it.

## Visual assets and other supplied content

The PWAF master icon, generated platform icons, and shared UI glyphs are shipped
with the project. [The icon guide](docs/icons.md) describes their source and
generation; [the graph guide](docs/graphs.md) records the graph component's provenance.
Preserve applicable source attribution and any asset-specific notices.

When adding or replacing fonts, images, icons, sample datasets, or other content,
record its creator/source, version or retrieval date where relevant, license, and
required attribution. Generating a resized or converted asset does not remove
notices associated with its source. Do not describe missing or unused datasets as
bundled dependencies.

## External services and application tools

The foundation does not require a domain-specific remote service or dataset. Derived applications may integrate external APIs,
command-line tools, hardware, or data providers. Document those integrations and
which software/content is merely accessed versus actually redistributed. Keep
credentials and private configuration out of notice files and source control.

## Maintaining notices in a cloned application

Keep the foundation's applicable attribution when personalizing the project. Update
this document to identify the derived application's actual additions and shipped
components, without replacing third-party terms with the app's own license.
Before each distribution, review changed dependencies, platform runtimes, visual
assets, and binaries against the built artifact.

Use an entry such as the following for each addition that needs a project-specific
record; this is a template, not a declaration that the component is included:

| Field | Value to record |
| --- | --- |
| Component | Name and purpose |
| Source | Upstream URL, author, or repository |
| Version | Exact shipped version/revision, where applicable |
| Distribution | Bundled, separately installed, or remotely accessed |
| License/notices | Applicable license identifier and included notice-file locations |
| Attribution | Required credit and where it appears |
| Changes | Local modifications, if any |

Keep this inventory accurate as components are added or removed. Do not populate
license claims or authorship from guesses; verify the supplied component materials.
