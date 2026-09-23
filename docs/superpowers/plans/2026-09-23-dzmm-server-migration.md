# DZMM Server Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the complete DZMM production workload from `43.134.78.52` to `49.234.20.159` with a final 10–15 minute write outage, a verified PostgreSQL restore, preserved browser login state, and a stopped old-server rollback copy.

**Architecture:** Prepare and rehearse the new server while the old server remains live, without starting any externally active worker on the new server. At cutover, stop all old DZMM writers, create and transfer a final PostgreSQL custom-format backup plus the stopped browser profile, restore and validate them on the new server, then start new services in dependency order. Keep the old server stopped and intact for rollback.

**Tech Stack:** Ubuntu 24.04, systemd, PostgreSQL 16, Python 3.12 virtualenv, Alembic, Playwright Chromium, SSH, `pg_dump`/`pg_restore`, rsync/tar, curl.

**Spec:** `docs/superpowers/specs/2026-09-23-dzmm-server-migration-design.md`

## Global Constraints

- Final write outage is limited to approximately 10–15 minutes.
- New admin web listens on `0.0.0.0:18080`; core remains on `127.0.0.1:18120`; browser CDP remains on `127.0.0.1:19222`.
- Do not migrate or alter OpenClaw or any other non-DZMM service.
- Never print, commit, or save plaintext credentials outside root-owned `/etc/dzmm/dzmm.env`.
- Never run old and new browser workers at the same time.
- AI memory remains disabled in the database and `dzmm-ai-memory-worker.service` remains disabled/inactive.
- Preserve the old database, browser profile, environment file, and application tree until the user separately approves deletion.
- Deploy committed repository state `83965d883523851e41e508aef3665fab25724874` or a later migration-only documentation commit containing the same application code.

## Review Focus

- The final dump must be created only after all old DZMM writers stop; verify no active DZMM process before dumping.
- The rehearsal restore must never start browser or AI workers; only core may start temporarily for a local health check.
- The new admin systemd override must survive base unit installation and expose only port `18080`, not `18090`.
- Browser profile ownership and Chromium dependencies must match the `dzmm` system user before browser startup.
- If the new browser accepts real traffic and rollback becomes necessary, forward the new database state back to the old server before restarting old workers; never create divergent writers.

---

### Task 1: Establish the migration control channel and immutable baseline

**Files:**
- Read: `deploy/systemd/*.service`
- Read: `/etc/dzmm/dzmm.env` on the old server without printing values
- Create on old server: `/var/backups/dzmm/<timestamp>/baseline.json`
- Create locally: `/tmp/dzmm-release-83965d8.tar.gz`

**Interfaces:**
- Consumes: SSH access to both servers and committed repository state.
- Produces: authenticated SSH control sockets, baseline metadata, and a content-addressed release archive.

- [ ] **Step 1: Create local release archive and record its checksum**

Run locally:

```bash
git diff --check
git status --short
git archive --format=tar.gz \
  -o /tmp/dzmm-release-83965d8.tar.gz \
  83965d883523851e41e508aef3665fab25724874
sha256sum /tmp/dzmm-release-83965d8.tar.gz
```

Expected: only known untracked `.env`/`.DS_Store` files appear; archive creation succeeds and prints a SHA-256 checksum.

- [ ] **Step 2: Establish password-authenticated SSH masters without placing passwords in commands**

Run one interactive control master per host and enter each password only at its terminal prompt:

```bash
ssh -MN -o ControlMaster=yes -o ControlPath=/tmp/dzmm-old-ssh \
  -o ControlPersist=1800 ubuntu@43.134.78.52
ssh -MN -o ControlMaster=yes -o ControlPath=/tmp/dzmm-new-ssh \
  -o ControlPersist=1800 ubuntu@49.234.20.159
```

Expected: `ssh -S /tmp/dzmm-old-ssh -O check ubuntu@43.134.78.52` and the corresponding new-host command both report a running master.

- [ ] **Step 3: Capture old production baseline without secrets**

Use the installed DZMM environment and schema metadata to write a root-only JSON manifest containing Alembic revision, database size, exact row counts for every mapped public table, service states, and AI memory enabled state. Do not include environment values. Store it below a new timestamped `/var/backups/dzmm/` directory with mode `0700`.

