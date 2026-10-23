# Agent Protocol — Service Registration

This repository owns the homelab service catalog and the generated Homepage
dashboard. **Dashboard entries are not hand-edited.** The source of truth is
`inventory/services.yaml`.

## Definition of done for a new web service

Any time an agent deploys, exposes, or discovers a web service, it must register it:

```bash
scripts/register-service.py \
  --name "Grafana" \
  --url "https://oracle.manee-frog.ts.net:3002" \
  --group Monitoring \
  --icon grafana \
  --description "Metrics dashboards (tailnet)" \
  --source-host vps \
  --source-kind docker \
  --source-ref grafana \
  --health "http://grafana:3000/login" \
  --tag tailnet \
  --added-by opencode
```

Then commit both:

```bash
inventory/services.yaml
monitoring/homepage/config/services.yaml
```

The generated Homepage config is refreshed by the command. Verify with:

```bash
python3 scripts/render-homepage.py --check
```

## Rules

1. **One service, one registry entry.** Do not add a second dashboard just for a
   new host or agent.
2. **Use the source fields.** `source.host` is the device (`vps`, `pve`, `pvevcm`,
   `cash`, `ai-server`, `unraid`, …), `source.kind` is `docker`, `lxc`, `qemu`,
   `systemd`, `tailscale`, or `manual`, and `source.ref` is the container/VMID/unit.
3. **Record the owner agent.** `--added-by` must identify the agent or human that
   introduced the service. This is how we answer “what deployed this?” later.
4. **Use a tailnet URL by default.** Public URLs only when the service is intended
   to be public and has a Caddy route. Mark tailnet-only entries with
   `--tag tailnet`.
5. **No secrets in the registry.** Store only links, names, groups, icons, and
   ownership metadata. Tokens/passwords belong in 1Password or root-only env files.
6. **If the URL is not known yet,** register it as pending:
   ```bash
   scripts/register-service.py --name "New App" --group Apps \
     --source-host pve --source-kind lxc --source-ref 123 --pending
   ```
   Pending entries stay out of Homepage until a URL is added.
7. **Never edit generated files directly:**
   - `monitoring/homepage/config/services.yaml`
   - `monitoring/homepage/config/settings.yaml` (layout is generated; title/theme
     fields are preserved)
8. **Register before declaring the task complete.** A service that is not in the
   registry is effectively invisible to the homelab.

## Docker services: opt-in labels

Discovery reads Docker labels. Add these to the container/compose:

```yaml
labels:
  homepage.enable: "true"
  homepage.name: "Grafana"
  homepage.href: "https://oracle.manee-frog.ts.net:3002"
  homepage.group: "Monitoring"
  homepage.icon: "grafana"
  homepage.description: "Metrics dashboards (tailnet)"
  homepage.health: "http://grafana:3000/login"
  homepage.tailnet: "true"
  homepage.tags: "monitoring,tailnet"
```

Then run discovery (or register directly):

```bash
scripts/discover-services.py \
  --host vps=root@100.67.166.50 \
  --host cash=root@100.102.64.18 \
  --host ai-server=root@100.75.111.86 \
  --host unraid=root@100.76.50.59 \
  --apply
```

Discovery is opt-in: containers without `homepage.*` labels are ignored. It writes
`inventory/discovered.yaml` first; `--apply` merges explicit proposals.

## Proxmox VMs/LXCs: opt-in notes

Put these lines in the VM/LXC **Notes** field:

```text
homepage.enable=true
homepage.url=https://ai-server.manee-frog.ts.net:9443
homepage.group=AI
homepage.icon=omniroute
homepage.description=OmniRoute AI gateway
homepage.health=http://10.1.30.20:20128/health
homepage.tags=ai,tailnet
```

Discovery reads the notes through `pvesh` on `pve`/`pvevcm`. A bare `homepage`
tag is not enough without a URL; the entry remains pending.

## Ownership / conflict handling

- `id` is stable. Registering the same `--id` again updates the existing entry.
- Registry writes are locked; concurrent agents should still commit/rebase
  `inventory/services.yaml` like any other Git file.
- If two agents add the same service, keep one entry and merge metadata; do not
  create a dashboard duplicate.
- Do not add a second Homepage/Homarr/Dashy instance for a new service. The VPS
  Homepage at `:3010` is the single dashboard.

## Dashboard

- Renderer: `scripts/render-homepage.py`
- Homepage: `https://dash.aadd.rocks` (basic auth) or tailnet `:3010`
- Homepage config: `monitoring/homepage/config/`
- Deploy: `deploy-vps.sh` pulls the repo, checks generated config, and restarts
  Homepage only when the generated services file changes.

See [docs/service-registry.md](docs/service-registry.md) for the schema and
troubleshooting.
