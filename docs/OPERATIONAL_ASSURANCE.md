# Slipcage-smol — Local Operational Assurance (v0.10 lineage)

Smol retains v0.10's backup and health verification without
enabling more workloads. These instructions apply only to a separately
approved fresh smol host—not the original production VPS. Guest VM
execution remains manual. Nothing here
starts QEMU, fuzzes, sends off-VPS backup copies, changes the production DB
or authorizes provider-boundary tests.

## 1. Weekly bounded, local scratch restore of the latest backup

The new slipcage-assurance.timer runs once per week on **Sunday around
04:30 UTC** (up to 90 minutes randomized delay). Its read-only backup
assurance service selects the latest completed backup under
/var/backups/slipcage, verifies SHA-256 files and backup SQLite integrity
using the existing slipcage-restore-check code, restores its SQLite/report
contents into a private temporary cache directory, checks the resulting
SQLite candidate count and report count, then removes only that unique
temporary directory. It **never writes into** /srv/isolab, live reports
or the backup source, and does not change daily backup retention.

The service is network-isolated, no devices, filesystem-protected, with
MemoryMax=512M, CPUQuota=35%, TasksMax=32, LimitFSIZE=768M,
TimeoutStartSec=10min, and low I/O scheduling priority. The runner
fails closed on backed-up DBs above 256 MiB, archives above 512 MiB,
or insufficient scratch disk (requires >2 GiB plus twice input sizes).
These caps may cause a larger future backup to fail assurance; this is
an alert to redesign the resource budget, not permission to discard
or truncate data.

After an approved release, manually establish the initial health record
*before* interpreting v0.10 hourly health alerts:

    sudo systemctl start slipcage-pull-deploy.service
    sudo cat /var/lib/slipcage/deployed-sha
    sudo systemctl start slipcage-assurance.service
    sudo journalctl -u slipcage-assurance.service -n 40 --no-pager -l
    sudo systemctl start slipcage-health.service
    sudo journalctl -u slipcage-health.service -n 40 --no-pager -l

The assurance service writes
/var/lib/slipcage-assurance/status.json, root-private 0600.
Expect passed=true, live_data_modified=false, and a valid backed-up
candidate/report count. Health monitoring now requires a passed restore
status no more than 10 days old. Before the first scratch check, health
will correctly warn restore_assurance:never_checked. If the scratch
check fails, investigate its status and disk capacity rather than
retrying repeatedly. A forced SIGKILL/system crash may leave an
unverified scratch directory requiring *manual* inspection: no
unattended cleanup of unknown residue is added.

This validates a *local backup* but cannot protect against losing
the entire VPS. Encrypted off-server backups remain deferred.

## 2. Local health alerts (no remote notifier)

Smol retains the **hourly passive health checker**
(`slipcage-health.service`) and its local status record
(`/var/lib/slipcage-health/status.json`). Each check writes JSON to
the local systemd journal. On a change in issue codes, it emits
`SLIPCAGE_HEALTH_WARNING` or `SLIPCAGE_HEALTH_RECOVERED`;
repeat warnings are deduplicated in the journal transition stream.

Read-only checks on a **separately enrolled smol host**:

    sudo cat /var/lib/slipcage-health/status.json
    sudo journalctl -u slipcage-health.service -n 50 --no-pager -l
    sudo systemctl status slipcage-health.timer --no-pager

Smol does **not** install the optional v0.10 HTTPS webhook dispatcher
or its systemd service/timer. No external notification transport is
configured or promised, and there is no notification credential
workflow. Local journal warnings require an operator to read them.
If off-VPS alerts are ever needed, review them as a separate feature
with an explicit destination and security/privacy requirements.

## 3. Incident response

See [Incident Runbooks](INCIDENT_RUNBOOKS.md) for triage of:
- missing or unverifiable backups and failed scratch restores;
- low disk space;
- interrupted disposable VM experiments;
- failed release pull deployments;
- Dagu/recovery service failures;
- inspecting locally retained health warnings and status.

All runbooks use **read-only checks first**. They do not authorize
automatic deletion, forced service restarts, database replacement
or executing new VM/fuzzing payloads.

## Human release gates

1. CI offline tests and service/Ansible review must pass.
2. Merge a reviewed change; if an independent fresh smol host has been
   separately approved, publish a **smol repository** release manually.
3. On that separate host only, check the smol deployed SHA.
4. Run bounded restore assurance once and inspect the local hourly
   health status; no external notifications or guest experiments are
   activated by this process.
5. Preserve the original Slipcage VPS deployment and all its data.
   An in-place migration is not covered by this document.

This is not a full disaster recovery service or hypervisor security
assurance. It is deliberately conservative operational evidence.
