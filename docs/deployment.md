# Local, LAN, and optional authenticated access

Password authentication is **off by default**. The default process mode is local;
select LAN mode when you want other devices to use the app. LAN without a login is
a shared workspace: devices that can reach it can view data, change settings, and
run tools. Host/origin validation and CSRF protection remain enabled in every mode.

## Local browser access

```sh
python -m app
```

Open `http://127.0.0.1:8191`. The server binds to loopback. No login or proxy is needed.
Run one process for each data directory.

## LAN access without a password

Choose the host machine's stable LAN address (or a LAN hostname that resolves to
it). Set an explicit origin; it is the address users will enter in their browsers.
For example, if the host is `192.168.1.50`:

```sh
export PWAF_MODE=lan
export PWAF_PUBLIC_ORIGIN=http://192.168.1.50:8191
python -m app
```

PowerShell:

```powershell
$env:PWAF_MODE = 'lan'
$env:PWAF_PUBLIC_ORIGIN = 'http://192.168.1.50:8191'
python -m app
```

`PWAF_LAN_AUTH` defaults to `none`, and the bind address defaults to `0.0.0.0` in
this mode. Open the configured address from a laptop or phone on the LAN. If the
host firewall blocks the port, allow it for the private LAN according to your
machine's firewall configuration. No router port forwarding is needed.

Only the exact configured hostname/IP and port are accepted; accessing the same
server through a different alias returns an invalid-host response. HTTP is expected
for this direct mode. All connected LAN users share transient jobs and successful
results. Authentication is an optional configuration change, not an installation
requirement or a first-run prompt.

Installed launchers (`run.sh` / `run.ps1`) inherit these same variables and preserve
their stable data directory. Return to local mode by removing LAN variables rather
than leaving incompatible proxy settings behind.

## Optional password authentication with Caddy

This opt-in mode uses a same-machine Caddy HTTPS reverse proxy. FastAPI binds only
to loopback. Caddy checks username/password, strips client-supplied identity values,
and sends the authenticated identity plus a shared proxy token upstream. FastAPI
requires both a loopback peer and the correct token, validates the user allowlist,
and allows mutations only for configured operators. A forged identity header alone
cannot bypass this boundary. OS users able to read the proxy token are trusted.

The provided `deploy/Caddyfile` has `operator` and `viewer` accounts. All allowed
users can see shared successful results and settings. Operators can change settings
and submit work; transient job status/cancellation and idempotency keys are scoped
to the submitting identity. This is a small shared-workspace policy, not private
multi-tenant storage. Browser mutation routes still require Origin and CSRF headers.

Install Caddy separately from its [official distribution](https://caddyserver.com/docs/install).
The configuration uses [basic_auth](https://caddyserver.com/docs/caddyfile/directives/basic_auth)
and [reverse_proxy](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy).
Native applications do not need Caddy.

1. Pick a LAN hostname or IP, for example `tools.home.arpa`, and arrange LAN DNS or
   hosts-file resolution. This example uses HTTPS port 8443, so no privileged port
   binding is necessary.
2. Generate a shared token into a private file. This command creates a new file and
   refuses to overwrite an existing one:

   ```sh
   python -c "import os,secrets; fd=os.open('proxy-token',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600); f=os.fdopen(fd,'w'); f.write(secrets.token_hex(32)); f.close()"
   ```

   On Windows, also restrict the file's NTFS access to the account running the
   application and proxy; POSIX mode bits do not configure Windows ACLs.
3. Configure the application (use an absolute token path):

   ```sh
   export PWAF_MODE=lan
   export PWAF_LAN_AUTH=proxy
   export PWAF_PUBLIC_ORIGIN=https://tools.home.arpa:8443
   export PWAF_HTTP_HOST=127.0.0.1
   export PWAF_PROXY_TOKEN_FILE=/absolute/private/path/proxy-token
   export PWAF_LAN_USERS=operator,viewer
   export PWAF_LAN_OPERATORS=operator
   python -m app
   ```

4. In the Caddy process environment, set the same public origin and backend port
   (8191 by default), the proxy token read from that file, and password hashes:

   ```sh
   export PWAF_PUBLIC_ORIGIN=https://tools.home.arpa:8443
   export PWAF_HTTP_PORT=8191
   export PWAF_PROXY_TOKEN="$(cat /absolute/private/path/proxy-token)"
   export PWAF_OPERATOR_HASH="$(caddy hash-password)"
   export PWAF_VIEWER_HASH="$(caddy hash-password)"
   caddy validate --config deploy/Caddyfile --adapter caddyfile
   caddy run --config deploy/Caddyfile --adapter caddyfile
   ```

   `caddy hash-password` prompts for a password; retain the hashes privately, not
   plaintext passwords in source control. The proxy overwrites `X-PWAF-User` and
   `X-PWAF-Proxy-Token` and removes `Authorization` before forwarding. Do not remove
   those header rules or expose the backend on another interface. Forwarded IP and
   scheme headers from clients are not trusted by Uvicorn.
5. The example uses Caddy's internal certificate authority. Install/trust its root
   certificate on the LAN devices that will use this service, or replace
   `tls internal` with a certificate configuration those devices already trust.
   The file explicitly disables automatic trust-store installation and HTTP
   redirects. Browse to HTTPS directly. Trust administration is an operator action;
   the installer and verification scripts do not change system trust stores.

The application must be restarted after changing authentication configuration.
The proxy admin API is disabled in the example. Protect its configuration and token,
rotate the token in both processes together, and restrict exposed ports to the LAN.
Public internet deployment is outside this foundation's verified scope.

## Environment reference

| Variable | Default | Validation and purpose |
| --- | --- | --- |
| `PWAF_MODE` | `local` | `local` or `lan`. |
| `PWAF_LAN_AUTH` | `none` | `none` or opt-in `proxy`; proxy requires LAN mode. |
| `PWAF_HTTP_HOST` | `127.0.0.1`; `0.0.0.0` for direct LAN | IP or `localhost`; local/proxy mode requires loopback. |
| `PWAF_HTTP_PORT` | `8191` | Integer 1–65535. |
| `PWAF_PUBLIC_ORIGIN` | unset | Required for LAN; exact HTTP origin for direct LAN or HTTPS origin for proxy mode, without path/query/credentials. Direct origin port must equal server port. |
| `PWAF_DATA_DIR` | `./data` | Resolved against startup working directory; installed launchers default to their root's `data/`. |
| `PWAF_LOG_LEVEL` | `INFO` | DEBUG, INFO, WARNING, ERROR, CRITICAL. |
| `PWAF_PROXY_TOKEN_FILE` | unset | Required only for proxy mode; file containing 64 lowercase hex characters. |
| `PWAF_LAN_USERS` | empty | Comma-separated usernames allowed through the authenticated proxy; required in proxy mode. |
| `PWAF_LAN_OPERATORS` | empty | Subset of allowed users permitted to mutate state/run work; empty means read-only. |

Usernames are 1–64 letters/digits/dots/underscores/hyphens. Proxy settings are rejected
in unauthenticated modes to avoid silently ignoring an intended authentication
configuration. Startup variables are not written to editable settings JSON.

The Caddyfile additionally consumes `PWAF_PROXY_TOKEN`, `PWAF_OPERATOR_HASH`, and
`PWAF_VIEWER_HASH` with no defaults. These are proxy-process inputs only; FastAPI
does not read them. Keep the token and hashes out of logs and committed files.
