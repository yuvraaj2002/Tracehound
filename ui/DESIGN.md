# Tracehound visual system

Status: finalized design direction, 21 October 2026.

This document is the reference for future UI changes. Preserve these decisions
unless the product owner explicitly revises them.

## Backgrounds and palette

White (#FFFFFF) is the permanent page and section background, including hero,
agent portraits, sticky navigation and approach section. Colored fills are
reserved for controls and the brand mark, never large sections.

| Role | Color | Use |
| --- | --- | --- |
| Primary | #284B63 | Triage ink blue: main actions, links, identity |
| Secondary | #70566F | Hypothesis plum: supporting accents |
| Tertiary | #8A6534 | Deploy bronze: small numbered details |
| Ink | #25272C | Main text |
| Muted | #62656C | Supporting text |
| Line | #E2E3E6 | Quiet separators |
| Soft | #EDF0F3 | Decorative lettering and text selection, never section fills |
| White | #FFFFFF | All page and section backgrounds |

Use white and neutral text for most of the interface. Do not give the three
brand colors equal visual weight. Keep the six character colors scoped to their
own headings, navigation indicators and captions. Logs uses #AA4937, Metrics
#47734E and Dependency #286F69; the other three reuse the brand tokens.
Tokens live in src/index.css; never duplicate them in components.

Primary, secondary and tertiary text have contrast ratios of 9.22:1, 6.46:1
and 5.26:1 against white respectively. All six agent text colors meet 4.5:1
against white. Pale watermarks and dividers are decorative, not readable text.
Do not introduce colored section backgrounds, neon accents, or large gradients.

## Layout and navigation

The agents are the dominant visual element. Keep the product introduction
compact and let the sharp group illustration lead the hero.

- Header: Tracehound home link, **Agents** (#agents), **How it works** (#how).
- Keep both navigation links visible on mobile.
- Do not reintroduce duplicate “Meet your team” or “Get to know the team” CTAs.
- Keep one scroll invitation beneath the hero illustration.
- Introduce agents individually while scrolling, in this fixed order:
  **Triage → Logs → Metrics → Dependency → Deploy → Hypothesis**.
- Keep the sticky agent index, active indicator, and next-agent links.
- Each agent has a large portrait, matching heading color, neutral body copy,
  and concise evidence/input and output descriptions.
- Stack portrait and copy on mobile; retain white surfaces at every breakpoint.
- Respect reduced-motion preferences and maintain visible keyboard focus.

| Agent | Text/accent color | Asset in public/agents/ |
| --- | --- | --- |
| Triage | #284B63 | triage.png |
| Logs | #AA4937 | logs.png |
| Metrics | #47734E | metrics.png |
| Dependency | #286F69 | dependency.jpg |
| Deploy | #8A6534 | deploy.png |
| Hypothesis | #70566F | hypothesis.jpg |

## Typography

Switzer is the single display and interface family. Use 500 for headings,
400 for body, and 600–750 sparingly for emphasis and identity. Compact heading
tracking, comfortable body line height, and tabular numerals provide hierarchy
without decorative monospace or a second display face. Body copy is 14–16px.

Selection is an aesthetic judgment, not an objective best-font claim. Switzer
was selected for a restrained sans-serif presentation that leaves personality
to the agents. IBM Plex Sans was also considered, but its stronger engineering
identity would push this page toward a more utilitarian tone.

Official references:

- https://www.fontshare.com/fonts/switzer
- https://www.fontshare.com/licenses
- https://www.ibm.com/design/language/typography/typeface/

Switzer loads through Fontshare's official CSS endpoint with font-display: swap.
It requires network access; Helvetica Neue/Helvetica/Arial provide fallbacks.
No font binaries are redistributed in this repository.

## Assets

Keep agents-hero-hd.png, the six role-named portraits, and the custom favicon.
Removed the unused low-resolution agents-hero.png and starter icons.svg sprite.
Portraits retain their source pixels; CSS applies the shared saturation grade.
Their baked studio shadows are part of the artwork, not section backgrounds.

Use the high-resolution group image at its natural aspect ratio. Do not use
blur effects on the artwork or restore the deleted low-resolution duplicate.
The shared CSS grading is saturation 0.65 / contrast 0.96 for the hero and
saturation 0.78 / brightness 1.04 for portraits. Keep grading centralized.

## Implementation reference

- src/index.css: color tokens, font stack, focus and reduced-motion defaults.
- src/App.css: layout, typography hierarchy, image grading and responsive rules.
- src/App.tsx: agent content, sequence and navigation destinations.
- index.html: official Switzer stylesheet connection.

Build and lint passed after the palette update. Contrast was checked numerically;
rendered browser visual verification remains outstanding.
