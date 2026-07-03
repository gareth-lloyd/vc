# 02 · Administration

System-wide lookup data (geography, currency, taxonomies) and system configuration. These are the slow-changing reference values that everything else depends on. Most are pushed downstream to the public WordPress site via the sync queue.

## Files

| File | Workflows |
|---|---|
| [`geographic-taxonomy.md`](./geographic-taxonomy.md) | Manage countries (CRUD + reorder), manage regions (CRUD) |
| [`financial-taxonomy.md`](./financial-taxonomy.md) | Manage currencies (CRUD + reorder + set-default) |
| [`product-taxonomy.md`](./product-taxonomy.md) | Manage collections, manage groups, manage tags / features (CRUD + reorder), map villas into collections |
| [`system-configuration.md`](./system-configuration.md) | General config (system name/URL/API key), website (multi-tenant target sites), global email config, property default settings (default deposit %, commission, etc.) |

## Entities touched

- `VillaCountry` (`Id`, `Name`, `ShortName1`, `ShortName2`, `Code`, `TaxRate`, `IsActive`, `Order`, `SyncId`, plus standard audit columns)
- `VillaCurrency` (`Id`, `Name`, `CurrencyCode`, `Symbol`, `IsShowAfter`, `IsDefault`, `Order`)
- `Regions` (`Id`, `Name`, `CountryId`, `Slug`)
- `VillaGroup` (multiplexed for collections **and** groups — discriminator in code)
- `VillaCollectionsMappings` (junction: villa ↔ collection)
- `VillaFeatures` (`Id`, `Name`, `Description`, `ServiceType` ∈ {10=ContactService, 20=PropertyFeature}, `IconId`, `IconName`, `CategoryId`, `Order`)
- `VillaFeaturesCategoryMapping` (junction: feature ↔ category)
- `VillaConfigGeneral`, `VillaConfigWebsite`, `VillaConfigEmail`, `VillaConfigPropertyDefault`

## Stored procedures

- `SP_COUNTRIES`, `sp_currencies`, `SP_REGIONS`, `sp_villa_groups` / `sp_groups`, `SP_CRUD_VILLA_FEATURES_TAGS`
- `SP_CRUD_VILLACONFIGGENERAL`, `sp_sites_register`, `SP_CRUD_VillaConfigEmail`, `SP_CRUD_VillaConfigPropertyDefault`

## Sync modules (push to WordPress public site)

Each module ID below is the `ResModule.*` enum constant the legacy code uses when queueing a sync:

| Entity | Module | Endpoint on WordPress side |
|---|---|---|
| Countries | `ResModule.COUNTRY` | `/WP_Sync_Country` |
| Regions | `20` (numeric literal in code) | `/WP_Sync_Regions` |
| Collections | `40` (numeric literal) | `/WP_Sync_Collections` |
| Features | `ResModule.FEATURE` | `/Sync_key_feature` |

Currencies and groups have **no** downstream sync — they are local-only.