Expected: the manifest is valid JSON, Alembic is `20260919_82`, and the AI memory enabled value is `false`.

- [ ] **Step 4: Verify source and destination capacity**

Run read-only checks on both servers:

```bash
df -h /
free -h
systemctl is-active postgresql
ss -lnt
```

Expected: old production remains healthy; new server has more than 2 GB free disk after accounting for two database copies, application dependencies, and Chromium. No target DZMM port is occupied on the new server.

### Task 2: Provision the new operating system and PostgreSQL

**Files:**
- Create on new server: `/opt/dzmm`, `/var/lib/dzmm-browser`, `/var/log/dzmm`, `/var/backups/dzmm`, `/etc/dzmm`
- Create on new server: PostgreSQL application role and `dzmm` database

**Interfaces:**
- Consumes: old PostgreSQL role name/password verifier and old root-owned environment file.
- Produces: PostgreSQL 16 instance and filesystem ownership compatible with the existing systemd units.

- [ ] **Step 1: Install required packages**

Run on the new server:

```bash
sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
  postgresql postgresql-client python3-venv rsync \
  xvfb fluxbox x11vnc novnc websockify
```

Expected: `psql --version` and `pg_dump --version` report PostgreSQL 16; `systemctl is-active postgresql` reports active.

- [ ] **Step 2: Create the DZMM system user and directories**

Run on the new server:

```bash
sudo id dzmm >/dev/null 2>&1 || \
  sudo useradd --system --create-home --shell /usr/sbin/nologin dzmm
sudo install -d -o dzmm -g dzmm /opt/dzmm /var/lib/dzmm-browser /var/log/dzmm
sudo install -d -m 700 -o root -g root /etc/dzmm /var/backups/dzmm
```

Expected: `id dzmm` succeeds; application directories belong to `dzmm:dzmm`; configuration and backup directories belong to `root:root` with mode `0700`.

- [ ] **Step 3: Transfer the environment file and only the application PostgreSQL role verifier**

Transfer `/etc/dzmm/dzmm.env` through the authenticated SSH channel without displaying it, install it as `root:root` mode `0600`, and transfer a root-only SQL statement containing only the existing DZMM role name and SCRAM password verifier. Do not copy or modify the old `postgres` role.

Expected: an environment-key-only listing matches the old server; file mode is `0600`; no environment value appears in captured output.

- [ ] **Step 4: Create the application role and empty database**

Restore the single application role statement as the local PostgreSQL superuser, then create database `dzmm` owned by that role. Confirm the copied `DZMM_DATABASE_URL` connects locally from a root shell without printing the URL.

Expected: `select current_database(), current_user` through the copied URL returns database `dzmm` and the application role.

### Task 3: Deploy application code without activating external workers

**Files:**
- Create on new server: `/opt/dzmm/releases/83965d8/`
- Create on new server: `/opt/dzmm/current/`
- Create on new server: `/opt/dzmm/venv/`
- Install: `/etc/systemd/system/dzmm-*.service`
- Create: `/etc/systemd/system/dzmm-admin-web.service.d/port.conf`

**Interfaces:**
- Consumes: release archive from Task 1 and environment/database from Task 2.
- Produces: installed application and unit files, with every DZMM service stopped.

- [ ] **Step 1: Transfer and verify the committed release**

Stream the local archive through the new-host SSH control socket into a new release directory. Recompute SHA-256 before extraction and compare it to the local checksum.

Expected: checksums are identical; extracted `pyproject.toml` and Alembic revision `20260919_82` exist.

- [ ] **Step 2: Install the application and Chromium dependencies**

Run on the new server:

```bash
sudo rsync -a --delete /opt/dzmm/releases/83965d8/ /opt/dzmm/current/
sudo chown -R dzmm:dzmm /opt/dzmm/current
sudo python3 -m venv /opt/dzmm/venv
sudo /opt/dzmm/venv/bin/pip install --upgrade pip
sudo /opt/dzmm/venv/bin/pip install /opt/dzmm/current
sudo /opt/dzmm/venv/bin/playwright install-deps chromium
sudo -u dzmm /opt/dzmm/venv/bin/playwright install chromium
```

