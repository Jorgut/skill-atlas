# Skill Atlas showcase site

Static, dependency-free, trilingual showcase site for Skill Atlas. It is served
straight from this directory by GitHub Pages (see
`.github/workflows/pages.yml`), so there is no build step: HTML, one shared
stylesheet (`styles.css`), one tiny deferred script (`motion.js`) and SVG
diagrams in `assets/`.

Pages:

| Page | Path |
| --- | --- |
| English | `/` (`index.html`) |
| Simplified Chinese | `/zh-CN/` |
| Russian | `/ru/` |

## Preview locally

Serve this directory over HTTP (opening the files with `file://` also works,
but a local server matches the deployed URLs and relative links):

```bash
# from the repository root
python3 -m http.server 8000 --directory site
```

Then open:

- <http://127.0.0.1:8000/>
- <http://127.0.0.1:8000/zh-CN/>
- <http://127.0.0.1:8000/ru/>

## Screenshots

`scripts/screenshot.sh` captures all three pages with headless Chrome:

```bash
# deployed site (default): ./screenshots/en.png, zh.png, ru.png
scripts/screenshot.sh

# local preview
scripts/screenshot.sh /tmp/skill-atlas-shots http://127.0.0.1:8000/

# tablet width
WINDOW_SIZE=768,2400 scripts/screenshot.sh /tmp/skill-atlas-shots-tablet http://127.0.0.1:8000/

# full desktop page in one image (the English page is about 5400 px tall)
WINDOW_SIZE=1440,5600 scripts/screenshot.sh /tmp/skill-atlas-shots-full http://127.0.0.1:8000/
```

Arguments: `[output-dir] [base-url]` (defaults `./screenshots` and
`https://jorgut.github.io/skill-atlas/`). The script:

- uses `$CHROME` or `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`
  and fails with a clear message when Chrome is missing;
- runs `--headless=new --disable-gpu --no-sandbox --hide-scrollbars` with a
  throwaway temporary `--user-data-dir` (a shared profile cannot be used by a
  running browser and may be read-only in sandboxed sessions);
- waits `VIRTUAL_TIME_BUDGET` (default 6000 ms of virtual time) so entrance
  animations and the terminal typing finish before the shot;
- prints the absolute path of every PNG.

`WINDOW_SIZE` defaults to `1440,3200` and is a viewport capture, not a
full-page capture; use a taller height (see above) when you need the whole page.

### Phone-width captures

Headless Chrome clamps its layout viewport to a minimum width of about 500 CSS
px: `--window-size=390,1400` still lays the page out at 500 px and crops the PNG
to 390 px, so it is not a real phone rendering (the script warns when asked for
a width below 500). For a true 390 px rendering, use Chrome DevTools device
emulation (Responsive mode, 390 x 844) or the CDP method
`Emulation.setDeviceMetricsOverride({ width: 390, height: 844, deviceScaleFactor: 1, mobile: true })`
with `Page.captureScreenshot`. The motion on this site was checked that way at
390 px: no horizontal page overflow, and terminal blocks scroll horizontally
inside their own `<pre>` exactly as they did before the motion work.

## Motion and progressive enhancement

`motion.js` (deferred, no dependencies, no network requests) adds:

- scroll reveals for section headings, cards, figures, tables and link lists
  (IntersectionObserver; only elements below the fold are prepared, so nothing
  is hidden on load);
- terminal presentation: the existing command line is typed character by
  character, then the existing output is streamed line by line. The final text
  is identical to the HTML; nothing is invented;
- a soft shadow/border change on the sticky header after scrolling.

The hero entrance and the slow glow behind the hero are pure CSS, so they also
work without JavaScript. Accessibility and robustness:

- `prefers-reduced-motion: reduce` disables reveals, typing, the glow loop,
  hover lifts and transitions, and shows the final state immediately. The
  preference is re-read if the visitor changes it while the page is open.
- With JavaScript disabled, or if `motion.js` fails to load, no content is
  hidden: every page stays complete and readable.
- Animated properties are limited to `transform` and `opacity`; motion never
  affects layout, and the terminal reserves its final height before typing.
- Keyboard focus stays visible; focusing a not-yet-revealed link reveals it.

## Limits

- No trackers, cookies, analytics, third-party fonts or external assets; the
  only external links point at the repository.
- The screenshot script needs network access for the default deployed URL;
  pass a local URL for offline captures.
- Screenshot PNGs are not committed to the repository.
