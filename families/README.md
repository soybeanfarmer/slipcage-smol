# Experiment families

Experiment families are reviewed, bounded queue producers. A family may only
select the existing `fixed_arithmetic_sha256_v1` runner, choose cycle counts
from 1 through 3, reserve a starting `EXP-XXXX` ID, and set a bounded
repetition count.

No approved family is included by default. Adding a `FAM-XXXX.json` file is
therefore an explicit reviewed decision that creates new guest work after a
release is manually approved and deployed.

Example shape (documentation only):

```json
{
  "schema_version": 1,
  "id": "FAM-0001",
  "status": "approved",
  "runner": "fixed_arithmetic_sha256_v1",
  "experiment_id_start": 1000,
  "cycles": [1, 2, 3],
  "repetitions": 10
}
```

That example deterministically expands to 30 ordinary experiment manifests.
The global expanded queue remains capped at 500 items. Unknown fields, runner
names, cycle values, overlapping IDs, commands, URLs, image selectors and
network controls are rejected.