Expected: importing `dzmm_bot` from `/opt/dzmm/venv/bin/python` succeeds; Chromium executable exists beneath the `dzmm` home directory.

- [ ] **Step 3: Install units and set the new admin port**

Install all base units, then create the new-server-only override:

```ini
[Service]
ExecStart=
ExecStart=/opt/dzmm/venv/bin/python -m uvicorn dzmm_bot.admin.app:create_app_from_environment --factory --host 0.0.0.0 --port 18080
```

Store it at `/etc/systemd/system/dzmm-admin-web.service.d/port.conf`, run `systemctl daemon-reload`, disable AI memory, and leave all DZMM services stopped.

Expected: `systemctl cat dzmm-admin-web.service` shows the `18080` override; `systemctl is-enabled dzmm-ai-memory-worker.service` reports disabled; no target port is listening.

### Task 4: Rehearse database restore and local health

**Files:**
- Create on old server: `/var/backups/dzmm/<timestamp>/rehearsal.dump`
- Create on new server: `/var/backups/dzmm/rehearsal.dump`

**Interfaces:**
- Consumes: running old database and prepared empty new database.
- Produces: validated backup-transfer-restore procedure before downtime starts.

- [ ] **Step 1: Create and validate a live rehearsal backup**

From a root shell that sources `/etc/dzmm/dzmm.env`, run `pg_dump --format=custom --no-owner --no-privileges` against `DZMM_DATABASE_URL`. Run `pg_restore --list` and record `sha256sum`.

Expected: dump and list commands exit zero; the old production remains active.

- [ ] **Step 2: Transfer and checksum the rehearsal backup**

Stream the dump old → workstation → new over the two authenticated SSH channels. Compare SHA-256 on both hosts.

Expected: checksums match exactly.

- [ ] **Step 3: Restore rehearsal data**

Stop all new DZMM services, recreate the empty new database owned by the application role, and run:

```bash
pg_restore --exit-on-error --no-owner --no-privileges \
  --dbname="$DZMM_DATABASE_URL" /var/backups/dzmm/rehearsal.dump
```

Expected: restore exits zero; Alembic reports `20260919_82`; AI memory setting remains false.

- [ ] **Step 4: Test only core and admin locally**

Start core, wait for `curl -fsS http://127.0.0.1:18120/healthz`, start admin, verify local port `18080`, then stop both. Never start browser, ordinary AI, or AI memory during rehearsal.

Expected: core health reports database available; `18080` responds; `18090`, `19222`, and external workers remain inactive.

### Task 5: Enter the final write outage and capture final state

**Files:**
- Create on old server: `/var/backups/dzmm/<timestamp>/final.dump`
- Create on old server: `/var/backups/dzmm/<timestamp>/final-counts.json`
- Create on new server: `/var/backups/dzmm/final.dump`
- Replace on new server: `/var/lib/dzmm-browser/`

**Interfaces:**
- Consumes: proven rehearsal procedure.
- Produces: final immutable database dump, exact count manifest, and stopped browser profile.

- [ ] **Step 1: Stop old DZMM writers**

Run on the old server:

```bash
sudo systemctl stop \
  dzmm-browser-worker.service dzmm-ai-worker.service \
  dzmm-ai-memory-worker.service dzmm-admin-web.service dzmm-core.service
```

Expected: all five units report inactive; no DZMM Python process remains; PostgreSQL stays active; OpenClaw and unrelated services are unchanged.

- [ ] **Step 2: Capture final counts and final backup**

Generate the same all-table JSON manifest as Task 1 after services stop, then create the custom-format final dump and validate it using `pg_restore --list`. Record SHA-256 and file size.

Expected: every command exits zero; AI memory is false; the dump is nonempty and valid.

- [ ] **Step 3: Transfer final database and browser state**

Stream the final dump to new `/var/backups/dzmm/final.dump` and compare SHA-256. Stream a tar archive of old `/var/lib/dzmm-browser` after the browser worker is stopped, replace the prepared new directory, then restore `dzmm:dzmm` ownership.

