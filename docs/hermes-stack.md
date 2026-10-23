# Hermes / OmniRoute Routing Stack

Last updated: 2026-10-23  
Scope: Hermes Agent on `ai-server`, jev-router, and the OmniRoute gateway on Proxmox.

This document describes the current inference path, the config that lives where, and the
operational checks. It intentionally contains **no secret values**; use the referenced
1Password items or root-only env files.

## 1. Current inference path

```text
Hermes Agent (ai-server)
  │  model: hermes
  │  provider: custom:omniroute
  │  base_url: http://127.0.0.1:8791/v1
  ▼
jev-router (ai-server, systemd --user, :8791)
  │  semantic decision → pool
  │  forwards to OmniRoute /v1/...
  ▼
OmniRoute gateway (pve LXC 120, 10.1.30.20:20128)
  │  named combo / model
  ▼
provider connections + local llama.cpp
  (Claude, Codex, Gemini, OpenCode Go, Cline, OpenRouter, local llama, …)
```

Tailnet access to OmniRoute is `https://ai-server.manee-frog.ts.net:9443` via
`tailscale serve` on ai-server.

### Why jev-router stayed on ai-server

Only **OmniRoute** moved off ai-server. jev-router and Hermes Agent remain on ai-server,
because:

- Hermes runs there and its default provider is a loopback URL.
- jev-router is a small Python service with no GPU requirement, but moving it is a separate
  migration.
- The old OmniRoute endpoint was replaced in jev-router config, which restored Hermes.

If either moves later, update `model.base_url`, `custom_providers[].base_url`, and the
OmniRoute upstream in jev-router together.

## 2. Hermes Agent config (key points)

Config: `/home/mjb/.hermes/config.yaml`  
Env: `/home/mjb/.hermes/.env` (mode 600)  
Secrets source: 1Password vault `1pserv`; see `op://1pserv/...` references.

| Setting | Value |
|---|---|
| Default model | `hermes` |
| Provider | `custom:omniroute` |
| Provider base URL | `http://127.0.0.1:8791/v1` (jev-router) |
| API mode | `chat_completions` |
| Custom provider model | `subs2free` |
| Inference key env | `OMNIROUTE_API_KEY` |
| MCP management key env | `OMNIROUTE_MANAGEMENT_KEY` |
| Webhook port | `8644` |
| WebUI | `127.0.0.1:8787` |

### Services (systemd --user on ai-server)

| Unit | Port | Purpose |
|---|---|---|
| `hermes-gateway.service` | `8644` | Messaging/webhook gateway |
| `hermes-webui.service` | `8787` | Browser console / model picker |
| `jev-router.service` | `8791` | Semantic router in front of OmniRoute |
| `signal-cli.service` | — | Signal transport |

### MCP servers

| Server | URL | Notes |
|---|---|---|
| `home-assistant` | `http://10.1.30.10:8123/api/mcp` | enabled |
| `unifi-network` | `https://cash.manee-frog.ts.net:8445/mcp` | enabled |
| `cash-mcp` | `https://cash.manee-frog.ts.net:8443/mcp` | enabled |
| `omniroute` | `http://10.1.30.20:20128/api/mcp/stream` | enabled; management key |
| `ma` | `http://localhost:8095/mcp/v1` | disabled |

The OmniRoute MCP server is a **management** route. It must use
`OMNIROUTE_MANAGEMENT_KEY`, not the inference key. With the management key,
`hermes mcp test omniroute` registered **110 OmniRoute tools**. Keep this key
separate from `OMNIROUTE_API_KEY` and out of logs/history.

## 3. jev-router

Config: `/home/mjb/dev/opencode/ai-serving/jev-router/config.yaml`  
Service: `~/.config/systemd/user/jev-router.service`  
Health: `curl http://127.0.0.1:8791/health`

Current mode: **`dry-run`**  
Fallback pool: `default`  
OmniRoute upstream: `http://10.1.30.20:20128`

### Routes

