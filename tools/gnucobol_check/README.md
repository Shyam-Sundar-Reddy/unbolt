# GnuCOBOL cross-check

A local, dev-only sanity check for `src/unbolt/datatypes/sizing.py`.
**Not** part of CI, and not a change to decision 0001 — IBM Enterprise
COBOL stays the documented target dialect; GnuCOBOL is just a free
compiler we can actually run, used here only to independently verify
byte sizes via `LENGTH OF`.

What it checks: for every field in every `fixtures/*.cpy`, does
GnuCOBOL's own `LENGTH OF <field>` agree with unbolt's `build_dsl()`
byte size? This exercises real compiler logic for group/`OCCURS`/
`REDEFINES` sizing without reading a line of our code.

What it does **not** check: EBCDIC byte content, overpunch sign
encoding, or TRUNC(STD) range semantics exactly as IBM defines them —
GnuCOBOL's defaults aren't guaranteed to match IBM Enterprise there.

## Run it

```bash
docker build -t unbolt-gnucobol-check tools/gnucobol_check
uv run python tools/gnucobol_check/check.py
```
