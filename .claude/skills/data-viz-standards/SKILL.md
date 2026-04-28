---
name: data-viz-standards
description: |
  Lumen's canonical data visualization decision rules. INVOKE THIS SKILL whenever you
  are about to (a) pick a chart type for query results, (b) design or critique a
  dashboard tile, (c) write a chart_spec inside a Cube query response, or (d) answer
  any "what chart should I use" question. The rules here are how the visualizer
  subagent picks charts deterministically — keeping your output aligned with this
  skill ensures your chart choices are consistent with what the platform actually
  renders.
---

# Lumen Data Visualization Standards

> Distilled from Cleveland & McGill (1984), Stephen Few, Edward Tufte, Mackinlay's APT, the Tableau "Show Me" rules, the Datawrapper chart guide, and the Vega-Lite grammar. Operationalized for an AI-driven BI platform that auto-picks visualizations.

This document is **prescriptive**: it tells the platform exactly what to render for any given data shape. Departure from these rules requires a documented reason in `meta.viz_override` on the Cube measure or a user-issued explicit chart selection.

---

## 1. The compass question

Before choosing a chart, identify the **statement** the chart must make. Datawrapper calls this the compass; we call it the **intent**. There are exactly six intents we recognize:

| Intent code | Question the chart answers | Default chart family |
|---|---|---|
| `magnitude` | "How big is this number?" | big-number |
| `change` | "How is this changing over time?" | line / area / sparkline |
| `comparison` | "Which is bigger, A or B?" | bar / grouped bar / dot plot |
| `composition` | "How does this whole break down?" | stacked bar / donut / treemap |
| `relationship` | "Are A and B correlated?" | scatter / bubble / heatmap |
| `distribution` | "How is X spread across values?" | histogram / box / violin |

**Most queries are `comparison` or `change`.** When in doubt, default to those families.

A query can carry intent in three ways (priority high → low):
1. **Explicit user request** ("show as a pie", "trend over time") — always wins
2. **Schema annotation** — `meta.default_intent: change` on the measure
3. **Inference** — from data shape (see §3 algorithm)

---

## 2. The perceptual hierarchy (the why)

Cleveland & McGill (1984) ran experiments measuring how accurately humans decode quantitative values from each visual channel. Mackinlay extended this to APT (1986). The combined ranking, from **most accurate** to **least accurate**:

### Quantitative data

1. **Position along a common scale** (e.g. dot plot, bar chart) — most accurate
2. **Position along non-aligned scales** (e.g. small multiples)
3. **Length** (bar height/width)
4. **Angle / slope** (e.g. line direction)
5. **Area** (e.g. bubble size, treemap rectangle)
6. **Volume / curvature** (e.g. 3D bar — never use)
7. **Color saturation / lightness** (e.g. heatmap intensity)
8. **Color hue** (e.g. categorical color) — least accurate for quantitative

### Categorical data

1. **Position** (proximity / clustering)
2. **Color hue** (most accurate channel for categories — opposite of quantitative)
3. **Shape** (when ≤ 4 categories)
4. **Texture / pattern**

### The rule that follows

> **Map the most important variable to the most accurate channel available.**

Practically:
- Encode your primary measure on **position** (Y axis on a bar/line chart, X axis on a horizontal bar)
- Encode your primary categorical breakdown on **color hue**
- Use **size** (area) only when both X and Y are already taken
- Use **color saturation** only for sequential/diverging quantitative data, never categorical

---

## 3. The chart-type decision tree

This is the algorithm the visualizer subagent runs. Inputs are derived from the Cube query result + schema metadata. Outputs are a `ChartSpec`.

### Inputs

```
n_measures           = len(query.measures)
n_dimensions         = len(query.dimensions)
has_time             = bool(query.timeDimensions)
time_granularity     = query.timeDimensions[0].granularity  # "day"|"week"|"month"|...
n_rows               = len(result.data)
dim_cardinalities    = { dim: distinct count in result }
measure_formats      = { measure: "currency"|"percent"|"number" }
intent_hint          = from user_request | schema annotation | None
```

### Algorithm

