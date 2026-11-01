# Oracle Cloud Accounts

Last updated: 2026-11-01

Two separate OCI tenancies are in use. Do not mix their OCI profiles.

## Account A — Caddy / public VPS

Tenancy: **`aaohanasuite`**  
Home region: `us-chicago-1` (ORD)  
OCI CLI profile: `[DEFAULT]` on cash

Inventory:

| Resource | Value |
|---|---|
| Compartments | None (root tenancy) |
| Compute | `virtual-server-tunnel` — `VM.Standard.A1.Flex`, 4 OCPU / 24 GB, RUNNING |
| Boot volume | 100 GB |
| VCN | `aadd-vcn` `10.0.0.0/16` |
| Subnet | `aaadd-n8n1-subnet` `10.0.0.0/24` |
| Internet gateway | 1 |
| Security lists | 2 |
| Block volumes | None |
| Load balancers | None |
| Object Storage | None |
| OKE clusters | None |

This is the Caddy / monitoring / Homepage / Tailscale VPS. No spare compute,
block storage, or Kubernetes resources exist in this tenancy.

## Account B — OKE

Tenancy: **`mjbeatty89`**  
Home region: `us-chicago-1` (ORD)  
OCI CLI profile: `[mjbeatty89]` on cash

Access is private to cash:

| Item | Value |
|---|---|
| OCI config | `cash:/home/mjb/.oci/config` → `[mjbeatty89]` |
| API key | `cash:/home/mjb/.ssh/oci/mjbeatty89/` (0600) |
| OCI CLI | `cash:/home/mjb/.venvs/oci-cli/bin/oci` |
| kubeconfig | `cash:/home/mjb/.kube/oke-cluster1` (0600) |
| kubectl | `cash:/home/mjb/.local/bin/kubectl` |

Use:

```bash
ssh cash
export KUBECONFIG=/home/mjb/.kube/oke-cluster1
/home/mjb/.local/bin/kubectl get nodes
```

The kubeconfig exec plugin uses the absolute OCI CLI path and
`--profile mjbeatty89`, so it does not depend on the shell PATH.

## OKE inventory

| Item | Value |
|---|---|
| Cluster | `cluster1` |
| State | ACTIVE |
| Kubernetes | `v1.34.2` |
| Endpoint | public `147.224.138.188:6443` |
| Endpoint config | public IP enabled; private workers |
| VCN | dedicated OKE VCN |
| CNI | VCN-native IP (`OCI_VCN_IP_NATIVE`) |
| Node pool | `pool1` |
| Nodes | **2 × `VM.Standard.A1.Flex`, both Ready** |
| Per node | **2 OCPU / 12 GB / 36 GiB ephemeral** |
| OS/runtime | Oracle Linux 8.10 aarch64, CRI-O 1.34 |
| Pods per node | 31 |
| Always Free posture | **4 OCPU / 24 GB total**, 2 × 50 GB boot = 100 GB; Basic cluster; no LB/block volumes |
| Storage classes | `oci-bv` (default), `oci` |
| Ingress controller | none |
| Metrics server | not observed |
| User workloads | none — only `kube-system` |

Access is **cluster-admin** for the configured OCI user. The cluster is 233 days
old and has no non-system namespaces.

Resized 2026-11-01 from `3 × 3 OCPU / 6 GB` to `2 × 2 OCPU / 12 GB` to fit the
Always Free A1 allowance. The old workers and their boot volumes are terminated;
the two current workers have two 50 GB boot volumes.

## `homelab` namespace

Applied 2026-11-01 from `k8s/oke/homelab/`:

- Namespace `homelab`
- ResourceQuota: 2 CPU / 8 GiB requests, 4 CPU / 16 GiB limits, 20 pods,
  10 services, 4 PVCs, 20 GiB storage
- LimitRange: 100m/128Mi default requests, 500m/512Mi default limits,
  2 CPU / 4 GiB max per container

## Tailscale operator

The Tailscale operator Helm release was installed and then uninstalled because
the existing `TS_OAUTH` client is under-scoped:

```text
creating operator authkey: calling actor does not have enough permissions (403)
```

Required OAuth client settings:

- General > Services: Read + Write
- Devices > Core: Read + Write
- Keys > Auth Keys: Read + Write
- Tag: `tag:k8s-operator`

ACL changes already applied:

- `tag:k8s-operator` owned by `group:dev`
- `tag:k8s` owned by `tag:k8s-operator`
- `autoApprovers.services.tag:k8s` → `tag:k8s`

The `tailscale` namespace and `operator-oauth` secret are present; the Helm
release is removed until the OAuth client is corrected. Helm is installed on
cash at `/home/mjb/.local/bin/helm`.

## Guardrails

- The nodes are **ARM64**. Use multi-arch images or build ARM64 images.
- No GPU.
- Persistent storage is OCI Block Volume via `oci-bv`; there is no shared NFS
  filesystem configured.
- The API endpoint is public. Restrict it with OKE API-endpoint controls or
  network policy after deciding who needs access.
- Do not put PBS, Homepage, AdGuard, media, or other stateful home services here.
- Keep secrets out of Git; use Kubernetes secrets/OCI Vault or External Secrets.

## Candidate first workloads

1. **Namespace + ResourceQuota/LimitRange** for a `homelab` tenant.
2. **Tailscale Kubernetes Operator** for tailnet-only access to selected services.
3. **Forgejo Actions runner** (ARM64) for CI jobs that should not run on ai-server.
4. **External watcher** (Uptime Kuma/blackbox) independent of the Oracle VPS.
5. **Argo CD or Flux** if the cluster becomes a GitOps target.

Stateful services and media stay on the homelab.
