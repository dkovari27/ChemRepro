# Design

## Register

product (with brand surfaces on /, /about, /privacy)

## Color

Strategy: **Restrained** — one saturated primary, one accent, tinted neutrals.

| Role    | OKLCH                   | Hex        | Use |
|---------|-------------------------|------------|-----|
| bg      | oklch(1.000 0.000 0)    | #ffffff    | Page background |
| surface | oklch(0.975 0.005 160)  | #f2f7f5    | Cards, panels, inputs |
| primary | oklch(0.380 0.120 162)  | #0f6b47    | CTAs, links, active states, brand accents |
| accent  | oklch(0.680 0.120 082)  | #c49a38    | Tags, non-interactive highlights |
| ink     | oklch(0.150 0.020 165)  | #111c17    | Body text, headings |
| muted   | oklch(0.500 0.010 165)  | #5d706a    | Secondary text, placeholders, borders |

Semantic (not brand): amber #f59e0b (repro stars), blue-500 #3b82f6 (extension stars), red-500 (destructive).  
White text on primary fills (L 0.38, mid-dark). Dark ink on surface fills (L 0.975).

## Typography

Single family: **Inter Variable** (rsms.me/inter).  
Product rule: one well-tuned sans carries all roles — no serif pairing.

| Role       | Size            | Weight | Letter-spacing | Use |
|------------|-----------------|--------|----------------|-----|
| Display    | 2.5rem / 40px   | 700    | −0.025em       | Homepage hero h1 only |
| Heading 1  | 1.5rem / 24px   | 700    | −0.02em        | Paper title on paper page |
| Heading 2  | 1.125rem / 18px | 600    | −0.01em        | Section headers |
| Body       | 0.875rem / 14px | 400    | 0              | Review text, prose |
| Label      | 0.75rem / 12px  | 500    | +0.01em        | Meta, dates, authors |
| Mono       | 0.75rem / 12px  | 400    | 0              | DOIs |

Line length cap: 65ch on prose. Data columns/tables: unrestricted.  
`text-wrap: balance` on h1–h2. Body `leading-relaxed` (1.625).

## Spacing

Base unit: 4px. Content max-width: 64rem (1024px). Horizontal padding: 1rem (px-4).  
Card padding: 1.25rem (p-5). Section gap: 2rem (gap-8).

## Components

**Buttons**
- Primary: `bg-[#0f6b47] text-white rounded-lg px-4 py-2 font-medium` + hover `bg-[#0a4d33]`
- Ghost: `border border-slate-200 text-slate-600 rounded-lg px-4 py-2` + hover `border-slate-300 text-slate-800`
- Destructive: `text-red-600` only, no filled red buttons

**Cards**
- `bg-white border border-slate-200 rounded-xl p-5` + hover `border-[#0f6b47]/40 shadow-sm`
- Never nested cards.

**Inputs**
- `bg-[#f2f7f5] border border-slate-200 rounded-lg px-4 py-2.5` + focus `ring-2 ring-[#0f6b47]/25 border-[#0f6b47]/60`

**Nav**
- `bg-white border-b border-slate-200` — no shadow. Clean separation only.

**Badges / pills**
- Status: rounded-full, surface bg + colored text (no filled saturated pills in inactive states)

## Motion

- Transitions: 150ms `cubic-bezier(0.16, 1, 0.3, 1)` (expo-out). State changes only.
- No page-load sequences, no decorative entrance animations.
- `@media (prefers-reduced-motion: reduce)`: instant transitions (`transition: none`).
