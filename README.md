<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/Shyam-Sundar-Reddy/unbolt/main/docs/logo-wordmark-dark.svg">
  <img src="https://raw.githubusercontent.com/Shyam-Sundar-Reddy/unbolt/main/docs/logo-wordmark-light.svg" alt="unbolt" height="60">
</picture>

[![Tests](https://github.com/Shyam-Sundar-Reddy/unbolt/actions/workflows/ci.yml/badge.svg)](https://github.com/Shyam-Sundar-Reddy/unbolt/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

Turn COBOL copybooks into a versioned, language-independent DSL, explain
every Go/Java type choice, and generate traceable code — as a pure-Python
package, a CLI, and an MCP server.

Mainframe data definitions are hard to reuse in modern services. Teams
hand-translate copybooks and lose information: numeric ranges, decimal
scale, packed/binary storage, signedness, nesting, overlays (`REDEFINES`).
`unbolt` parses a copybook into an immutable DSL, recommends valid Go and
Java types with a written reason for every candidate, and generates
deterministic code with full traceability back to the source line.

## 30-second demo

![unbolt parsing a copybook, recommending a Go type with its rationale, generating code, and tracing the decision — a real terminal recording, not a mockup](https://raw.githubusercontent.com/Shyam-Sundar-Reddy/unbolt/main/docs/cli-demo.gif)

The same copybook in text, for anyone who'd rather read than watch:

```
$ cat account.cpy
01  CUSTOMER-RECORD.
    05  CUSTOMER-ID         PIC 9(6).
    05  CUSTOMER-AGE        PIC S9(3).
    05  ACCOUNT-BALANCE     PIC S9(7)V99.

$ unbolt generate account.cpy --target go -o out/
wrote out/gen.go
```

```go
// out/gen.go
type CustomerRecord struct {
	CustomerId     int32
	CustomerAge    int16
	AccountBalance int64
}

func ValidateAccountBalance(v int64) error {
	if v < -999999999 || v > 999999999 {
		return fmt.Errorf("ACCOUNT-BALANCE: %v outside -999999999..999999999", v)
	}
	return nil
}
```

**Why `ACCOUNT-BALANCE` (`PIC S9(7)V99`) became `int64`, not `float64`:**
`unbolt report account.cpy --target go` says exactly why —

> unscaled value fits int64 (-999999999.00..999999999.00); caller
> divides by 10^2 (decision 0002)

A float would silently lose cents on arithmetic; `unbolt` never defaults
decimal/packed fields to floating point, and the report always says
why a field got the type it got, not just what the type is.

## Install

```bash
pip install unbolt
pip install "unbolt[mcp]"   # adds the MCP server
```

## Quickstart

### Library

```python
from unbolt.parser import parse_copybook
from unbolt.dsl import build_dsl
from unbolt.mapping import recommend_mappings
from unbolt.generators import generate_code

source = open("account.cpy").read()
dsl = build_dsl(parse_copybook(source), source_file="account.cpy")
mapping = recommend_mappings(dsl, "go")
files = generate_code(dsl, mapping, "go")  # {"gen.go": "..."}
```

A full runnable version, including the validation and traceability
report, is in [examples/quickstart.py](examples/quickstart.py).

### CLI

```bash
unbolt parse account.cpy                        # diagnostics
unbolt recommend account.cpy --target go         # every candidate + why
unbolt generate account.cpy --target go -o out/  # write the code
unbolt report account.cpy --target go            # full traceability report
```

See [docs/cli.md](docs/cli.md) for every command and flag.

### MCP

```bash
pip install "unbolt[mcp]"
unbolt mcp   # stdio transport - copybooks never leave your machine
```

```json
{
  "mcpServers": {
    "unbolt": {
      "command": "uvx",
      "args": ["unbolt[mcp]", "mcp"]
    }
  }
}
```

See [docs/mcp.md](docs/mcp.md) for every tool's params/returns/errors.

## Supported / not supported

| | |
|---|---|
| Supported | Levels 01-49/77, `PIC` (numeric + alphanumeric), `DISPLAY`/`COMP`/`COMP-3`/`COMP-4`/`COMP-5`/`COMP-1`/`COMP-2`, `OCCURS n`, `REDEFINES`, `SIGN SEPARATE` |
| Diagnostic (reported, not converted) | Level 66 (`RENAMES`), `OCCURS ... DEPENDING ON`, `COPY ... REPLACING`, edited pictures (`Z`, `*`, `$`, ...) |
| Unsupported | `PIC N`/`G` (national/DBCS) |

Full matrix: [docs/supported-constructs.md](docs/supported-constructs.md).

## How it works

```
copybook text → parser → AST + diagnostics → DSL (immutable source facts)
                                              │
                    rules + overrides ────────┤→ mapping candidates + rationale
                                              │
                                              └→ generators → Go / Java + validators
                                                     └→ report (field ↔ source line ↔ rule)
```

## Docs

Full index: [docs/index.md](docs/index.md).

- [docs/supported-constructs.md](docs/supported-constructs.md) — the full construct matrix
- [docs/dsl-spec.md](docs/dsl-spec.md) — the DSL schema, field by field
- [docs/mapping-rules.md](docs/mapping-rules.md) — every Go/Java mapping rule and rationale
- [docs/diagnostics.md](docs/diagnostics.md) — every diagnostic code and how to fix it
- [docs/cli.md](docs/cli.md) / [docs/mcp.md](docs/mcp.md) — every command/tool
- [docs/performance.md](docs/performance.md) — estimated vs. measured, never mixed
- [docs/limitations.md](docs/limitations.md) — what doesn't work yet
- [CONTRIBUTING.md](CONTRIBUTING.md) · [LICENSE](LICENSE) (Apache-2.0)
