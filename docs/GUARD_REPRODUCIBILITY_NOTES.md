# Future guard reproducibility work

The guarded staging upgrade is a research prototype, not an approved live
switch. Its CLI `switch` remains disabled. These notes preserve findings from
older prototype branches; they are not deployment or recovery instructions.

## Before enabling a switch

A future design must establish, before any Docker mutation, that the preserved
image and pinned Compose snapshot can reproduce the old runtime. A matching
Compose config hash or captured environment alone does not prove this. Define
and independently validate provenance, probe creation, cleanup, networking,
external dependencies, and the runtime fields that must be compared. Test that
missing, invalid, or mismatched proof prevents every mutation. If direct calls to
`switch()` become a supported production interface, enforce the proof gate there
as well as in the CLI; the present Python helper is for research and is not a
supported production interface.

`staging_mcp/staging-upgrade/proof_compare.py` and its tests are retained as an
**offline comparison building block only**. It compares selected fields and
rejects ambiguous data, but requires networking disabled and a stopped probe. It
cannot establish equivalence for the networked staging service, create a safe
probe, establish provenance, or authorize a deployment. It is not wired into the
guard and must not be used as proof to enable the switch.

## Inventory and rehearsal ideas

The earlier staging-specific preflight was a point-in-time prototype, not a
migration or durable rollback mechanism, and has not been retained as an operator
command. If a new preflight is designed, consider tests for invalid candidates
before I/O, exclusive root-only capture, untrusted paths, occupied rollback tags,
configuration/image drift, and duplicate environment entries. Captures can
contain complete identities and other secrets; never print them.

An earlier rehearsal created and removed its own uniquely named Podman VM and
refused to run if another machine was running. This offers a possible isolation
technique for a future rehearsal, but requires provisioning a machine and is not
itself evidence of production Docker equivalence. The current rehearsal's stated
limits continue to apply.
