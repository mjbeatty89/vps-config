# Raspberry Pi nodes

Two tailnet nodes:

| Node | Hostname (default) | Role |
|---|---|---|
| DNS | `pi-dns` | AdGuard Home + Unbound (LAN + tailnet DNS) |
| Docker | `pi-docker` | spare local containers |

Both run the same **node-agent** (node-exporter + cadvisor) so the VPS Prometheus
monitors them. Suggested split: give the **Pi 5** the Docker role (more RAM), the
**Pi 4** the DNS role (it's light) — but either works.

> **Note (as-built):** your nodes (`dnspi`, `dockernodepi`) came up as **DietPi**
> with the roles already provisioned — AdGuard Home + Unbound on `dnspi`
> (web UI on `:8083`, upstream → `unbound` `127.0.0.1:5335`), and a service stack
> (Portainer, Forgejo, InfluxDB, Homebridge, FileBrowser, Syncthing, Webmin) on
> `dockernodepi`. `bootstrap.sh` is only for a *blank* node — on these, skip
> sections 1–3 and just wire monitoring (section 4–5). `node_exporter` is already
> running on both (`:9100`); cadvisor is not.

## 1. Bootstrap each node

From a checkout of this repo on the Pi:

```bash
sudo ./pi/bootstrap.sh --role dns    --hostname pi-dns
sudo ./pi/bootstrap.sh --role docker --hostname pi-docker
```

It installs Docker + Compose, Tailscale, sets the hostname, and runs
`tailscale up --ssh --accept-routes`. The first `tailscale up` prints a login URL —
open it to authorize. (Non-interactive: create a Tailscale auth key and pass
`--authkey tskey-...`; add `--tags tag:pi` if your ACL has a `tagOwners` entry.)

Then, from the VPS, `tailscale ssh pi-dns` / `tailscale ssh pi-docker` works.

## 2. DNS node

```bash
cd home-dns
sudo sed -i 's/^#\?DNSStubListener=.*/DNSStubListener=no/' /etc/systemd/resolved.conf
sudo systemctl restart systemd-resolved
sudo docker compose up -d
```

Finish the AdGuard wizard at `http://<tailnet-ip>:3000` (upstream `127.0.0.1:5335`).
Details + hardening in [`../home-dns/README.md`](../home-dns/README.md).

Point **UniFi DHCP → DNS** at this node's IP so LAN clients filter. Tailnet/roaming
clients can use the node's tailnet IP as their resolver too.

## 3. Docker node

```bash
cd pi/docker-node
cp .env.example .env
sudo docker compose up -d
```

Add your spare containers to `pi/docker-node/docker-compose.yml`. Keep ports bound
to `127.0.0.1` (reach them via `tailscale serve`) or to the tailnet IP — don't
publish to the public internet from the Pi.

## 4. Monitoring agents (both nodes)

```bash
cd pi/node-agent
sudo docker compose up -d
```

This exposes `:9100` (host metrics) and `:8080` (container metrics) on the tailnet.
The VPS Prometheus scrapes them via the file-SD targets in
`monitoring/prometheus/targets/`.

## 5. Wire into the VPS monitoring

Edit (or confirm) the hostnames in:

- `monitoring/prometheus/targets/nodes.yml`    (node-exporter, job `pi-node`)
- `monitoring/prometheus/targets/cadvisor.yml` (cadvisor, job `pi-cadvisor`)

Then either wait for the 5-minute GitOps deploy or reload now:

```bash
# on the VPS
curl -X POST http://127.0.0.1:9090/-/reload
```

Optionally add ping monitors in Uptime Kuma for `pi-dns` / `pi-docker` (tailnet IPs)
so you get Telegram alerts if a Pi drops.

## Tailscale ACL (optional, if you use tags)

To let the VPS scrape the nodes and to tag the Pis, add something like this to your
tailnet policy (adjust tag owners to your account):

```jsonc
{
  "tagOwners": { "tag:pi": ["autogroup:admin"] },
  "acls": [
    // VPS can reach the Pis on the scrape ports
    { "action": "accept", "src": ["oracle"], "dst": ["tag:pi:9100,8080"] },
    // admins can reach everything
    { "action": "accept", "src": ["autogroup:admin"], "dst": ["*:*"] }
  ],
  "ssh": [
    { "action": "accept", "src": ["autogroup:admin"], "dst": ["tag:pi"], "users": ["autogroup:nonroot", "root"] }
  ]
}
```

## 6. Self-updating (on-node GitOps)

Each node runs `pi-deploy.timer` (every 5 min) → `pi/deploy.sh`, which does
`git fetch/reset` of this repo at `/opt/aadd/vps-config`, applies the node's
`pi/nodes/<hostname>/docker-compose.yml`, and applies its `serve` rules. So:

- Change a compose file or `serve` manifest in the repo → push → nodes converge.
- Nodes authenticate with a **read-only deploy key** per host
  (`/root/.ssh/vps-config-deploy`; keys titled `pi-deploy@<host>` in GitHub).

Logs: `/var/log/pi-deploy.log` and `journalctl -u pi-deploy`.
