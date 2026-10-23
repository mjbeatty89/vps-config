# PBS Offsite Backup — Hetzner Storage Box

Last updated: 2026-10-23  
Status: initial backup running; daily timer enabled.

## Design

```text
PBS (10.1.30.14)
  /rpool/backups  (PBS datastore, directory on rpool)
        │
        │ zfs snapshot rpool@pbs-offsite-YYYYmmdd-HHMMSS
        ▼
  /rpool/.zfs/snapshot/<snap>/backups
        │
        │ borg create (zstd, encrypted)
        ▼
Hetzner Storage Box
  ssh://u696446@u696446.your-storagebox.de:23/./pbs-backups
```

A ZFS snapshot is taken first so Borg sees a consistent datastore. The snapshot is
destroyed after the run.

## Endpoints / paths

| Item | Value |
|---|---|
| PBS | `10.1.30.14`, PBS `4.2.8-1` |
| PBS datastore | `/rpool/backups` |
| PBS pool | `rpool` 911 GB, ~7.2 GB used at setup |
| Storage Box | `hetz-vps`, `u696446.your-storagebox.de:23`, 1 TB, Helsinki |
| Borg repo | `ssh://u696446@u696446.your-storagebox.de:23/./pbs-backups` |
| SSH key on PBS | `/root/.ssh/id_ed25519_hetzner` (public key appended to Storage Box `.ssh/authorized_keys`) |
| Root env | `/etc/pbs-offsite-borg.env` (mode 600) |
| Borg passphrase | 1Password `op://1pserv/PBS_OFFSITE_BORG/password` |
| Script | `/usr/local/sbin/pbs-offsite-borg.sh` |
| Service | `/etc/systemd/system/pbs-offsite-borg.service` |
| Timer | `/etc/systemd/system/pbs-offsite-borg.timer` |

The Storage Box account password is in 1Password as `Hetzner`; Borg uses the dedicated
PBS SSH key, not the password.

## Schedule / retention

- Systemd timer: `OnCalendar=*-*-* 03:30:00`, `RandomizedDelaySec=20m`, `Persistent=true`
- Retention: **7 daily, 4 weekly, 6 monthly**
- Runs after the 02:00 PBS backup jobs.
- A ZFS snapshot named `pbs-offsite-*` is created and removed per run.

## Operations

```bash
# Status / logs
systemctl status pbs-offsite-borg.service
journalctl -u pbs-offsite-borg.service -n 100 --no-pager
systemctl list-timers pbs-offsite-borg.timer

# Manual run
systemctl start --no-block pbs-offsite-borg.service

# Inspect the repo (root on PBS)
set -a; . /etc/pbs-offsite-borg.env; set +a
borg list "$BORG_REPO"
borg info "$BORG_REPO::<archive>"

# Verify a run
borg check "$BORG_REPO"
```

## Restore outline

For a disaster recovery:

1. Provision/attach a PBS datastore path.
2. Restore the chosen Borg archive to a temporary directory:
   ```bash
   set -a; . /etc/pbs-offsite-borg.env; set +a
   mkdir -p /rpool/restore
   borg extract --list "$BORG_REPO::<archive>" --target /rpool/restore
   ```
   The archive contains the `backups/` subtree.
3. Move/copy the restored `backups` directory into a fresh PBS datastore path.
4. Add it as a PBS datastore and run `proxmox-backup-manager verify <datastore>`.
5. Re-register the datastore in PVE (`pbs-backups`) if needed.

Test a restore into a scratch path before relying on the offsite copy.

## Caveats

- The Storage Box is 1 TB; monitor `df`/`du` as the PBS datastore grows.
- Borg `repokey` stores the key in the repository; export the Borg key and keep it with
  the 1Password passphrase:
  ```bash
  borg key export "$BORG_REPO" /root/pbs-borg-key.txt
  ```
  Store that file in 1Password/offline safe storage, then remove the temporary copy.
- The initial backup is large; later runs are incremental.
- Do not run the offsite job concurrently with PBS prune/verify jobs without checking
  I/O and snapshot behavior.
