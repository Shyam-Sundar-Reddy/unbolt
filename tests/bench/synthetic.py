"""Synthetic copybooks for benchmarking - not hand-written fixtures,
generated at a requested field count so the harness can scale up
without a 10,000-line file checked into the repo.
"""


def synthetic_copybook(field_count: int) -> str:
    lines = ["01  BENCH-RECORD."]
    for i in range(field_count):
        lines.append(f"    05  FIELD-{i:06d} PIC 9(5).")
    return "\n".join(lines) + "\n"
