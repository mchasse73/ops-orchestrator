---
name: dynu-dns
description: Manage PUBLIC DNS records on Dynu (add/list/delete A records for your public domains).
---

# Dynu DNS

Dynu hosts the **public** DNS for internet-facing services. Public service hostnames
resolve to the gateway's public IP (the reverse proxy), not to a backend directly.

## Procedure
1. `dynu__list_records(domain)` first to see what exists and avoid duplicates.
2. To publish a new public host, `dynu__add_a_record(domain, node_name, ipv4)`:
   - `node_name` is the host part only (`"x9print"`), not the FQDN.
   - `ipv4` is almost always the **public gateway IP**, not the backend's LAN IP.
3. Verify it resolves: the record propagates in a few minutes (TTL 300).

## Important
- A **public** Dynu record is not enough for internal clients — if the domain is also an
  authoritative local zone (e.g. Technitium serves it internally), add the matching
  internal record too (see the technitium-dns skill). Otherwise LAN users get NXDOMAIN.
- Deleting records is destructive — confirm the `record_id` with `list_records` first.
- Public exposure is a policy decision: a new public hostname should be approved before
  it goes live.
