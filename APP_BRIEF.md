# Application brief

Fill this out in your cloned project before asking an agent to build the app.
This is a product brief, not runtime configuration. Bracketed values and unchecked
items are undecided; agents must not invent them as approved requirements. Record
reasonable implementation assumptions separately. Do not put credentials here.

## Purpose and audience

- Application name: [display name]
- One-sentence purpose: [problem this app solves]
- Intended users: [who will use it and their technical familiarity]
- Existing tool/service: [path, CLI command, or importable Python API]
- First complete workflow: [input → operation → useful result]
- First-release features: [required capabilities]
- Out of scope: [features deliberately postponed]

## Identity and appearance

- Repository/folder name: [name]
- Python distribution name: [lowercase package-distribution name]
- Window/page title and short description: [text]
- Author/organization and support link: [public information]
- Icon source/design brief: [file or description]
- Colors, typography, and default light/dark theme: [preferences]
- Landing page and navigation: [pages and labels]
- Header/footer/about content: [text and links]
- Version policy: [inherited PWAF scheme or explicitly specified app scheme]
- License/attribution decisions: [owner decision; preserve inherited notices]

## Platforms and operation

- Target OSes and minimum supported versions: [list]
- Launch modes: [desktop, browser-only, or both]
- Access: [local only, password-free LAN, or optional authenticated proxy]
- Development port and installed port: [ports; avoid 8000]
- Installation destination convention: [separate app-owned folder]
- Runtime data directory: [absolute installed path or per-installation data/]
- Required native tools/system packages: [names and discovery/failure behavior]
- Shortcuts, app bundles, or autostart: [none or explicit requirements]

## Inputs, settings, and data

- Inputs and validation bounds: [fields, allowed values, workload limits]
- Editable settings/defaults/panes: [fields and ownership]
- Startup-only configuration: [environment variables; no secret values]
- Results and failure cases: [schemas, units, user-visible messages]
- Long-running work: [timeouts, cancellation, progress, concurrency]
- Persistence: [what survives restart and its schema]
- Retention/export/backup/restore: [policy and formats]
- Existing data to preserve or migrate: [location and compatibility constraints]

## Optional UI components

- Graphum: [disabled or enabled]
- If enabled: [metric IDs/labels/units, null semantics, available selections,
  data source, time ranges, refresh behavior]
- Additional dialogs or custom UI: [requirements]
- Accessibility/mobile requirements: [keyboard, screen sizes, contrast, etc.]

## Acceptance and delivery

- CLI acceptance example: [command, input, expected result shape]
- Web/desktop acceptance example: [actions and expected outcome]
- Required failure/cancellation tests: [cases]
- Required clean-install and upgrade checks: [platforms and saved data]
- Real hardware/network access available for verification: [scope]
- Release artifacts: [wheel/source archive/installer/app bundle as required]
- Review checkpoints: [any explicit plan/design/release reviews requested]
- Publication scope: [local only unless publishing is explicitly authorized]

## Implementation record — maintained by the agent

- Agreed decisions: [decisions confirmed in the conversation or brief]
- Assumptions/open questions: [do not silently treat these as requirements]
- Foundation starting revision: [Git commit/tag]
- Customizations and shared extensions: [files/interfaces and why]
- Verification performed: [commands, platforms, results]
- Remaining limitations: [unverified platforms and deferred work]
