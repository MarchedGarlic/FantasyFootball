"""Shared mobile-responsiveness post-processing for every Bokeh-generated standalone HTML report.

Each report (power rating chart, trade/waiver/manager-grade charts, luck/roster-grade charts) is
opened two ways on a phone: embedded in an auto-sized iframe on the results page, and directly via
each section's "Open full size" link - the direct-link path gets none of the parent page's own
mobile fixes (index.html/results_template.html's iframe autosize + overflow-x:hidden), so every
report file needs its own baseline here.

This used to be duplicated as visualizations.py's private _make_html_mobile_friendly() and was
never applied to trade_analysis.py/power_rankings.py at all. Extracted here, and fixed along the
way - two rounds of fixing, in fact:

1. The row/column *layout* (chart-beside-leaderboard, multi-button toolbars) is made responsive by
   giving each row/column/Div `sizing_mode="stretch_width"` (and buttons `height=44`) in the
   calling code, NOT via CSS here. This turned out to be the only approach that actually works:
2. Bokeh 3.x renders every widget (buttons, Divs, layouts) inside a **Shadow DOM** subtree per
   component - confirmed empirically by walking the real rendered DOM of a generated report
   (72 shadow hosts found; `document.querySelector('.bk-root')` returns null; the only `bk-*`
   classes actually present anywhere are `bk-Column`/`bk-Notifications`). A `<style>` block placed
   in the page's light-DOM `<head>` (which is all a post-processing text-replace step like this
   one can do) **cannot** reach inside those shadow roots - so `.bk-btn`, `.bk-root table`, and
   every other Bokeh-internal selector below is a dead rule against the Bokeh version this repo
   actually pins (bokeh>=2.4.0, installed as 3.9.2). That's also why the *previous* version of this
   file's mobile CSS never visibly did anything - not because the class names were slightly wrong
   for the Bokeh version, but because no external stylesheet can style inside a shadow root at all.
   Verified this fix works by measuring real rendered buttons (exactly height:44 from the Python
   `height=44` kwarg - a genuine Bokeh model property, not CSS) and the stacked layout (real
   `display:flex; flex-direction:column`, width matching the 375px viewport exactly) in a real
   generated report at a 375px viewport.

This module's own reach stops at the *light-DOM* elements one level up from Bokeh's own root -
the viewport meta tag, and `html`/`body` itself. That's genuinely all a post-processing
text-replace step like this one can touch: the dark page background behind the plot (so opening
a report's "Open full size" link doesn't flash white outside the chart) and an `overflow-x:
hidden` safety net. **Everything Bokeh actually renders (buttons, selects, the figure itself) is
styled from Python instead** - see `src/bokeh_theme.py`, which discovered and documents the real
mechanism for that: passing `stylesheets=[InlineStyleSheet(css=...)]` to a Bokeh model injects
CSS straight into that model's own shadow root (verified empirically), which is different from -
and does work, unlike - an external `<style>` tag trying to reach in from outside.
"""

_VIEWPORT_META = '<meta name="viewport" content="width=device-width, initial-scale=1.0">'

_MOBILE_CSS = """
    <style>
        /* Light-DOM-only: everything Bokeh renders lives inside shadow roots this stylesheet
           cannot reach (see module docstring) - real widget/figure theming happens in Python via
           src/bokeh_theme.py instead. This covers only the light-DOM page shell: the dark
           background so a directly-opened report doesn't flash white outside the chart, and an
           overflow-x safety net so one wide shadow-DOM child can't drag the whole page sideways. */
        html, body {
            overflow-x: hidden !important;
            background: #070D18 !important;
            color: #F4F6FA !important;
        }
    </style>"""


def make_bokeh_html_mobile_friendly(filename):
    """Add a viewport meta tag and the light-DOM overflow safety net to a Bokeh output_file() HTML file."""
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            content = f.read()

        if 'name="viewport"' not in content:
            content = content.replace('<meta charset="utf-8">', f'<meta charset="utf-8">\n    {_VIEWPORT_META}')

        if '<!-- bokeh-mobile-css -->' not in content:
            content = content.replace('</head>', f'<!-- bokeh-mobile-css -->{_MOBILE_CSS}\n</head>')

        with open(filename, 'w', encoding='utf-8') as f:
            f.write(content)

        print(f"   [OK] Added mobile responsiveness to {filename}")
    except Exception as e:
        print(f"   [WARN] Could not add mobile responsiveness to {filename}: {e}")
