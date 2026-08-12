# CODA Design System — Master File

> **LOGIC:** When building a specific page, first check `design-system/pages/[page-name].md`.
> If that file exists, its rules **override** this Master file. Otherwise follow the rules below.

**Project:** CODA (internal data discovery / query tool)
**Generated:** 2026-07-29
**Design Dials:** Variance 2/10 (Centered / Minimal) · Motion 2/10 (Functional only) · Density 8/10 (Dense / Dashboard)

Generated with the `ui-ux-pro-max` skill (`styles.csv`, `colors.csv`, `typography.csv`), then hand-corrected: the
skill's own `--design-system` auto-picker initially matched "Exaggerated Minimalism" + a marketing landing-page
pattern (oversized hero type, scroll-reveal sections) — the wrong fit for a dense internal tool. This file instead
combines two better-matched entries from the same database: **Minimalism & Swiss Style** (explicitly "Best For:
Enterprise apps, dashboards, professional tools") for the visual language, and **Data-Dense Dashboard** (BI/Analytics
category) for density and layout conventions.

---

## 1. Style & Pattern

**Style:** Minimalism & Swiss Style
Clean, grid-based, functional, high-contrast, generous negative space, sans-serif, essential elements only. WCAG AAA-friendly by construction.

**Layout convention:** Data-Dense Dashboard
Multiple stat/KPI cards, per-item info cards, sortable/filterable tables, compact padding, sidebar + main content shell, maximum data legibility with minimum decoration.

**Explicit anti-patterns for this project** (from the brief — treat as hard constraints, not suggestions):
- ❌ No heavy or decorative gradients (a 1-2 stop subtle tint on a chart or focus ring is fine; gradient-filled cards/buttons are not)
- ❌ No neon or saturated accent colors
- ❌ No loud/attention-seeking animation — motion is functional only (state change, loading, focus), never decorative
- ❌ No glassmorphism / frosted blur for its own sake
- ❌ No emoji as icons — one consistent SVG icon set only (Heroicons or Lucide)
- ❌ No hover `translateY`/scale "lift" gimmicks on cards — indicate interactivity with border/shadow/color shift instead, so the UI reads as calm, not bouncy

---

## 2. Color Palette

Source: `colors.csv` → "Analytics Dashboard" entry. Blue is the neutral/functional primary (chrome, links, focus rings); amber is reserved for the single primary call-to-action per view (e.g. "Search", "Request Access") so it doesn't get diluted.

