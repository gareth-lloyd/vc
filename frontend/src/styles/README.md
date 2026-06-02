# Theme system

All visual decisions live in `globals.css`. Components read tokens, never raw
colours. Re-skinning the app — or branding it for a partner — is a single-file
edit.

## Token layers (top → bottom)

```
Component             ← consume utility (bg-primary, text-success)
   ↑
@theme inline         ← exposes CSS vars as Tailwind utilities
   ↑
Semantic surfaces     ← --primary, --background, --status-success, …
   ↑
Ramps                 ← --brand-*, --accent-*, --neutral-*
```

Edit the lowest layer needed for what you want to change:

- **Whole rebrand** → edit the ramps (`--brand-*`, `--accent-*`, `--neutral-*`)
  in `:root`. Everything cascades.
- **One status hue** (e.g. make "warning" orange instead of amber) → edit
  `--status-warning` in `:root`.
- **Service colour** → edit `--svc-{name}`.

## Available tokens

| Family       | Tokens                                                                |
| ------------ | --------------------------------------------------------------------- |
| Brand ramp   | `--brand-50` … `--brand-900`                                          |
| Accent ramp  | `--accent-50` … `--accent-900` (warm gold)                            |
| Neutral ramp | `--neutral-0` … `--neutral-900` (warm-tinted grey)                    |
| shadcn       | `--background`, `--foreground`, `--card`, `--primary`, `--accent`, …  |
| Status       | `--status-success / warning / danger / info / neutral / hold`         |
| Tier         | `--tier-quintessential`, `--tier-signature`                           |
| Service      | `--svc-car / transfers / boat / chef / grocery / firstnight / …` (13) |
| Lead status  | `--lead-hot / warm / cold / dead`                                     |
| Navigation   | `--nav-active`, `--nav-active-foreground`, `--nav-hover`              |
| Typography   | `--font-sans` (Inter), `--font-serif` (Fraunces), `--font-mono`       |
| Radii        | `--radius`, `--radius-sm / md / lg / xl / pill`                       |
| Shadows      | `--shadow-card / popover / modal`                                     |

## How to consume

### From Tailwind classes

Tokens exposed via `@theme inline` become utilities:

```tsx
<div className="bg-primary text-primary-foreground">…</div>
<span className="bg-success/10 text-success border-success/40">Paid</span>
<h1 className="font-serif text-3xl">Villa Anemoi</h1>
```

### From TypeScript (data-driven palettes)

When the colour is picked by data (concierge service, lead status, tier), use
the typed helpers in `tokens.ts`:

```tsx
import { serviceColorVar, type ServiceKey } from "@/styles/tokens";

<span
  className="inline-block size-3 rounded-full"
  style={{ backgroundColor: serviceColorVar[service] }}
/>;
```

The `var(--…)` value still lives in CSS, so a re-skin is still one file.

## Adding a new status tone

1. Add the OKLCH value to `:root` in `globals.css`:
   ```css
   --status-newtone: oklch(0.6 0.15 100);
   ```
2. Expose it in `@theme inline`:
   ```css
   --color-newtone: var(--status-newtone);
   ```
3. Add it to `STATUS_TONES` + `statusToneVar` in `tokens.ts`.

Consumers can now write `bg-newtone/10 text-newtone`.

## Reference components

- `components/data/StatusBadge.tsx` — six-tone status pill.
- `components/data/ServiceDot.tsx` — coloured concierge-service dot with
  service-status overlay.
- `components/data/TierBadge.tsx` — Quintessential / Signature concierge tier.
