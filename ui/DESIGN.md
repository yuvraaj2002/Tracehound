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

- Header: Tracehound home link, **Agents** (#agents), **How it works** (#how),
  and **Meet the developer** (LinkedIn, opens in a new tab).
- Keep all navigation links visible on mobile in a second row beneath the
  wordmark; no cramped single row or hidden developer link.
- Do not reintroduce duplicate “Meet your team” or “Get to know the team” CTAs.
- Keep one scroll invitation beneath the hero illustration.
- Introduce agents individually while scrolling, in this fixed order:
  **Triage → Logs → Metrics → Dependency → Deploy → Hypothesis**.
- Keep the sticky agent index, active indicator, and next-agent links.
- Alternate desktop portraits left/right through the sequence, starting left.
- A fine SVG thread follows the gutter between profiles. Scroll position fills
  the path and moves a softly glowing light tip. The light transitions through
  the six agent colors, matching each agent at the center of its section.
  Keep the glow localized; it must not overlap copy or intercept input.
  After Hypothesis, the thread curves into 120px of white space and dissolves
  into a few particles. It ends before How it works, rather than crossing copy.
- On mobile, use a narrow left gutter for the thread and stack every portrait
  above its copy. Reduced-motion mode shows a static thread without a light
  tip, glow or particles.
- Each agent has a large portrait, matching heading color, neutral body copy,
  and concise evidence/input and output descriptions.
- Stack portrait and copy on mobile; retain white surfaces at every breakpoint.
- Respect reduced-motion preferences and maintain visible keyboard focus.
- Footer includes “Meet the developer” linking to
  https://www.linkedin.com/in/yuvraaj-singh/ in a new tab, with an accessible
  new-tab notice and noopener/noreferrer.

| Agent | Text/accent color | Asset in public/agents/ |
| --- | --- | --- |
| Triage | #284B63 | triage.png |
| Logs | #AA4937 | logs.png |
| Metrics | #47734E | metrics.png |
| Dependency | #286F69 | dependency.jpg |
| Deploy | #8A6534 | deploy.png |
| Hypothesis | #70566F | hypothesis.jpg |

## Typography

Switzer is the display and interface family. Cabinet Grotesk 700 is reserved
for the Tracehound wordmark in the header and footer. Use 500 for headings,
400 for body, and 600–750 sparingly for emphasis and identity. Compact heading
tracking, comfortable body line height, and tabular numerals provide hierarchy
without decorative monospace or additional heading typefaces. Body copy is 14–16px.

Selection is an aesthetic judgment, not an objective best-font claim. Switzer
was selected for a restrained sans-serif presentation that leaves personality
to the agents. IBM Plex Sans was also considered, but its stronger engineering
identity would push this page toward a more utilitarian tone.

Official references:

- https://www.fontshare.com/fonts/cabinet-grotesk
- https://www.fontshare.com/fonts/switzer
- https://www.fontshare.com/licenses
- https://www.ibm.com/design/language/typography/typeface/

Both families load through Fontshare's official CSS endpoint with font-display: swap.
It requires network access; Helvetica Neue/Helvetica/Arial provide fallbacks.
No font binaries are redistributed in this repository.

## Assets

Keep agents-hero-hd.png, the six role-named portraits, tracehound-mark.svg,
and the matching favicon.
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
- index.html: official Switzer and Cabinet Grotesk stylesheet connection.

Build and lint pass. Contrast was checked numerically. The page was rendered
and visually reviewed in Chrome at desktop and mobile sizes; layout assertions
cover 320, 390, 700, 768 and 1440px. Workflow selection, alternating portrait
order, reduced-motion thread behavior and the developer destinations were checked.
Wheel easing, anchor placement and all six thread colors were verified in-browser.

## Logo and wordmark

Use the original hound outline in public/tracehound-mark.svg, drawn as vector
paths rather than cropped from the concept sheet. The descending neck suggests
a trail. Ink blue on white is the default. The favicon uses a slightly heavier
stroke for small sizes. Keep the symbol's viewBox and aspect ratio intact.

Pair it with title-case Tracehound in Cabinet Grotesk 700, tracking -0.025em.
Header: 29px desktop, 24px mobile, 21px on the narrowest screens. Footer: 23px.
Use the same ink blue for symbol and lettering. No trailing period, monogram
tile, multicolor letters, or stretched lettering. The wordmark remains live text
for accessibility; its adjacent image has empty alt text to avoid repetition.

## Product story and interactive walkthrough

The PRD is the source for the value proposition: evidence-first incident
investigation for on-call engineers. The landing page emphasizes cited sources,
competing explanations, visible uncertainty, and next checks under human control.
Six agents explain the approach; inspectable reasoning explains its value.

The four selectable stages are Scope, Investigate, Reason and Review. Each
updates an illustrative investigation brief. The example uses invented telemetry
for checkout-api and is explicitly labeled illustrative, never a live result.
Do not present PRD accuracy targets, future integrations, replay, export or
planned dashboard features as already delivered. Current hypothesis contracts
support confidence rationale, supporting/contradicting evidence and checks.

Keep the walkthrough on white with quiet rules and restrained accents. Use real
buttons, visible selection, keyboard access and a polite live region. Avoid
unnecessary 3D scenes: existing agent illustrations carry the visual personality.

## Scroll behavior

Lenis provides wheel easing with lerp 0.085 and autoRaf enabled. Touch uses native
scrolling (syncTouch false). Same-page links use the same easing, preserve hashes,
respect CSS scroll margins, and focus the destination without a second jump.
Modified clicks and external links retain native behavior. The instance is
removed when reduced motion is enabled and reinstated when it is disabled.
Do not add CSS scroll easing on top of Lenis or introduce scroll snapping.

The thread reads actual page position and updates with requestAnimationFrame;
it does not trigger React renders on every scroll. ResizeObserver recalculates
its geometry when the responsive layout changes.

Implementation: src/useSmoothScroll.ts, src/AgentThread.tsx and
src/InvestigationFlow.tsx. Browser-review tools and screenshots live outside the
repository; node_modules and generated output remain ignored.
