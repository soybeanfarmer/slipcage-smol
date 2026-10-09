# Smol development VPS and release channel

The development VPS has been reinstalled with Ubuntu 24.04 and
enrolled in **`soybeanfarmer/slipcage-smol`**, using its root-private
`/etc/slipcage/release-channel` marker. Do not rerun the
fresh-host bootstrap on an enrolled server.

The pull deployer checks the latest published non-draft,
non-prerelease Smol release, validates the commit is on `main`
and that GitHub Actions `validate` passed, and runs Ansible under
the deployment-maintenance/drain gate. The release workflow requires
explicit operator approval.

## Advisory subsystem retirement

The first release with this change takes one final verified legacy
SQLite-plus-reports backup before removing `slipcage-discover.*`,
`slipcage-review.*` and the old Python advisory/queue code.
It does not delete the previous SQLite database, Markdown reports,
or prior root-private backup directories. The ongoing daily backup
service switches to reports-only snapshots and weekly scratch restore
assurance remains active. A failure to preserve the legacy snapshot
stops the installer before the retire operation.

## Verify a release

```bash
sudo cat /var/lib/slipcage/deployed-sha
sudo systemctl list-timers --all 'slipcage-*' --no-pager
sudo systemctl --failed --no-pager
sudo journalctl -u slipcage-pull-deploy.service -n 80 --no-pager
sudo cat /var/lib/slipcage-assurance/status.json
```

Only the VPS operator runs these host commands. Do not disable release
gates, overwrite the deployed SHA, remove the maintenance guard, or
share SSH keys/secrets. The archive and backups are root-private and
must not be committed to the public repo.

No experiment queue/consumer or GitHub result writer has been deployed
in this release. Manual benign guest checks remain disabled by default.