Expected: final dump checksums match; browser directory size is within filesystem-block variance of the old 41 MB baseline; no new DZMM service has started.

### Task 6: Restore final data and perform pre-start validation

**Files:**
- Replace on new server: PostgreSQL database `dzmm`
- Read: final count manifest

**Interfaces:**
- Consumes: final dump/profile from Task 5.
- Produces: a validated but still offline new production database.

- [ ] **Step 1: Recreate and restore the production database**

Terminate only sessions connected to the new rehearsal database, drop and recreate it with the application owner, then restore `final.dump` using `--exit-on-error --no-owner --no-privileges`.

Expected: restore exits zero and `pg_restore --list` remains valid.

- [ ] **Step 2: Compare exact database manifests before starting services**

Generate all-table exact counts from the restored new database and compare them to `final-counts.json`. Check database size, Alembic `20260919_82`, and AI memory false.

Expected: every table count matches exactly; schema revision matches; no business service is active.

- [ ] **Step 3: Verify ownership, ports, and disabled memory worker**

Check `/etc/dzmm/dzmm.env` mode `0600`, browser profile owner `dzmm:dzmm`, admin override `18080`, target ports free, and memory worker disabled/inactive.

Expected: all checks match the design before any production worker starts.

### Task 7: Start the new production and verify cutover

**Files:**
- Runtime state only.

**Interfaces:**
- Consumes: validated final database and browser profile.
- Produces: active new production with old production stopped.

- [ ] **Step 1: Start core and verify health**

Enable/start PostgreSQL and DZMM core. Poll `/healthz` for at most 30 seconds.

Expected: database available is true; no restart loop; core listens only on `127.0.0.1:18120`.

- [ ] **Step 2: Start admin and ordinary AI worker**

Enable/start admin and ordinary AI. Verify admin listens on `0.0.0.0:18080`, nothing listens on `18090`, and ordinary AI remains active after 10 seconds. Keep AI memory disabled/inactive.

Expected: both intended services active; memory worker inactive.

- [ ] **Step 3: Start browser worker last**

Enable/start browser only after every earlier check passes. Verify worker heartbeat age, login state, CDP port, and recent logs.

Expected: browser is ready/listening without requiring login. If login is not ready, stop browser and pause for user login rather than starting old and new workers together.

- [ ] **Step 4: Verify externally visible behavior**

From the workstation, access `http://49.234.20.159:18080/` and confirm the expected admin response. Ask the user to send one low-risk read command in the configured group and verify one inbound record and one successful outbound delivery appear on the new server.

Expected: new IP and port work; one command round-trip succeeds; old DZMM services remain inactive.

- [ ] **Step 5: Observe for five minutes**

Sample health, service state, restart counts, CPU, memory, pending outbound count, worker queues, and warning/error logs at the start and end of five minutes.

Expected: no restart count increase, no persistent warning, no queue growth, and stable resource use.

### Task 8: Close the migration or execute rollback

**Files:**
- Preserve all old and new backups.

**Interfaces:**
- Consumes: Task 7 verification evidence.
- Produces: either an accepted new production or a consistent rollback.

- [ ] **Step 1: Success handoff**

If all validation passes, leave old DZMM services stopped and disabled from accidental boot, but do not delete files or PostgreSQL data. Record new service states, final backup checksum, release commit, and admin URL in the migration report.

Expected: only new DZMM services are active; old OpenClaw and unrelated services remain unchanged.

- [ ] **Step 2: Pre-traffic rollback if required**

If failure occurs before browser accepts real traffic, stop all new DZMM services and restart old core, admin, ordinary AI, and browser in dependency order. Keep both AI memory workers disabled.

Expected: old health and message processing return; new services are all inactive.

- [ ] **Step 3: Post-traffic rollback if required**

If new browser has accepted any real traffic, stop all new DZMM writers, dump the new database, restore that dump to the stopped old database, transfer the latest new browser profile back, compare manifests, then restart old services. Never restart the old browser from its stale pre-cutover database.

Expected: no accepted inbound, balance transaction, or outbound state is lost during rollback.
