# Troubleshooting

| Symptom | Check |
| --- | --- |
| Address already in use | Stop the other instance or change `PWAF_HTTP_PORT`; desktop mode never attaches to an existing server. |
| LAN request says invalid host | Open the exact `PWAF_PUBLIC_ORIGIN`, including port. A second hostname/IP is not implicitly allowed. |
| LAN cannot connect | Confirm the host's LAN address, LAN mode, bind interface, and private-network firewall rule. No router forwarding is needed. |
| Mutation returns 403 | Refresh to obtain the current CSRF token; send the configured Origin. Optional proxy viewers cannot mutate state. |
| Proxy access returns 401 | Use the HTTPS proxy. Direct backend requests are intentionally rejected; check that both processes use the same token. |
| Proxy access returns 403 | Confirm the Caddy identity is in `PWAF_LAN_USERS`; execution/settings changes also require membership in `PWAF_LAN_OPERATORS`. |
| HTTPS certificate warning | Trust the chosen CA on that client or use a certificate it already trusts; do not disable verification as a permanent fix. |
| Settings file is invalid | Stop the app, preserve the file, and repair or restore it. The app does not silently overwrite corrupt whole-file JSON. |
| Database schema is newer | Use the matching app release or restore a compatible data backup; do not manually lower migration versions. |
| Job returns 404 after restart | Job records are temporary. Check successful saved measurements in history. |
| Job capacity is full | Wait for work to finish or cancel a supported job. Default capacity is one running plus four waiting. |
| Desktop dependencies unavailable | Install the desktop extra and platform webview prerequisites, or use browser mode. |
| Installer refuses destination | Choose an empty folder or a recognized PWAF installation outside the source checkout. |
| Stale install lock | Confirm no installer is running before removing `.install-lock`; rerun to prepare a fresh release. |

Logs are written to the process console. `PWAF_LOG_LEVEL=DEBUG` can help diagnose
startup, but integration code must not log passwords, tokens, or private tool output.
A stopped/failed required service makes `/healthz` return 503. In authenticated mode,
health checks go through the authenticated proxy just like other requests.
