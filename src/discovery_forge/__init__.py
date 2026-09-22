"""Forge adapters for the discovery runtime — deliberately outside the core.

`discovery` (the core) contains no network or process-launch adapter; that
is its author ≠ execute boundary as a capability (DESIGN-016), and
`tests/test_boundary.py` walks its import graph to prove it. This package
is where such an adapter is allowed to live: it implements
`discovery.forge.Forge` and is imported only inside `discovery.cli`'s
composition seam, never at module level of any core module.
"""