```
def select_chart(n_measures, n_dimensions, has_time, n_rows, dim_cardinalities, intent_hint):

    # ── Single value ────────────────────────────────────────────────────
    if n_measures == 1 and n_dimensions == 0 and not has_time and n_rows == 1:
        return BIG_NUMBER

    # ── Time series ─────────────────────────────────────────────────────
    if has_time:
        n_periods = distinct_count(time_buckets)   # months/quarters/years actually present
        if n_measures == 1 and n_dimensions == 0:
            return LINE if n_rows >= 5 else BAR(time_as_ordinal)
        if n_measures == 1 and n_dimensions == 1:
            cardinality = dim_cardinalities[dim_0]
            # NEW (R11 in §13a): low-N time × low-N category → grouped bar.
            # Position-on-common-scale beats color-distinction-of-series when
            # both axes are short. See §4.6.1 for the named case.
            if n_periods <= 4 and cardinality <= 5:
                return GROUPED_BAR(x=time, group=dim_0)
            if cardinality <= 5:
                return MULTI_LINE
            elif cardinality <= 12:
                return SMALL_MULTIPLES_LINE
            else:
                return TOP_N_LINE(n=10)  # plus an "Other" rollup
        if n_measures >= 2 and n_dimensions == 0:
            if same_unit(measures): return MULTI_LINE
            else: return SMALL_MULTIPLES_LINE  # never dual-axis, see §9

    # ── Comparison (no time) ────────────────────────────────────────────
    if n_measures == 1 and n_dimensions == 1 and not has_time:
        cardinality = dim_cardinalities[dim_0]
        if intent_hint == "composition":
            if cardinality <= 6: return DONUT
            elif cardinality <= 20: return STACKED_BAR(single)
            else: return TREEMAP
        # default: comparison
        if cardinality <= 30: return BAR(sorted_desc)
        else: return TOP_N_BAR(n=20, with_other=True)

    if n_measures == 1 and n_dimensions == 2 and not has_time:
        c1, c2 = dim_cardinalities[dim_0], dim_cardinalities[dim_1]
        if c1 <= 12 and c2 <= 12: return HEATMAP
        if c1 <= 6: return GROUPED_BAR(facet=dim_1)  # facet by larger
        return TABLE

    # ── Composition ─────────────────────────────────────────────────────
    if n_measures >= 2 and n_dimensions == 1 and intent_hint == "composition":
        return STACKED_BAR(measures)

    # ── Relationship ────────────────────────────────────────────────────
    if n_measures == 2 and n_dimensions == 0:
        return SCATTER
    if n_measures == 2 and n_dimensions == 1:
        return SCATTER(color=dim_0)
    if n_measures == 3 and n_dimensions <= 1:
        return BUBBLE  # x, y, size

    # ── Fallback ────────────────────────────────────────────────────────
    return TABLE
```

### Edge-case overrides

- If `n_rows == 0`: `EMPTY_STATE` — never render an empty axis.
- If `n_rows == 1` but result still has dimensions: `BIG_NUMBER` per measure, side by side (KPI strip).
- If requested width < 300px: prefer `SPARKLINE` over `LINE`, `BULLET` over `BAR`.
- If a measure is `format=currency` and `n_rows == 1` and intent is `magnitude`: `BIG_NUMBER` with delta indicator (period-over-period if available).

---

## 4. Chart-by-chart guide

For every chart type the platform supports, the rules below are authoritative.

### 4.1 Big number

**Use when**: a single measure value is the answer; intent = `magnitude`.

**Required**: value, label, format. **Add when available**: comparison delta (vs prior period), sparkline trail, target/threshold marker.