| When | Pool |
|---|---|
| task=code, effort=high | `subs-coding-reasoning` |
| task=code | `subs-coding` |
| effort=high | `subs-coding-reasoning` |
| task=analysis, effort=high | `subs-coding-reasoning` |
| task=ops | `hermes` |
| effort=low | `default` |
| anything else | `default` |

### Important dry-run behaviour

`jev-router` is still in `mode: dry-run`. In this mode it logs the decision but only
preserves a requested model if that model is one of the named `pools`:

```yaml
pools: [default, hermes, subs-coding, subs-coding-reasoning, free-stack, historian]
```

For Hermes’ default model `hermes`, the request is preserved and forwarded as the
`hermes` combo. For a model **not** in `pools` (for example a selected
`auto/best-coding` in the WebUI, or `subs2free`), the request is rewritten to
`default`. That is current behaviour, not an OmniRoute failure.

If per-request model selection should pass through unchanged, either:

1. switch jev-router to `mode: live` after validating the routes, or
2. add a passthrough branch / include the model IDs in the allowed set.

Do this deliberately: live mode changes routing for every `/v1` caller.

## 4. OmniRoute

Host: pve LXC 120  
Resources: 2 vCPU / 2 GB RAM / 16 GB `local-lvm`  
Address: `10.1.30.20:20128`  
Tailnet: `https://ai-server.manee-frog.ts.net:9443`  
Compose: `/opt/omniroute/compose.yml` inside the LXC

Data:

| Item | Value |
|---|---|
| Data volume | `/app/data` (Docker volume `omniroute-data`) |
| Data size | ~1.6 GB |
| Primary DB | `storage.sqlite` ~100 MB |
| Combos | 12 |
| Provider connections | 40+ |
| Models exposed by `/v1/models` | ~7,224 |

The custom **`hermes` combo** is present in `storage.sqlite`:

- ID `5bef6500-03d7-4c81-a89f-a013efc226bb`
- 10 candidates: Claude Sonnet 4.6, Codex GPT-5.6 Sol/Terra, Claude Sonnet 4.5,
  Claude Opus 4.8, Gemini 3.6 Flash, Cline free, OpenCode Go DeepSeek V4.1 Flash /
  V4 Pro, local llama.cpp
- Strategy: reset-aware, quota-protective, free fallbacks

Other combos: `default`, `free-stack`, `historian`, `homelab-watch`, `opencode-go`,
`reason-hedge`, `static-best-free`, `subs-coding`, `subs-coding-reasoning`,
`subs2free`, `wan-proof`.

`/v1/models` does not enumerate every custom combo. The `hermes` combo is still
addressable by name and is what Hermes’ default `hermes` model reaches.

## 5. Operational checks

```bash
# jev-router sees the new OmniRoute
curl -s http://127.0.0.1:8791/health | python3 -m json.tool

# OmniRoute model catalog through jev-router
curl -s http://127.0.0.1:8791/v1/models | python3 -c \
  'import sys,json; print(len(json.load(sys.stdin)["data"]),"models")'

# OmniRoute directly (inference key)
curl -s -H "Authorization: Bearer $OMNIROUTE_API_KEY" \
  http://10.1.30.20:20128/v1/models >/dev/null && echo ok

# MCP (management key)
hermes mcp test omniroute

# Services
systemctl --user status jev-router hermes-gateway hermes-webui
```

If Hermes’ prepared-model list looks stale, refresh the WebUI model cache or run the
WebUI’s model builder; the on-disk cache is
`/home/mjb/.hermes/webui/models_cache.json`.

## 6. Known caveats / next steps

- jev-router is **dry-run**; see the passthrough caveat above.
- The `hermes` combo is not listed by `/v1/models`; it is a combo, not a provider model.
- `subs2free` is the custom provider’s default model but is **not** in jev-router’s
  `pools`, so requests for it currently become `default`.
- OmniRoute MCP uses a high-privilege management key. Keep it in `.env` (600) and
  1Password; do not expose it to the browser or public ingress.
- If jev-router/Hermes move to Proxmox later, update all three URLs together and keep
  the `OMNIROUTE_API_KEY` / `OMNIROUTE_MANAGEMENT_KEY` split.
