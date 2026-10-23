# Performance

Estimated and measured numbers are never mixed - goal.md section 4/12. An estimate is arithmetic from byte sizes already computed in Phase 1; a measurement is a real timed run, with its environment recorded alongside it.

## Measured: pipeline stage timings (dated 2026-10-23)

Environment: Python 3.12.11, Windows-11-10.0.26200-SP0, AMD64 Family 23 Model 96 Stepping 1, AuthenticAMD.

| Stage | Rounds | Mean | Stdev | Min | Max |
|---|---|---|---|---|---|
| parse (100 fields) | 10 | 0.65 ms | 0.05 ms | 0.62 ms | 0.79 ms |
| build_dsl (100 fields) | 10 | 0.65 ms | 0.03 ms | 0.61 ms | 0.72 ms |
| recommend_mappings, go (100 fields) | 10 | 3.12 ms | 0.37 ms | 2.78 ms | 4.07 ms |
| generate_code, go (100 fields) | 10 | 1.25 ms | 0.24 ms | 1.03 ms | 1.74 ms |
| parse (1000 fields) | 10 | 7.37 ms | 1.63 ms | 6.32 ms | 11.84 ms |
| build_dsl (1000 fields) | 10 | 6.99 ms | 1.08 ms | 6.27 ms | 9.10 ms |
| recommend_mappings, go (1000 fields) | 10 | 30.49 ms | 2.83 ms | 25.56 ms | 33.42 ms |
| generate_code, go (1000 fields) | 10 | 10.71 ms | 1.22 ms | 9.04 ms | 13.03 ms |
| parse (10000 fields) | 10 | 89.88 ms | 8.90 ms | 75.69 ms | 101.33 ms |
| build_dsl (10000 fields) | 10 | 72.74 ms | 6.84 ms | 66.38 ms | 85.87 ms |
| recommend_mappings, go (10000 fields) | 10 | 348.67 ms | 22.76 ms | 314.54 ms | 383.08 ms |
| generate_code, go (10000 fields) | 10 | 119.66 ms | 41.54 ms | 94.58 ms | 199.62 ms |

## Estimated: real fixtures

| Fixture | COBOL bytes | Go bytes |
|---|---|---|
| `flat_display.cpy` | 18 | 14 |
| `nested_groups.cpy` | 25 | 16 |
| `occurs_table.cpy` | 76 | 63 |
| `redefines_overlay.cpy` | 30 | 39 |

## CI regression budget

Not wired into CI yet: goal.md section 4 says to set the budget from the first real measurement, not a guess - the table above *is* that first measurement, recorded 2026-10-23. A regression check needs a prior run to compare against, which doesn't exist until this has been measured again at least once. Revisit once there's a second data point.
