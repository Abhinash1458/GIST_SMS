# GIST SMS demo data

## Load the demo

From the project root:

```powershell
python -m scripts.seed
```

The command resets the configured database to an empty schema, loads the same
fixed-seed dataset every time, and prints record counts plus one login for
each role.

> **Warning:** The fixed passwords are for classroom demonstrations only.
> Never use them for real users or production data.

## Demo logins

| Role | Username | Password | Dashboard |
|---|---|---|---|
| Management | `management@college.edu` | `Admin@123` | `/management` |
| HOD | `hod.cse@college.edu` | `Hod@123` | `/hod` |
| Mentor | `mentor.cse.2026a@college.edu` | `Mentor@123` | `/mentor` |
| External trainer | `trainer1@college.edu` | `Trainer@123` | `/trainer` |
| Student | `26CSE001` | `Student@123` | `/student` |

All HOD, mentor, and trainer accounts follow the same username pattern for
their department or index.

## Dataset summary

- 5 departments with an intake of 120
- 20 batches (2023–2026) and 40 sections
- 500 students, split into 12–13 students per section
- 40 mentor groups, with no group above 30 students
- 120 subjects and 240 teaching assignments
- 40 registrations: 30 pending, 5 sent back, and 5 rejected
- 3 notices

## Run the tests

```powershell
python -m unittest discover -s tests -v
```
