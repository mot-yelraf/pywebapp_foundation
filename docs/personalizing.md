# Personalize a cloned PWAF application

Complete [APP_BRIEF.md](../APP_BRIEF.md) in the new project, then give it to your
agent with [AGENTS.md](../AGENTS.md). Use the checklist below as acceptance criteria.
The brief records decisions; it does not automatically configure the application.
[PingTest](pingtest.md) is a concrete build example.

## 1. Identity: give every user-facing surface the app's name

| Surface | Current location / action |
| --- | --- |
| Repository and folder | Clone into a new directory; keep foundation remote as `upstream` and your app as `origin` |
| Distribution name, description, authors, support URLs | Review `[project]` in `pyproject.toml`; changing the distribution name does not rename Python modules |
| Default display name | Subclass `FoundationSettings`, override `app_name` with its validation bounds, pass the schema to `create_app` |
| API title | The application-owned FastAPI construction in `app/app.py` currently uses a fixed title |
| Native window title | `launch_desktop` currently uses a fixed title; add a generic optional title argument if needed, passed from `app/` |
| Page/sidebar/header/footer text | Override application templates; the default layout is `pwaf_foundation/templates/base.html` |
| Browser/mobile identity and icons | Follow [icon customization](icons.md#derived-application-customization), including manifest identity and colors |
| Installer prompts and success text | Inspect `scripts/install_runtime.py` and wrapper scripts for user-facing PWAF wording |
| Version | Packaging currently reads `pwaf_foundation.__version__`; keep one canonical source or explicitly adopt and wire a separate app version |

Keep the Python packages `app` and `pwaf_foundation` unless a deliberate migration
updates every import, entrypoint, launcher, and packaging rule. Keep configuration
names and installer markers stable unless compatibility changes are intended.
Do not replace another user's saved `app_name` when changing a default.

## 2. Appearance: customize through application files

Register `app/templates/` and `app/static/` using `UIConfig`. Application templates
are searched first. To change the entire layout, copy the foundation `base.html`
to `app/templates/base.html` and edit it there. Do not make that same-name override
extend `base.html` recursively. For a new page, extend the existing base normally.

Load a stylesheet such as `app/static/branding.css` after the shared stylesheet,
using the `head` block in a page template or your custom base:

```jinja
{% block head %}
{{ super() }}
<link rel="stylesheet" href="{{ url_for('app_static', path='branding.css') }}">
{% endblock %}
```

Override the existing CSS variables (`--accent`, `--accent-soft`, `--bg`,
`--surface`, `--text`, `--muted`, `--line`, `--nav`) and typography there. Define
both `:root` and `:root[data-theme=dark]` values; check text contrast, focus rings,
buttons, settings dialogs, and mobile layouts. Preserve existing control IDs and
accessibility attributes when reusing the shared JavaScript. Page-specific `head`
blocks affect only those pages; a base override applies branding across the app.

Keep the supported theme values `light` and `dark` unless schema, controls, styles,
and tests are extended together. Changing the default must not reset saved themes.
Additional fonts/images/manifests may need explicit package-data patterns; the app's
current patterns cover HTML templates and CSS/JS, not arbitrary assets.

## 3. Replace the demo with the app's working flow

- Define the landing page, navigation, service, validated input/result models,
  routes, settings schema, migrations, and job definitions under `app/`.
- Replace `example_options()` / `create_example_app()` wiring with the app's
  composition. Update **both** `app/__main__.py` and `app/desktop.py` callers if
  renaming the factory, plus `app/cli.py` and its subprocess callers.
- Remove the Performance navigation, hashing form, benchmark-only settings, and
  example jobs from the finished UI. Remove unused demo source deliberately;
  preserve framework tests and previously stored data/tables.
- Update example-specific tests and smoke/clone/browser/install scripts that expect
  the performance route, result schema, or original wording. Do not simply disable
  failing verification to make a new app pass.
- Leave Graphum disabled unless the brief needs graphs. Enable it via
  `UIConfig(graph_enabled=True)` and supply app-owned metrics and data. See
  [Graphum](graphs.md) and [extensions](extending.md).

## 4. Settings and durable data

Use an app-specific `FoundationSettings` subclass and register independent
`SettingsPane` field groups. State which options users can edit and which belong
to startup environment configuration. Give each field a default, validation, and
clear label. Save through the shared settings service; preserve unknown fields
and existing preferences. Never embed credentials in the brief or defaults.

Define application migrations under their own namespace. Decide retention, export,
backup, and restore policy explicitly: generic automatic pruning/export is not
provided for every derived schema. Test both fresh databases and upgrades from
prior app versions. Back up before migration and stop the app before copying a
SQLite data directory. See [installation and recovery](installation.md).

## 5. Keep cloned apps separate at runtime

Every independently installed app should have its own installation directory and
data directory. Installed launchers default to `<installation>/data`; source runs
default to `./data` relative to the working directory. An inherited `PWAF_DATA_DIR`
can override either and accidentally point two apps at the same database.

Use a distinct available port when apps run simultaneously. For example, after
installing PingTest into its own directory:

```sh
# macOS/Linux — change these paths and port for your app.
PWAF_HTTP_PORT=8192 PWAF_DATA_DIR="$HOME/PingTest/data" "$HOME/PingTest/run.sh"
```

```powershell
# Windows PowerShell — variables apply to processes started in this session.
$env:PWAF_HTTP_PORT = "8192"
$env:PWAF_DATA_DIR = "$env:LOCALAPPDATA\PingTest\data"
& "$env:LOCALAPPDATA\PingTest\run.ps1"
```

These settings are environment configuration, not automatically saved by the
installer. Avoid port 8000. A conflicting port must produce a clear failure;
do not silently attach the window to another app's server. Use one server process
per data directory.

Standard installs include pywebview. Browser-only installs use `--browser-only`
(`-BrowserOnly` in PowerShell). For LAN mode, use browser-only launch and follow
[deployment](deployment.md), including the matching public origin/port. LAN password
authentication remains optional. Desktop mode currently requires local mode.

Finder `.app` bundles, Windows shortcuts, autostart, and system services are not
created by the current installer. If required, record and implement them as explicit
deliverables; an icon asset is not an application bundle. Customize installer-facing
branding without changing activation locks or data-preservation behavior.

## 6. Metadata, verification, and release

Set public description, author/support information, attribution, and release notes
for the derived app. Preserve inherited notices; identify the owner's licensing
choice instead of inventing one. Review the inherited [BSD 2-Clause license](../LICENSE)
and [third-party notices](../THIRD_PARTY_NOTICES.md); preserve their notices in the
derived project and its distributions. Record any additional app-specific licensing
decisions separately. Audit the third-party notice framework against actual
dependencies/assets when personalizing; it is not a complete resolved inventory
of the new app.

Run tests and lint, check keyboard/mobile behavior, and verify source and installed
startup separately. Test a clean install and an upgrade containing saved settings
and results. Exercise desktop and browser modes required by the brief. Inspect the
wheel/source archive for application templates, static assets, native icon files,
CLI modules, migrations, and needed documentation. Report actual tested platforms.

Document working commands and known limitations in the derived README/AGENTS.md;
update the brief's implementation record. Build artifacts locally, then publish
only when authorized. The foundation's version rule still applies unless an
explicit app-version policy supersedes it consistently.

## 7. Maintain the app as the foundation evolves

Record the foundation's starting commit/tag in the brief. Keep a customization list
and prefer app-owned files so later reviews can distinguish shared changes from
application work. To inspect available updates when network access is available:

```sh
git fetch upstream
git log --oneline HEAD..upstream/MAIN_BRANCH
```

Replace `MAIN_BRANCH` with the real upstream branch name. Fetching does not merge
anything. Review relevant changes, create an update branch with a clean working
tree, then deliberately merge or cherry-pick the changes you need. Resolve conflicts
in shared contracts, copied templates, packaging, and agent instructions; preserve
the derived app's purpose and data. Rerun app tests and upgrade checks. Do not
replace the whole cloned directory or reset to upstream to perform an update.

## Ready-to-deliver checklist

- [ ] Brief decisions and assumptions are recorded.
- [ ] Identity, artwork, theme, and product text are consistent.
- [ ] The real app workflow replaces the performance demo.
- [ ] Optional components and settings match the brief.
- [ ] Runtime directory, data, port, and launch mode are app-specific.
- [ ] Migrations, backups, and failure/cancellation behavior are verified.
- [ ] Packaging, clean install, upgrade, and required UI checks pass.
- [ ] Metadata, notices, commands, limitations, and update procedure are documented.
