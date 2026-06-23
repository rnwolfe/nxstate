---
title: Quickstart
description: Install nxstate and gather read-only state from a Cisco Nexus switch.
owner: rnwolfe
lastReviewed: 2026-06-23
---

> Stub — to be filled by the harvest-docs pass from the repo README and source.

Install and run your first read against a switch:

```bash
uv tool install nxstate
export NXSTATE_HOST=sw1 NXSTATE_USERNAME=netops NXSTATE_PASSWORD=...
nxstate doctor
nxstate system version --json
```
