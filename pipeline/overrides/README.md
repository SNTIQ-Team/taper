# Corrections to register records

Each YAML file records one correction and its source. The build applies the files in filename order after loading the source snapshots. A later rebuild reads the same correction until a maintainer updates or removes it. [Implementation](../build_db.py)

## Actions

| Action | Effect |
| --- | --- |
| `set` | Update fields on the matched authority, such as its telephone number. This is the default action. |
| `add_authority` | Add an authority with the supplied contact details and competence assignments. |
| `remove_competence` | Remove an assignment for a specific kind of work. Optional level and area filters narrow the match. |

Use an external identifier when it identifies one record. An exact active authority name can also be matched, optionally with its kind. The build reports unmatched corrections and skips them. [Berlin immigration office example](2026-06-11-berlin-lea.yaml)

## A correction in context

Berlin's Business Immigration Service handles employers and skilled workers. One correction removes its general immigration assignment for Berlin. A companion file assigns the general office to the Landesamt für Einwanderung. The original snapshot remains available for comparison. [Removed assignment](2026-06-11-berlin-bis-demote.yaml) · [General office assignment](2026-06-11-berlin-lea.yaml)

The `reason` field explains the discrepancy. `source` links to the supporting material and `date` records the observation. For assignments created by `add_authority`, the build copies `expires` into the evidence as a review date. The correction stays in the build until its file changes.
