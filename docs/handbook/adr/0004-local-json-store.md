# ADR-0004: Local JSON store by default, Supabase/Postgres optional

- **Status:** accepted
- **Date:** 2026-11-13
- **Superseded by:** —

## Context

The spec named Supabase (Postgres + Storage) as the data layer (`../../../SPEC.md` sections 3 and 10). On 13 Nov
the build had no Supabase project and had to run and be tested without one (SPEC section 18).

## Options considered

| Option | Status in the sources | Why it lost or won |
|---|---|---|
| `LocalStore`: one JSON file (`data/local_db.json`), outputs on local disk | chosen as the default; SPEC section 18 | runs and tests with no external service |
| `SupabaseStore` when `SUPABASE_*` is set | built; never configured on the running setup (SPEC section 20, 21 Nov) | needs a project and keys |
| v1 Postgres store (`V1_STORE=postgres`, `app/v1/store_pg.py`) | written 23 Nov, **never run** against a database (`../../v1/PROGRESS.md` phase 2; `../../v1/NEEDS_APPROVAL.md` item 14) | no database on the laptop |

## Decision

`db.get_store()` returns `SupabaseStore` when `SUPABASE_*` is set, else `LocalStore`. In v1, `V1_STORE=json` is the
default and the recommendation; `postgres` is optional and untested (`../../v1/SUMMARY.md` section 2).

## Consequences

### Good

- The whole product ran end to end on one laptop with no database (SPEC section 18).
- v1 got its own store file in its own data folder, so v1 never touches v0's data (ADR-0018).

### Bad

- One process, one file. The backend holds the store in memory and writes it on every change; two processes on the
  same file overwrite each other (`../../v1/DISCOVERY.md` section 4, risk 6).
- This caused an incident on 21 Nov: a repair script wrote the store while the server ran, the server wrote its old
  copy back, and one voice profile's stored text no longer matched its sample file. Effect: lines at 250-300 ms a
  word instead of 455-555, words heard back 53-73% (**measured**, SPEC section 20, 8 lines a language). See INC-03
  in [`../INCIDENTS.md`](../INCIDENTS.md). Rule since then: never write the local store from a script while the
  server runs.
- No multi-user hosting on it; SPEC section 20 lists "Data" as missing for a product.
- No backup has run: the backup script exists, no bucket is set (`../../v1/NEEDS_APPROVAL.md` item 15).

## Evidence

- Commits: `df1fa91`/`f488544` (`LocalStore`), `e89487c`/`1304aa8` (ignore `backend/data`), `421d133` (v1 Postgres store, never run)
- Sources: [`SPEC.md`](../../../SPEC.md) sections 10, 18, 20;
  [`DISCOVERY.md`](../../v1/DISCOVERY.md) section 4 and risks;
  [`NEEDS_APPROVAL.md`](../../v1/NEEDS_APPROVAL.md) items 14-15