| Role | Hex | CSS Variable | Usage |
|------|-----|--------------|-------|
| Primary | `#1E40AF` | `--color-primary` | Active nav state, links, primary text on brand surfaces |
| Primary Foreground | `#FFFFFF` | `--color-primary-foreground` | Text/icons on primary-filled surfaces |
| Secondary | `#3B82F6` | `--color-secondary` | Secondary actions, chart series 1, info accents |
| Accent (CTA) | `#D97706` | `--color-accent` | The one primary CTA per screen (Search, Request Access, Approve) |
| Accent Foreground | `#FFFFFF` | `--color-accent-foreground` | Text on accent-filled buttons |
| Background | `#F8FAFC` | `--color-background` | Page background |
| Surface / Card | `#FFFFFF` | `--color-surface` | Cards, sidebar, modals, table rows |
| Foreground | `#1E293B` | `--color-foreground` | Primary body text (adjusted from generator's `#1E3A8A` — too blue-tinted for body copy at small sizes; this is standard slate-900 for real 4.5:1+ contrast) |
| Muted Foreground | `#64748B` | `--color-muted-foreground` | Secondary/help text, labels, timestamps |
| Muted Surface | `#E9EEF6` | `--color-muted` | Subtle section backgrounds, disabled fills |
| Border | `#E2E8F0` | `--color-border` | Card borders, dividers, table lines |
| Success | `#16A34A` | `--color-success` | Approved status, positive stats |
| Warning | `#D97706` | `--color-warning` | Pending status (reuses accent — status colors stay muted, not neon) |
| Destructive | `#DC2626` | `--color-destructive` | Rejected status, delete/reject actions |
| Ring | `#1E40AF` | `--color-ring` | Focus outline (visible, ≥2px, never removed) |

**Dark mode:** out of scope for v1 (current app doesn't have it either) but tokens are named semantically so a dark variant can be added later without touching components.

**Chart/series colors** (numeric histograms, categorical distributions in Column Information cards): reuse `--color-secondary` (`#3B82F6`) as the single default series color for bars/histograms. For multi-category charts (pie/doughnut, 2-6 slices), use a restrained qualitative set — no neon:
`#3B82F6` (blue), `#0EA5E9` (sky), `#64748B` (slate), `#D97706` (amber), `#16A34A` (green), `#7C3AED` (muted violet, sparingly).

---

## 3. Typography

Source: `typography.csv`. The auto-picker's "Dashboard Data" pairing (Fira Code heading + Fira Sans body) reads too
"developer console" for a tool used by non-engineers requesting data access — reserving monospace for what's
actually code/data keeps it purposeful instead of decorative.

- **UI font (headings + body):** **Inter** — the standard for Swiss-style enterprise dashboards (Linear, Vercel, Stripe dashboard, GitHub). Neutral, extremely legible at small sizes, huge weight range.
- **Mono font (SPARQL queries, column/type badges, row IDs, scan IDs):** **JetBrains Mono** — used only where content is literally code or an identifier, never for general UI text.

```css
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap');
```

```js
// tailwind.config
fontFamily: {
  sans: ['Inter', 'system-ui', 'sans-serif'],
  mono: ['JetBrains Mono', 'ui-monospace', 'monospace'],
}
```

**Type scale** (4px-rounded, dashboard-appropriate — nothing oversized):

| Token | Size / Line-height | Weight | Usage |
|-------|---------------------|--------|-------|
| `--text-xs` | 12px / 16px | 500 | Table meta, badges, timestamps |
| `--text-sm` | 13px / 20px | 400–500 | Body copy, table cells, form labels |
| `--text-base` | 14px / 22px | 400 | Default body |
| `--text-lg` | 16px / 24px | 600 | Card titles, section labels |
| `--text-xl` | 20px / 28px | 700 | Page titles ("Query Data") |
| `--text-2xl` | 24px / 32px | 800 | Stat card numbers |

Note: base is 14px, not the usual 16px web default — deliberate for `density: 8/10`, matching the existing product's information density. Never go below 12px for body/data text (accessibility floor).

---

## 4. Spacing, Radius, Shadow

**Spacing** (density 8/10 → dense/dashboard scale):

| Token | Value | Usage |
|-------|-------|-------|
| `--space-1` | 4px | Icon-to-label gaps |
| `--space-2` | 8px | Compact padding (badges, chips) |
| `--space-3` | 12px | Card internal padding, table cell padding |
| `--space-4` | 16px | Standard component gaps |
| `--space-6` | 24px | Section spacing |
| `--space-8` | 32px | Page-level margins |

**Radius** — a deliberate, small departure from Swiss style's literal `0px`: fully square corners read harsh across dozens of stat/column cards. Kept small and constant instead:

| Token | Value | Usage |
|-------|-------|-------|
| `--radius-sm` | 4px | Inputs, badges, buttons |
| `--radius-md` | 8px | Cards, modals |
| `--radius-lg` | 12px | Modal containers only |

**Shadow** — subtle only, no dramatic elevation:

| Token | Value | Usage |
|-------|-------|-------|
| `--shadow-sm` | `0 1px 2px rgba(15,23,42,0.06)` | Cards at rest |
| `--shadow-md` | `0 4px 8px rgba(15,23,42,0.08)` | Dropdowns, popovers |
| `--shadow-lg` | `0 12px 24px rgba(15,23,42,0.12)` | Modals only |

---

## 5. Component Specs

### Buttons
- **Primary (accent):** `bg-accent text-accent-foreground`, `radius-sm`, `px-4 py-2.5`, weight 600, `transition-colors duration-150`. Hover: darken 8% (no lift/scale). Disabled: 40% opacity, no pointer.
- **Secondary:** `border border-border text-foreground bg-surface`, same sizing. Hover: `border-primary` + `bg-muted`.
- **Destructive** (Reject): same shape, `text-destructive border-destructive`, filled only inside confirmation contexts.
- One primary (accent) CTA per view — matches the existing product's pattern (Search on Query page, Request Access after results, Approve in the review modal).

### Cards (StatCard, ColumnCard, request cards)
- `bg-surface border border-border radius-md p-3 (12px)`, `shadow-sm`.
- Hover (only where the card is clickable, e.g. request-history cards): `border-color` shifts to `--color-primary` + `shadow-md`. No transform.
- StatCard: icon (20px, `--color-muted-foreground` or semantic color) + label (`text-xs`, muted) + value (`text-2xl`, weight 800, `--color-foreground`).
- ColumnCard: header row (type icon + column name, `text-lg` weight 600) + stat rows (`text-sm`) + optional inline chart. Consistent card shape regardless of numeric/categorical/datetime type — only the body content changes.

### DataTable (reusable — Sample Data now, full filter/sort/paginate later)
- Design it now with the seams for filters/sort/pagination even though only the plain preview table ships first:
  - Header cells: fixed `--space-3` padding, `text-xs uppercase tracking-wide text-muted-foreground`, `border-b border-border`. Reserve a trailing icon slot per header cell for a future sort caret.
  - Body rows: `--table-row-height: 36px`, alternating row background optional (`--color-muted` at 40% on even rows) for scanability at high density.
  - Row hover: `bg-muted` (no border/shadow change).
  - Footer slot reserved (empty for now) for a future pagination control.
  - Empty state: centered muted text, no illustration.

### Inputs (search bar, form fields)
- `border border-border radius-sm px-3 py-2.5 text-sm bg-surface`.
- Focus: `border-primary` + `ring-2 ring-primary/20` (visible focus ring — never remove).
- Search bar specifically: full-width, leading search icon, trailing primary button attached (matches existing product).

### Modals (Request Access, Approve/Reject confirm)
- `bg-surface radius-lg shadow-lg`, overlay `rgba(15,23,42,0.4)` — no blur (blur is reserved for dismissal cues per the skill's own guidance, and we're avoiding glassmorphism entirely, so keep it a flat scrim).
- Header + body + footer action row (secondary action left/ghost, primary action right).

### Sidebar
- Fixed width `--sidebar-width: 240px`, `bg-surface`, right border `--color-border`.
- Nav item: icon (20px) + label, `radius-sm`, `px-3 py-2.5`. Active state: `bg-muted text-primary` + left accent bar (2px, `--color-primary`) — not a filled pill (stays Swiss/flat).
- Sign Out pinned to bottom, visually separated by a divider — never mixed into the main nav list (matches current product's `sidebar-footer` pattern and general destructive/exit-action separation best practice).

---

## 6. Motion

Functional only — every transition should explain a state change, never decorate.

| Interaction | Duration | Easing | Notes |
|---|---|---|---|
| Hover (color/border) | 150ms | ease-out | Buttons, cards, nav items |
| Focus ring appear | 100ms | ease-out | Inputs, buttons |
| Modal open/close | 200ms | ease-out (in) / ease-in (out) | Fade + slight scale (0.98→1), from trigger origin |
| Panel/section expand (e.g. preview loading → content) | 200ms | ease-out | Fade only, no slide |
| Loading state | n/a | — | Skeleton placeholders for anything >300ms, not spinners-only |

No scroll-triggered reveals, no staggered list entrances, no parallax — those are landing-page techniques and were explicitly rejected by the brief's "no loud animation" constraint. Respect `prefers-reduced-motion` (disable all of the above when set).

---

## 7. Information Architecture (reference — functionality only, not visual)

Carried over from the current `ui/static/*.html` for React reimplementation, per the brief: same functionality and hierarchy, entirely new visual layer.

- **Sidebar nav:** Query Data · My Data Requests · Model Workspace (nav entry exists today, no page behind it yet — build as a placeholder route) · Data Access Requests (conditional — only rendered for `role: data-manager`, decoded from the JWT) · Sign Out (bottom, separated)
- **Query Data** (`/`): NL search bar + Search → results section:
  - Preview-only info banner + Request Access button (shown once a query returns)
  - Dataset Summary: Row Count / Column Count stat cards
  - Patient Coverage (conditional, domain-specific: unique/returning patients, return-rate, visits-per-patient chart) — keep conditional, don't force it into the generic layout
  - Column Information: one ColumnCard per column (type badge, unique count, missing %, numeric mean/min/max/std + histogram, categorical top-values + chart, datetime range)
  - Sample Data table (first 5 rows) — build on the reusable DataTable
  - Request Access modal: query/dataset summary readout, project name (2-255 chars), optional PDF upload (≤10MB), reason (10-500 chars), char counters
- **My Data Requests** (`/requests`): filter tabs (All/Pending/Approved/Rejected) with counts, request cards → detail modal (metadata, NL+SPARQL query, data preview, full results + CSV/JSON export once approved)
- **Data Access Requests** (`/admin/requests`, data-manager only): same filter-tab pattern, request cards → detail modal with Approve / Reject actions (reject requires optional reason text)
- **Model Workspace**: nav entry only today — scaffold an empty/placeholder page, don't invent functionality for it
- **Auth:** Google OAuth redirect flow; JWT in `localStorage`; role read by decoding the JWT client-side (`role` claim) — same mechanism, just move it into a hook (`useAuth`) instead of inline script

---

## 8. Pre-Delivery Checklist

- [ ] No emojis as icons — one SVG set only (Heroicons or Lucide)
- [ ] `cursor-pointer` on all clickable elements
- [ ] Hover/focus states use color/border transitions only (150–300ms) — no lift/scale gimmicks
- [ ] Text contrast ≥4.5:1 (body), ≥3:1 (large/label text) — verify against `--color-background` and `--color-surface` both
- [ ] Visible focus ring on every interactive element, keyboard-navigable
- [ ] `prefers-reduced-motion` respected
- [ ] Responsive at 375 / 768 / 1024 / 1440px (sidebar collapses below 1024px)
- [ ] No gradients beyond a single subtle 2-stop tint; no neon; no blur-for-decoration
- [ ] DataTable, StatCard, ColumnCard, Sidebar built as standalone reusable components (not inlined per-page) — required for the filters/sort/pagination work coming next
