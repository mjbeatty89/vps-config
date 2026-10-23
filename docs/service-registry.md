# Service Registry & Homepage Automation

Last updated: 2026-10-23

## Why

Homepage is a good dashboard, but hand-editing `services.yaml` does not scale when
multiple desktops, agents, Proxmox guests, and Unraid containers are introducing
services. The registry makes **one file** authoritative and renders the dashboard
from it.

```text
inventory/services.yaml          ← humans + agents register here
        │
        ├── scripts/render-homepage.py
        │      └── monitoring/homepage/config/services.yaml
        │      └── monitoring/homepage/config/settings.yaml (layout)
        │
        └── scripts/discover-services.py
               ├── Docker labels (homepage.*)
               └── Proxmox notes (homepage.*)
```

The VPS Homepage (`:3010`, tailnet) is the single dashboard. Cash’s dashboard
pilots are not the source of truth and should be retired eventually.

## Schema

```yaml
version: 1
groups:
  Monitoring:
    order: 20
    columns: 4
    style: row
services:
  - id: grafana
    name: Grafana
    group: Monitoring
    href: https://oracle.manee-frog.ts.net:3002
    icon: grafana
    description: Dashboards (tailnet)
    status: active              # active | pending
    source:
      host: vps                 # device, not agent
      kind: docker              # docker | lxc | qemu | systemd | tailscale | manual | external
      ref: grafana              # container/VMID/unit
    owner: mjb
    added_by: opencode
    added_at: '2026-10-23'
    updated_at: '2026-10-23'
    tags: [monitoring, tailnet]
    docker_server: vps          # optional Homepage Docker integration
    docker_container: grafana
    widget:
      type: siteMonitor
      url: http://grafana:3000/login
```

Rules:

- `id` is stable; re-registering updates.
- `status: pending` keeps a service out of the dashboard until a URL exists.
- `href` must be a browser URL (http/https) for active entries.
- `source` records where it runs; `added_by` records which agent/human added it.
- `widget` is passed through to Homepage; `--health` creates a `siteMonitor`.
- Do not store secrets in this file.

## Register

```bash
scripts/register-service.py \
  --name "Forgejo" \
  --url "https://ai-server.manee-frog.ts.net:3443" \
  --group "Apps" \
  --icon "forgejo" \
  --description "Git hosting" \
  --source-host pve \
  --source-kind lxc \
  --source-ref 122 \
  --health "http://10.1.30.23:3000/" \
  --tag git --tag tailnet \
  --added-by opencode
```

Then:

```bash
python3 scripts/render-homepage.py --check
git add inventory/services.yaml monitoring/homepage/config/services.yaml
git commit -m "services: add Forgejo"
```

If the service has no URL yet:

```bash
scripts/register-service.py --name "New App" --group Apps \
  --source-host pve --source-kind lxc --source-ref 123 --pending
```

## Discovery

### Docker opt-in labels

```yaml
labels:
  homepage.enable: "true"
  homepage.name: "Forgejo"
  homepage.href: "https://ai-server.manee-frog.ts.net:3443"
  homepage.group: "Apps"
  homepage.icon: "forgejo"
  homepage.description: "Git hosting"
  homepage.health: "http://127.0.0.1:3000/"
  homepage.tailnet: "true"
  homepage.tags: "git,tailnet"
```

Run from a machine with SSH access:

```bash
scripts/discover-services.py \
  --host vps=root@100.67.166.50 \
  --host pve=root@10.1.30.13 \
  --host pvevcm=root@10.1.30.15 \
  --host cash=root@10.1.30.8 \
  --host ai-server=root@10.1.30.9 \
  --host unraid=root@10.1.30.16
```

It writes `inventory/discovered.yaml`. Add `--apply` to merge proposals through the
same registry/upsert path. Containers without `homepage.*` labels are ignored.

### Proxmox opt-in notes

In the VM/LXC **Notes** field:

```text
homepage.enable=true
homepage.url=https://ai-server.manee-frog.ts.net:9443
homepage.group=AI
homepage.icon=omniroute
homepage.description=OmniRoute gateway
homepage.health=http://10.1.30.20:20128/health
homepage.tags=ai,tailnet
```

Discovery uses `pvesh get /cluster/resources` and each guest’s config notes. This
covers VM/LXC links without hard-coding every guest in Homepage.

**Limitations:** Unraid VMs do not expose a convenient notes field through the same
API; register those manually or use Docker labels for Unraid containers.

## Render / deploy

```bash
python3 scripts/render-homepage.py          # write both generated files
python3 scripts/render-homepage.py --check  # CI drift check
```

`deploy-vps.sh`:

1. pulls `main`
2. runs the renderer check
3. reconciles the monitoring stack
4. restarts Homepage only when `services.yaml` changed

Homepage’s `settings.yaml` title/theme/header settings are preserved; only the
`layout` block is generated from registry groups.

## Adding a service on a specific host

### pve / pvevcm LXC

```bash
# on the LXC, expose a URL and add Proxmox notes (or register manually)
scripts/register-service.py --name "OmniRoute" \
  --url "https://ai-server.manee-frog.ts.net:9443" \
  --group AI --source-host pve --source-kind lxc --source-ref 120 \
  --health "http://10.1.30.20:20128/health" --tag ai --tag tailnet \
  --added-by opencode
```

### Unraid Docker

Add `homepage.*` labels in the Unraid template/compose, then run discovery against
`unraid`. Do not create a separate Unraid dashboard.

### cash / ai-server Docker

Same labels; discovery reads them over SSH. The cash dashboard pilots are
deprecated as sources of truth.

## Verification checklist

- [ ] `inventory/services.yaml` has one entry, `id` stable.
- [ ] `source.host`, `source.kind`, `source.ref` set.
- [ ] `added_by` names the agent/human.
- [ ] `href` is tailnet/LAN unless intentionally public.
- [ ] `python3 scripts/render-homepage.py --check` passes.
- [ ] Committed registry + generated Homepage config.
- [ ] Page loads in Homepage (tailnet).
