# unbolt

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

**Status:** early scaffold. Package metadata, license, and CI/CD are set
up; the parser, DSL, and mapping engine haven't been built yet.

## Install

Not yet published to PyPI. Once released:

```bash
pip install unbolt
```