**Anti-patterns**:
- Multiple unrelated measures on one big-number tile (split into a KPI strip instead)
- Big-number for a measure with > 1 row (you're hiding the breakdown)

### 4.2 Bar chart

**Use when**: comparing one measure across a small/medium number of categories. Intent = `comparison`.

**Rules**:
- Sort descending by measure value (unless dimension has natural order — months, ordinal grades)
- Y-axis MUST start at zero (length encodes magnitude)
- Horizontal bars when category labels are long (> 12 chars) or there are > 8 categories
- Cap at 30 bars; beyond that, show top-N + "Other" rollup
- Use a single hue across all bars (color carries no info here); reserve color for highlighting one bar

**Anti-patterns**:
- Truncating Y-axis (deceptive — implies false magnitude differences). When values are tightly clustered making the bar useless, switch chart type per §4.2.1, don't truncate the bar's y-axis.
- 3D bars (volume encoding is least accurate; never)
- Rainbow colors per bar WHEN cardinality > 10 (colors recycle and imply false grouping)

### 4.2.1 The clustered-values rule (mandatory)

When `(max - min) / max < 15%` AND `n_rows >= 3` for a bar chart, the visualizer
**MUST switch from `bar` to `dot-plot`**. Reasoning:

- Bar chart's value channel is *length*. When values cluster within 15% of each
  other, the bar lengths look identical at chart scale — the encoding fails.
- A common (but bad) workaround is truncating the y-axis. This breaks the
  length-magnitude proportionality and is the canonical "lie factor" anti-pattern.
- The correct fix is **dot-plot**: encode value via *position* (Cleveland-McGill
  channel #1) instead of length. Position-along-axis with a non-zero baseline is
  NOT deceptive — it's the canonical way to show small differences accurately.

This auto-switch is in `backend/services/ai_service/visualizer.py` and is verified
in the eval harness.

### 4.2.2 The categorical-color allowance

Skill §4.2 above says "single hue across all bars". This is the strict
Tufte/Few view. We relax it for one specific case:

- When `n_dimensions == 1` AND `dim.distinct_count <= 10` AND chart is bar /
  horizontal-bar / dot-plot, we **DO** color by the categorical dimension
  (using the categorical palette).
- Reasoning: color hue is the *most accurate* channel for categorical data
  (per Cleveland-McGill ranking). It carries real encoding (the category) and
  helps with cross-filter UX (later, hover/filter highlighting works visually).
- This is what Tableau and Looker do by default. We follow industry practice
  here over Few's stricter view because the encoding adds information rather
  than redundancy when paired with future cross-filter / drill-down interaction.

Beyond 10 categories, colors recycle and the encoding becomes ambiguous —
that's when single-hue + sorted bar is correct again.

### 4.3 Grouped (clustered) bar chart

**Use when**: comparing one measure across two categorical dimensions, both with low cardinality (≤ 5 outer × ≤ 4 inner).
**Also use when**: time × category data with **N_periods ≤ 4 AND N_categories ≤ 5** (see §4.6.1 for the full rationale).

**Rules**:
- Outer dimension (or time, if it's the short axis) on X axis
- Inner dimension as color hue
- Sort outer dimension by total of inner values (or by named order — for time, chronological)
- Always include a legend for the color encoding
- Bars in a group are touching; gap between groups = ~50% of bar width

**Anti-patterns**:
- Grouped bars when inner cardinality > 5 (user can't read the cluster)
- Using grouped when totals matter — use stacked instead

### 4.3.1 The 3-period × 5-category case (worked example)

User asks: "number of orders by region over last 3 months over time."

Result shape: `n_measures=1` (count), `n_dimensions=1` (region, 5 values), `has_time=true`, `n_periods=3` (months).

**Wrong choice**: 5-line trend chart with color = region. The reader has to compare slopes across 5 lines that nearly overlap, with only 2 segments per line. Slope encoding wastes the channel when there's no continuous trend to perceive.

**Right choice**: grouped bar.
- X axis = month (3 buckets, chronological)
- Within each month, 5 bars side by side (one per region)
- Color hue encodes region (categorical palette)
- Sort regions consistently across all groups (alphabetic OR by total descending — pick one and lock it)
- Y axis = count, zero baseline (Rule R3)

**Why**: with only 3 periods and 5 categories, the user's question is "*compare regions within each period*" — exact comparison via length on a common baseline is Cleveland-McGill's most-accurate channel. Multi-line wins only when N_periods grows large enough that trend shape becomes the story.

### 4.4 Stacked bar chart

**Use when**: showing composition of a whole over a categorical axis. Intent = `composition`.

**Variants**:
- **Absolute stacked**: total height varies — shows both total and parts
- **Percent stacked (100% stacked)**: total height fixed — shows only proportions

**Rules**:
- Order stack segments consistently (largest on bottom OR by named order)
- Limit to ≤ 7 stack segments; group the rest into "Other"
- Use sequential or categorical palette depending on whether segments have order

**Anti-patterns**:
- Reading inner segment values is hard — provide tooltips with values
- Don't use for time series (use stacked area instead, but watch out for §4.7)

### 4.5 Line chart

**Use when**: showing change over time. Intent = `change`.

**Rules**:
- Time on X axis, value on Y axis
- Y-axis MAY start non-zero when emphasizing change (line slope encodes change, not magnitude)
- Use solid lines for actuals, dashed for forecasts/projections
- Maximum 5 lines on a single chart; beyond that → small multiples
- Always include a markers (dots) at data points if ≤ 30 data points
- Include axis grid lines (light gray) for readability

**Anti-patterns**:
- "Spaghetti chart": > 5 overlapping lines — switch to small multiples
- Connecting unordered categorical data with lines (suggests false continuity)
- Dual Y-axis (almost always misleading; use small multiples or normalize to %)

### 4.6 Multi-line / small multiples

**Multi-line**: ≤ 5 series, all on one chart, distinguished by color.

**Small multiples**: > 5 series, each gets its own mini-chart in a grid. Each subplot uses the same X and Y scale.

**Rules**:
- Small multiples MUST share scales (otherwise comparison fails)
- Sort small multiples by some meaningful order (alphabetical, total, recent change)
- 3-4 columns max

### 4.7 Area chart / Stacked area

**Use when**: showing change over time AND composition. Intent = `change` + `composition`.

**Rules**:
- ≤ 5 stack layers (areas overlap and obscure beyond that)
- Use percent-stacked when interest is in proportion changes; absolute-stacked when total matters
- Ordering matters: place the most important / largest series at the bottom (it has a flat baseline; others stack on top of noise)

**Anti-patterns**:
- Standard (non-stacked) overlapping areas with transparency — unreadable; use line chart instead
- Stacked area with negative values (geometrically broken)

### 4.8 Sparkline

**Use when**: trend over time IN-LINE with other content (KPI tile delta, table cell). Intent = `change`, but compactness is the constraint.

**Rules**:
- No axes, no gridlines, no data labels
- Maximum 100px wide, 30px tall
- Color: muted (single hue)
- Always render in a context where the axis units are known from surrounding label

### 4.9 Bullet chart

**Use when**: showing actual vs target with qualitative bands. Intent = `magnitude` + comparison to target.

**Rules**:
- Horizontal layout, narrow (~30px tall)
- One filled bar = actual; one tick mark = target; background bands = qualitative ranges (poor / OK / good)
- Replaces gauges and dashboard "speedometers" — never use those

### 4.10 Dot plot

**Use when** (in priority order):
1. **Tightly-clustered values** where bar's length encoding would fail (per §4.2.1)
2. Comparing a measure across many categories where bars would be too dense
3. Showing exact rank order without the visual weight of full bars

**Rules**:
- Horizontal arrangement (categories on Y, value on X) preferred — easier to read long category labels
- **Y-axis is NOT zero-based** — that's the whole point. Position-along-axis encodes value; non-zero baseline is canonically OK for position.
- X-axis (the value axis) shows the data range with ~5–10% padding on each end.
- Sort by value (descending)
- Render as **lollipop**: thin connecting line from baseline (or category axis) to dot, with dot diameter ~12–14px and a 2px white stroke ring for separation
- Categorical color from the standard palette when ≤ 10 categories (per §4.2.2)
- Hover: tooltip shows category + formatted value; non-hovered dots dim to ~35% opacity

### 4.11 Scatter plot

**Use when**: showing relationship between two measures. Intent = `relationship`.

**Rules**:
- X = independent variable; Y = dependent
- Add a regression line ONLY if there's a real relationship (don't fit noise)
- Use point opacity to handle overplotting (alpha = 0.3 when n_rows > 500)
- For heavy overplotting (n_rows > 5000): switch to **2D histogram / hexbin** automatically
- Encode a third measure as **size** (bubble); keep size variation modest (max:min radius ≤ 4:1)
- Encode a categorical breakdown as **color**

### 4.12 Heatmap

**Use when**: one measure across two categorical dimensions where both have moderate cardinality. Intent = `relationship` or `comparison`.

**Rules**:
- Sequential color scale (single hue gradient, e.g. blues) for ordinal magnitudes
- Diverging color scale (e.g. red-white-blue) when 0 is meaningful midpoint
- Cell labels with the value when grid is small enough to read (< 200 cells)
- Dimensions sortable: by value, by name, or by cluster (latter requires a hierarchical clustering pass — defer)
- Grid lines off; cells touch

**Anti-patterns**:
- Using rainbow color scale (perceptually non-uniform; misleading)
- Heatmap with > 1000 cells without aggregation

### 4.13 Donut / Pie

**Use when**: showing part-to-whole composition with ≤ 6 slices. Intent = `composition`.

**Strict rules**:
- ≤ 6 slices, period. With more, switch to bar chart or treemap.
- Total of slice values must be 100% (or near it). Don't pie a non-additive measure.
- Donut > pie (the hole shows the total in the center, freeing the angles to encode parts)
- Always include data labels with both percentage AND absolute value
- Order slices by size (descending), with "Other" last

**Anti-patterns**:
- Pies for trend ("pies don't tell stories — they tell snapshots")
- 3D pies (forbidden)
- Comparing two pies side-by-side — use a stacked bar instead, much more accurate

### 4.14 Treemap

**Use when**: composition with > 7 categories where a bar chart would be too wide. Intent = `composition` with hierarchy bonus.

**Rules**:
- Largest rectangle in top-left corner (squarified treemap layout)
- Color encodes either category (hue) or a secondary measure (sequential)
- Cell label inside rectangle when it fits; tooltip otherwise
- Hierarchical drilldown: click a parent to zoom in

**Anti-patterns**:
- Comparing rectangle areas precisely — area is bad for that. Tell the story with rank order, not exact ratios.

### 4.15 Table

**Use when**: detail matters; user needs exact values; multiple measures + dimensions don't summarize cleanly.

**Rules**:
- Right-align numbers; left-align text
- Tabular numerals (font feature `tnum`)
- Format numbers with K/M/B suffixes for human reading; show full precision on hover
- Sortable column headers
- Sticky header on long tables
- Zebra striping OFF by default (Few: it's noise); turn on only if rows have many columns

### 4.16 Map (choropleth / point map)

**Defer to v2** — needs geographic data + map projection lib. Until then, render geo data as a sorted bar chart by geography name.

---

## 5. Color rules

### 5.1 Three palette families

```
categorical:  for distinct, unordered groups (≤ 10 colors before reuse)
sequential:   for ordered numeric data (light → dark, single hue)
diverging:    for data with a meaningful midpoint (red ← white → blue)
```

### 5.2 Lumen palettes

Defined in `frontend/tailwind.config.js` and `config/settings.yaml`:

```
categorical: ['#5B8FF9','#5AD8A6','#5D7092','#F6BD16','#E8684A','#6DC8EC','#9270CA','#FF9D4D','#269A99','#FF99C3']
sequential:  ['#EAF1FF','#C5D9FF','#8BB1FF','#5B8FF9','#2E5CD8','#1A3A9C']
diverging:   ['#D63E3E','#F09494','#F2F2F2','#9DBFE3','#1F5BB5']
```

Both are color-blind safe (tested against deuteranopia/protanopia simulators).

### 5.3 Rules

- **Never** use red/green only — color-blind users can't distinguish
- **Never** use color hue to encode a quantitative variable (use saturation/lightness instead)
- Use color sparingly: a chart with 10 different colors loses meaning. Reserve color for the variable that needs distinguishing.
- Highlight the data point being discussed: gray out the rest, color the focus.

### 5.4 Semantic colors

```
success: #3DD68C   (good change, target met)
warning: #F0A04B   (degrading, attention needed)
danger:  #FF5C5C   (regression, target missed)
neutral: muted gray
```

Use semantic colors **only** for performance indicators (delta arrows, threshold violations). Don't overload them in regular charts.

---

## 6. Number formatting

### 6.1 Suffixes

```
< 1,000             1, 12, 999
1,000 → 999,999     1.2K, 12K, 999K
1M → 999M           1.2M, 12M, 999M
1B → 999B           1.2B, 12B
1T+                 1.2T
```

Use 3 significant digits by default (1.23M, 12.3M, 123M).

### 6.2 Currency

Symbol prefix + suffix abbreviation: `$1.2M`, `€450K`, `¥12.3B`.
For small currency values: `$12.34` (full cents).

### 6.3 Percent

```
≥ 10%       integer  (12%, 87%)
1% – 10%    1 decimal  (3.4%, 9.8%)
< 1%        2 decimals  (0.34%, 0.05%)
```

### 6.4 Time/duration

Use natural units: `2h 14m`, `1.4 days`, `34s`. Don't show "8160 minutes" when "5.7 days" reads.

### 6.5 Tabular numerals

Always render numbers with `font-feature-settings: "tnum"`. Frontend already has this on `.num` and table cells; verify any new component opts in.

---

## 7. Axis rules

### 7.1 Y-axis baseline

| Chart type | Y-axis must start at zero? |
|---|---|
| Bar | **Yes, always** (length = magnitude) |
| Stacked bar | Yes |
| Area | Yes (area = magnitude) |
| Line | No — start near data range to show change clearly |
| Scatter | No |
| Sparkline | No |

### 7.2 X-axis ordering (mandatory)

The platform applies these rules in this priority order:

1. **User-explicit `order` clause** — always wins.
2. **Time axis** → chronological ASC (Jan → Dec, 1992 → 1998). Never reversed by default.
3. **Detected ordinal pattern** — overrides server default. Patterns we auto-detect:
   - Numeric prefix: `1-URGENT`, `2-HIGH`, `3-MEDIUM` → sorted by leading number
   - Month names: `Jan`, `Feb`, `Mar` (or full names) → Jan-Dec order
   - Day-of-week: `Mon`, `Tue` → Mon-Sun
   - Quarters: `Q1`, `Q2`, `Q3`, `Q4` (with optional year suffix) → Q1→Q4 chronological
   - Loyalty / size tiers: `Free / Starter / Growth / Enterprise`, `S / M / L / XL`, `Bronze / Silver / Gold / Platinum`, `Low / Medium / High / Critical` — sorted lower → higher
   - TPC-H order status: `F` (finished) → `O` (open) → `P` (partial)
4. **Nominal categorical (no detected order)** → DESC by first measure (Cleveland-McGill: ranking is information).
5. **Continuous** → numeric ASC.

The detection in #3 happens **client-side** in `PlotChart.tsx::detectOrdinalSort`. Adding a new pattern there formalizes it across all chart types.

The default in #4 is enforced **server-side** in the DuckDB runners (and will be ported to the real Cube query layer in Phase 1) — this guarantees rows arrive in stable, meaningful order even if the chart layer never sorts.

**Together these mean**: row order is always meaningful, never random. A user who runs the same query twice sees the same chart layout.

### 7.3 Labels

- Always label axes UNLESS the field name is in the chart title or sparkline context
- Never label every tick if labels collide — sample to fit
- Date axis: format `MMM YYYY` for monthly, `YYYY` for yearly, `MMM DD` for daily

### 7.4 Grid lines

- Y-axis grid lines: light gray (`#272B33` in dark mode, `#E5E7EB` in light), every major tick
- X-axis grid lines: usually OFF (clutter); ON for time series

---

## 8. Title, subtitle, annotations

Every published chart should have:

1. **Title**: declarative sentence (not just field names). "Revenue by region, 2023" — not "Sum(revenue) × region".
   - Auto-generated when AI emits final_answer:
     - `<measure_label> by <dimension_label>` for comparisons
     - `<measure_label> over time` for time series
     - `<measure_label>` for big number
2. **Subtitle**: time period or filter context. "Last 12 months. Excludes refunded orders."
3. **Annotations**: vertical lines for known events ("Product launch"), horizontal threshold lines ("Target: $1M"), text callouts on outliers.
4. **Source / footnote**: `Generated <timestamp> from <data_source>`. Visible on hover or export.

---

## 9. Anti-patterns (always reject)

The visualizer must reject these even if requested explicitly (or warn loudly):

| Anti-pattern | Why | Correct alternative |
|---|---|---|
| 3D charts of any kind | Volume is least accurate channel; perspective distorts | 2D equivalent |
| Pie chart with > 6 slices | Angles indistinguishable | Bar or treemap |
| Pie chart for non-part-to-whole | Implies wholeness that doesn't exist | Bar |
| Truncated Y-axis on bar chart | Deceives about magnitude | Start at zero |
| Dual Y-axis | Suggests correlation that may not exist; arbitrary scaling | Small multiples or normalize |
| Rainbow color for sequential data | Perceptually non-uniform | Single-hue gradient (sequential) |
| Stacked area with > 5 layers | Layers obscure each other | Small multiples |
| Radar / spider chart | Area encoding + non-aligned scales = double penalty | Parallel coordinates or table |
| Donut without center label | Loses the value of the donut format | Add center label or use bar |
| Word clouds | Position arbitrary, area encoding unreliable | Bar of word counts |
| Gauges / speedometers | Wasted space; angle hard to read | Bullet chart |

---

## 9.5 Interaction patterns

Visualizations are not posters — they're explorable. Every chart in the platform
implements the following interactions (PlotChart enforces this via Plot's
built-in marks + the `.plot-mark-hover` CSS layer):

### 9.5.1 Hover tooltip (mandatory)

Every chart with marks (bar, line, dot, scatter, heatmap, etc.) MUST show a
tooltip on hover containing at minimum:
- The categorical or temporal label (the X / row identifier)
- The measure label + formatted value (`$1.2M`, `24.6%`, `12,345`)
- Any additional encoded fields (color category, size value)

Implementation: Plot's `tip: true` or `Plot.tip(rows, Plot.pointer({...}))` mark.
Tooltip styling (dark theme, tabular numerals) is in `frontend/src/styles.css`.

### 9.5.2 Hover highlight (mandatory)

When the user hovers a mark:
- The hovered mark scales 1.04× and goes to 100% opacity
- Non-hovered marks fade to ~35% opacity (Tableau-style focus)
- Transition duration: 180ms ease

This makes ranking-by-value or visually scanning across categories easier.

Implementation: CSS `.plot-mark-hover` class added to each mark, with `:has(:hover)`
selectors driving the dim-others behavior.

### 9.5.3 Click → cross-filter (when in dashboard)

When a chart tile is on a dashboard:
- Clicking a categorical mark (bar / pie slice / dot) emits a filter on that
  dimension+value to all other tiles in the dashboard.
- Visual feedback: the clicked mark gets a "selected" state (saturation = 100%,
  others dim to 25%); other tiles show a "filtered by …" pill in their header.
- Filters are URL-encoded so the state is shareable.

### 9.5.4 Click → drill-down (in chat / workbook)

In AI-rendered chat charts and workbench previews:
- Clicking a mark opens a Workbook with the same query plus a filter on the
  clicked dim+value.
- This is the "drill-down" pattern — escape from a high-level chart into the
  underlying detail in one click.

### 9.5.5 Pointer-driven cross-hair (line/area only)

For time-series charts, hovering anywhere on the plot area shows:
- A vertical cross-hair line at the nearest x-tick
- The value of every series at that x-position
- Tooltip with all values + the date

Plot does this natively via `Plot.tip(rows, Plot.pointerX({...}))`.

---

## 10. Accessibility (a11y)

Every chart must:

- Render alt-text describing the data (auto-generated: "Bar chart showing revenue by region; APAC leads at $4.2M")
- Support keyboard navigation (tab through data points, arrow keys for next/prev)
- Have a "View as table" toggle (screen reader fallback)
- Use color-blind safe palettes (Lumen palettes already are)
- Avoid color as the SOLE channel for important distinctions — pair with shape, label, or position

---

## 11. The visualizer subagent contract

This skill is operationalized by `backend/services/ai_service/visualizer.py`:

```python
def select_visualization(
    cube_query: CubeQuery,
    data_summary: DataSummary,        # n_rows, dim_cardinalities, sample, ...
    schema_metadata: SchemaMetadata,  # measure formats, dimension types
    intent_hint: str | None = None,
) -> ChartSpec:
    """Apply the §3 algorithm. Return a fully-specified ChartSpec.
    For tied or ambiguous cases, call out to the weak-tier LLM with this skill
    embedded in the system prompt and ask for a tiebreak with rationale."""
```

Visualizer always returns a ChartSpec with:
- `type` (one of the chart families above)
- `x`, `y`, `color`, `size`, `facet` field references
- `format` per-axis
- `title`, `subtitle`
- `rationale` (why this chart was chosen — for AI transparency)

Downstream:
- The frontend `PlotChart.tsx` reads ChartSpec and renders deterministically
- The chat panel surfaces `rationale` in a "Why this chart?" tooltip

---

## 12. When to invoke this skill (you, the AI)

Invoke this skill (or follow its rules implicitly) when:

1. You're inside the visualizer subagent emitting a `select_visualization` tool result
2. You're inside the main AI loop emitting `final_answer.chart_spec` (DEFER to the visualizer if available; only emit when there's no visualizer in the loop)
3. The user asks "what chart should I use" or critiques a current chart
4. You're scaffolding a new dashboard tile or workbook example
5. You're authoring `meta.example_questions` or few-shot examples for a Cube measure — the example must include a chart_spec compliant with these rules

---

## 13. References

- Cleveland, W. S. & McGill, R. (1984). *Graphical Perception: Theory, Experimentation, and Application to the Development of Graphical Methods.* JASA 79(387): 531–554.
- Cleveland, W. S. (1985). *The Elements of Graphing Data.* Wadsworth.
- Mackinlay, J. (1986). *Automating the Design of Graphical Presentations of Relational Information.* ACM TOG 5(2): 110–141.
- Tufte, E. R. (1983). *The Visual Display of Quantitative Information.* Graphics Press.
- Tufte, E. R. (1990). *Envisioning Information.* Graphics Press.
- Tufte, E. R. (2006). *Beautiful Evidence.* Graphics Press.
- Few, S. (2006, 2013 2nd ed). *Information Dashboard Design.* O'Reilly / Analytics Press.
- Few, S. (2008). *Dual-Scaled Axes in Graphs — Are They Ever the Best Solution?* Perceptual Edge.
- Wilkinson, L. (2005). *The Grammar of Graphics.* Springer.
- Munzner, T. (2014). *Visualization Analysis and Design.* CRC Press.
- Datawrapper. (2023). *A friendly guide to choosing a chart type.* https://www.datawrapper.de/blog/chart-types-guide
- Datawrapper Academy. *How to combine line and bar charts.* https://academy.datawrapper.de/article/266
- Datawrapper Academy. *How to create a grouped bar chart.* https://academy.datawrapper.de/article/121
- Observable. *When to use bar or line charts for time series data.* https://observablehq.com/blog/bars-vs-lines-time-series-data
- Tableau. *Show Me — choose the right chart type for your data.* https://help.tableau.com/current/pro/desktop/en-us/what_chart_example.htm
- Vega-Lite. *Mark and channel reference.* https://vega.github.io/vega-lite/

---

## 13a. The Tufte canon — the 14 prescriptive rules

Source-grounded synthesis. Every rule has an "applies when" clause and a citation. These rules are normative: when the rest of the skill conflicts with one, the rule below wins (and the conflict is a bug in this skill — file it).

### R1 — Position is king
**Applies when**: encoding any quantitative variable on any chart.
**Rule**: place the *primary* measure on a position channel along a common scale (Y on a vertical bar/line, X on a horizontal bar). Reserve length, angle, area, and color for secondary roles.
**Source**: Cleveland & McGill (1984), perceptual ranking slot 1.

### R2 — Encode by data type, not by chart-genre default
**Applies when**: assigning a non-position variable to a channel.
**Rule**:
- Nominal → **color hue** (Mackinlay rank 2 for nominal).
- Ordinal → **color saturation / lightness** or position-on-non-aligned-scale (Mackinlay ranks 2–3 for ordinal). Not hue.
- Quantitative secondary → **length** (bar/dot), then **size/area** (bubble) only if X and Y are taken.
**Source**: Mackinlay (1986), three-by-data-type effectiveness rankings.

### R3 — Bars must have a zero baseline; lines need not
**Applies when**: drawing a bar/column chart vs. a line chart.
**Rule**: a bar's *length* encodes magnitude → truncating its baseline distorts the encoding. A line's *slope* encodes change → starting near the data range is fine and often clearer. **Bars: always zero. Lines: never required to start at zero.**
**Source**: Tufte (1983) p. 57; Datawrapper chart guide.

### R4 — The Lie Factor envelope
**Applies when**: reviewing or auto-generating any chart's axis configuration.
**Rule**: `Lie Factor = (visual effect) / (data effect)` must lie within `[0.95, 1.05]`. Reject any axis transform, 3D effect, or aspect-ratio choice that pushes outside this band.
**Source**: Tufte (1983) p. 57.

### R5 — Maximize data-ink, erase redundant ink
**Applies when**: every chart, every render.
**Rule**: every pixel that doesn't represent a datum or label is suspect. Specifically erase: chart borders, redundant tick marks, gridlines on bar charts, drop shadows, 3D bevels, gradient fills, and category-color legends when categories are already labeled inline.
**Source**: Tufte (1983) ch. 4 (the five data-ink principles).

### R6 — No chartjunk
**Applies when**: tempted to add a "decorative" element.
**Rule**: reject moiré vibrations, heavy decorative grids, "self-promoting" graphics (logos eating tile real estate), and ducks (charts dressed as pictures of their subject). 3D bars, 3D pies, and gauge skeuomorphism are chartjunk.
**Source**: Tufte (1983) ch. 5.

### R7 — Small multiples for any series count > 5
**Applies when**: time series with > 5 series, or comparison across > 5 categories of the same shape.
**Rule**: replace the multi-line "spaghetti" chart with small multiples — one panel per series, **shared X and Y scales**, sorted by a meaningful order (alphabetic, total, or recent change). Cap at 3–4 columns.
**Source**: Tufte (1983); Tufte, *Envisioning Information* (1990) ch. 4.

### R8 — Sparklines: data-words, no chrome
**Applies when**: putting a trend in-line with text, in a KPI tile, or in a table cell.
**Rule**: render with no axes, no gridlines, no labels, single muted hue. Width ≤ 100 px, height ≤ 30 px. The surrounding label or column header supplies the units.
**Source**: Tufte, *Beautiful Evidence* (2006) ch. 2.

### R9 — Few's two-goal dashboard rule
**Applies when**: laying out a dashboard.
**Rule**: (1) reduce non-data pixels — neutral palette, thin grid, no boxes-around-boxes. (2) Enhance data pixels — reserve hue and intensity for points the viewer must notice. Operationalized: 90% of dashboard ink is neutral gray; 10% is the accent color reserved for KPIs and threshold violations.
**Source**: Few (2006, 2013) *Information Dashboard Design*.

### R10 — Color for emphasis, not enumeration
**Applies when**: > ~10 categorical values would otherwise each get a hue.
**Rule**: beyond ~10 categories, hues recycle and stop encoding identity. Switch to a single hue + sorted positions, and reserve color for the one bar/line being highlighted.
**Source**: Few (2006) ch. 4; Cleveland & McGill (1984), hue is rank ~7 for quantitative decoding.

### R11 — Line vs. grouped-bar — the named decision
**Applies when**: time × category data; intent = comparison.
**Rule**:
- **N_periods ≤ 4 AND N_categories ≤ 5** → **grouped bar** (categories as color, time as X).
- **N_periods ≥ 5** OR time is densely / continuously sampled → **multi-line** (color = category, X = time).
- **N_categories > 5** with continuous time → **small multiples line**, one panel per category.
- If lines cross each other > ~3 times in the visible range → **small multiples**, regardless of N.

**Why**: bars encode magnitude via length and dominate when the reader needs *exact* comparisons across a small set of discrete time points. Lines encode trend via slope and dominate when the reader needs to see the shape of change over many points. **The 3-period × 5-region case is grouped bar.** See worked example in §4.3.1.

**Source**: Datawrapper chart guide (2023); Datawrapper Academy article 266 ("How to combine line and bar charts"); Observable, "When to use bar or line charts for time series data"; Cleveland & McGill (1984) — length encodes magnitude better than slope at low resolution.

### R12 — Pie/donut: ≤ 6 slices, true part-to-whole only
**Applies when**: tempted to use a pie/donut.
**Rule**: ≤ 6 slices; total must equal the whole; never use to compare two pies side by side (use a 100%-stacked bar instead). Donut > pie because the hole holds the total. Always label both percentage and absolute value.
**Source**: Cleveland & McGill (1984) (angle rank ~3, area rank ~4); Datawrapper chart guide ("a 3% difference between two categories can be easy to spot in a bar chart, but practically invisible in a pie or donut").

### R13 — No dual Y-axis
**Applies when**: tempted to overlay two measures on different scales on one chart.
**Rule**: reject. Dual axes invite spurious correlation reading because the relative slopes are arbitrary. Use small multiples (shared X, separate Y) or normalize both measures to % change vs. baseline.
**Source**: Few (2006) ch. 3; Few (2008), *Dual-Scaled Axes in Graphs*.

### R14 — Clustered-values switch
**Applies when**: bar chart where `(max - min) / max < 15%` AND `n_rows ≥ 3`.
**Rule**: switch from bar to **dot plot / lollipop**. Bar's length channel fails when values cluster within 15%; the bars look identical at chart scale. The truncated-axis "fix" violates R3. Dot plot encodes via *position* (rank 1) on a non-zero scale, which is canonically OK for position. This auto-switch is in `backend/services/ai_service/visualizer.py` and is verified in the eval harness.
**Source**: Cleveland & McGill (1984); Cleveland (1985) *The Elements of Graphing Data* ch. 3 (dot plot as bar substitute).

---

### How to use this canon

- The decision tree in §3 is the executable form. Each branch should be traceable to one or more rules above.
- The chart-by-chart guide in §4 is the per-type elaboration. When updating §4 rules, make sure no new rule contradicts §13a.
- When a new chart type is added (e.g., dumbbell, calendar heatmap, Markdown viz) it MUST cite which of R1–R14 it follows or knowingly relaxes (and why).
