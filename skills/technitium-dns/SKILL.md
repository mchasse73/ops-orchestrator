---
name: technitium-dns
description: Manage INTERNAL DNS records on Technitium (LAN-authoritative zones like *.lab.local seen from inside).
---

# Technitium DNS

Technitium serves the **internal/authoritative** view. For domains that are local primary
zones, internal clients only see records that exist here — a public Dynu record alone gives
LAN users NXDOMAIN.

## Procedure
1. Add forward record on the primary (NS1): `technitium__add_record(zone, fqdn, type, value)`.
2. For hairpin parity with the public name, point it at the same gateway IP the public
   record uses (so internal browsers reach the proxy and get the valid TLS cert).
3. The secondary (NS2) syncs from NS1 — if it lags, trigger a resync so both resolve.
4. Verify with both resolvers before declaring done.

## Important
- Never write to the secondary directly; it's secondary-only.
- Deleting/overwriting a live record is destructive — confirm first.
