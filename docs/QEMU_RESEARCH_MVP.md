# QEMU/KVM research MVP: one VPS is enough for metadata discovery

## Practical deployment situation

Slipcage-smol is **not** installed on the existing VPS. That VPS belongs
to the original `soybeanfarmer/slipcage` release channel and holds its
own database, operational journal, guest evidence and local backups.
Do **not** run smol bootstrap, release deployment, guest experiments,
build/test automation or alternate research database writes against
the existing VPS. The fresh-host-only gate is deliberate.

**You do not need a second VPS to start advisory discovery.** This
repository provides a *manually dispatched GitHub Actions job* that
reads only public vulnerability advisory feeds into an ephemeral
GitHub-hosted runner. It produces a SQLite research snapshot and a
small JSON shortlist as workflow artifacts.

## One-click public-advisory research snapshot

1. Open GitHub → `soybeanfarmer/slipcage-smol` → **Actions** →
   **QEMU research snapshot (public metadata only)**.
2. Select `main` and **Run workflow**; choose 7, 14, or 30 days
   for the NVD **publication-date** backfill.
3. Review the run. If both live feeds fail or the NVD publication
   search exceeds its bounded per-keyword result window, the job
   fails visibly. Try a shorter window or review the API status;
   do not loosen limits or run an automatic bulk scrape.
4. On success, download the 7-day-retained artifact
   `qemu-public-research`. It contains:
   - `qemu-public-research.sqlite3` with **public advisory metadata**,
     scored leads and source/patch references; and
   - `qemu-leads.json` with up to 15 top QEMU/KVM leads ordered by
     deterministic **research-fit** scores, *not* by confirmed
     vulnerability or exploitability.
5. Manually review each promising advisory against upstream QEMU
   source/patch references. Published descriptions are not proof
   of an exploitable vulnerability and **must not be executed**.

This workflow is **manual only**, uses `contents: read` permissions,
has a 10-minute GitHub runner budget, and makes outbound requests
only to the configured public GitHub advisory and NVD endpoints.
It does not fetch or run PoCs, check out vulnerable upstream QEMU
code, launch QEMU/KVM, scan networks, open ports, run tests against
the hosting provider, or change a VPS.

**Artifact caution:** On public repositories, workflow summaries and
artifacts may be accessible to others. They contain **only public
advisory data**; never add your private research DB, guest logs,
server credentials, tokens, IP addresses or unpublished findings.
The artifact is an ephemeral *research snapshot*, not a continuously
operating hosted database or a backup.

## How the focus and backfill work

- The ordinary smol `discover.sh` adds `--focus qemu` when collecting
  public GHSA and recent-modified NVD metadata. It keeps the existing
  guarded Dagu queue/SQLite attempt-fencing **when deployed to a
  separately approved fresh smol host in the future**.
- The new `backfill-qemu` subcommand queries NVD for **QEMU** and
  **KVM** terms across an *explicit* 1–30-day publication window.
  Each keyword has no more than **three 200-item pages**. Results
  are gathered *before* making database writes: feed failures,
  oversized results or incomplete pages must not leave a partial
  backfill. Each NVD CVE is merged by stable source ID.
- `qemu-leads` is read/report only: outputs JSON with source,
  CVE, research-fit score, optional allowlisted upstream commit
  links, and advisory status. It does not enqueue reviews or run
  a guest. All output remains tagged as **unverified metadata**.

For an explicit, local metadata-only historic window on a workstation
(not the original production VPS):

```sh
python3 app/isolab.py backfill-qemu --db ./research-sample.sqlite3 \
  --start-day 2026-09-01 --end-day 2026-09-14
python3 app/isolab.py qemu-leads --db ./research-sample.sqlite3 --limit 15
```

Change dates deliberately; older searches require manually
selected, nonoverlapping bounded windows. No automatic bulk
historical crawling or stealth scanning is provided.

## First operational acceptance checks

- [ ] CI unit regressions succeed without live network or VM tests.
- [ ] Manual GitHub Actions workflow runs to completion.
- [ ] Artifact contains at least one real QEMU/KVM advisory with a
      source URL, with no fabricated vulnerability claim.
- [ ] Repeated searches of the same publication window do not
      duplicate the same NVD CVE in SQLite.
- [ ] Operator reviews three source-backed leads and records which
      versions/subsystems need closer examination.
- [ ] Existing original VPS database, deployed SHA, backups,
      timers and guest evidence remain unchanged.

This stage is **advisory hunting**, not active pentesting,
zero-day discovery, QEMU exploit reproduction or upstream patch
validation. A later approved bounded source-build/unit-test stage
requires an isolated environment with explicit authorization.
GitHub-hosted CI can validate our own Python code and inert fixture
data, but is **not** a substitute for an approved hypervisor attack lab.
