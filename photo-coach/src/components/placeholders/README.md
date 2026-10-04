# Placeholder components

Stand-ins for the Figma components. The onboarding screens (`src/app/onboarding/`) only
use what's in this folder for their UI, so replacing a placeholder with its Figma version
restyles every screen at once.

To swap one in: keep the file name, export name and props, and change what it renders.
If the Figma component needs different props, update the screens that use it.

| Component | Used for |
|---|---|
| `Screen` | Page frame: safe areas, padding, back button, footer buttons |
| `Button` | `primary`, `secondary` and `text` buttons |
| `Illustration` | Dashed box marking where a Figma illustration goes |
| `ProgressBar` | Progress through the picks |
| `StepRow` | Numbered step on "How it works" |
| `PriorityRow` | One learned priority on the results screen |
| `Badge` | Small label, e.g. how sure the results are |
