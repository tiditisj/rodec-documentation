# Annotated pages

One JSON file per page. `tools/build.py` turns it into: a hero (label, two-tone
title, optional lead), one or more panels (image with numbered badges + a
legend), then the full original text of the page from `content/`.

```json
{
  "path": "/rodec-mx-modular/control-section/monitor-section",
  "title": "Monitor section.",
  "title_em": "Outputs and headphones.",
  "lead": "optional, one sentence, only facts that are in the page text",
  "panels": [
    {
      "image": "assets/images/<file>",
      "alt": "what the image shows",
      "heading": "optional title above this panel (when a page has several)",
      "caption": "optional line under the image",
      "items": [
        {
          "name": "Master fader",
          "label": "MASTER",
          "at": [218, 189],
          "rect": [214, 8, 268, 372],
          "text": "The red fader sets the volume of the <strong>Main Outputs</strong>, also shown on the Main VU Meters.",
          "ref": {"strong": "Red Fader: Master Out Volume"}
        }
      ]
    }
  ]
}
```

- Coordinates are pixels of the ORIGINAL image file (before any crop).
  `at` is where the badge (a 24 px circle) is centred: next to the control,
  not on top of its printed label or on top of another control. `rect` is the
  highlight around the control (optional).
- `label` is the text printed on the panel (as printed, short). Optional.
- `text` is one short sentence, rewritten tightly from the page text, no
  new facts. `<strong>` allowed.
- `ref` is where "Read more" jumps: `{"strong": "..."}` is the exact text of a
  `<strong>` that opens a `<p>`, `<li>` or heading in the page's
  `content/<path>/index.html`; or `{"id": "h.xxxx"}` for a heading id.
- Numbers run in legend order across panels; order the items the way the
  text describes them (or top to bottom, left to right).
- The panel image is removed from the text below (it is shown in the panel).
- `"crop": [x0, y0, x1, y1]` (per panel, optional) shows only that part of
  the image; coordinates stay in original image pixels.
- Page options: `hero_image` + `hero_style` ("dark" for renders on black,
  "light" for product photos), `lead`, `specs` ([[label, value], ...]),
  `remove_images` (file names to take out of the text), `blocks` (HTML
  fragments from `src/pages/fragments/` after the panels), `card_images` and
  `card_texts` (picture and one line per subpage card). An item with `link`
  instead of `ref` opens another page.
- `"corrections": [["find", "replace"], ...]` (optional) fixes the page text
  on the new site where the captured text is wrong; `content/` stays as
  captured. The build stops if a find text is not in the page.

Check a file without building, and get a preview PNG with the badges:

```bash
.venv/bin/python tools/preview_annotation.py src/annotations/<name>.json /tmp
```

Pick coordinates on a grid (labels are original pixels):

```bash
.venv/bin/python tools/grid_image.py assets/images/<file> /tmp/grid.png 1400
```
