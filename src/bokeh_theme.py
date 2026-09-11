"""Shared dark-theme styling for every Bokeh-generated report (2026-09 redesign).

Bokeh 3.x renders every widget (buttons, selects, layouts) inside a Shadow DOM subtree per
component - see bokeh_mobile.py's docstring for how that was confirmed empirically, and why an
external <style> tag in the page's light DOM can't reach `.bk-btn` etc. What *does* work, and
wasn't discovered until this pass: passing `stylesheets=[InlineStyleSheet(css=...)]` directly to
a Bokeh model. Bokeh injects that CSS into the model's own shadow root, which is exactly the
supported, version-stable mechanism for this (verified empirically against a real rendered
button/select/figure before committing to it). That's what makes real dark-theme widget styling
(not just Python model properties like height/sizing_mode) possible here.

Figure-level colors (background_fill_color, axis/grid colors, etc.) are plain Bokeh model
properties, not CSS, and always worked - they just hadn't been set to anything but Bokeh's light
default before.
"""

from bokeh.models import InlineStyleSheet, Button, CustomJS

VOID = "#070D18"
SURFACE = "#101B2D"
SURFACE_RAISED = "#18283F"
INK = "#F4F6FA"
INK_MUTED = "#8DA0BC"
LINE = "#22344E"
ACCENT = "#FF6A2B"
ACCENT_DEEP = "#C83803"
GOOD = "#34D399"
BAD = "#F87171"

# Bokeh's default Category20 is tuned for a white background - several of its hues (dark green,
# dark red-brown, dark blue-grey) are nearly invisible against this app's new navy void. This is
# a curated, higher-brightness/higher-saturation categorical set instead, still one color per
# manager (functional data encoding, not decoration - CLAUDE.md section 10's original "leave the
# chart-data palette alone" note was written for a light-canvas page; the whole page changing to
# dark is what motivates revisiting it here).
DARK_CATEGORICAL = [
    "#FF6A2B", "#4C9AFF", "#34D399", "#F87171", "#FBBF24", "#C084FC",
    "#22D3EE", "#FB923C", "#A3E635", "#F472B6", "#818CF8", "#2DD4BF",
    "#FCA5A5", "#93C5FD", "#FDE047", "#5EEAD4", "#F0ABFC", "#BEF264",
    "#FDBA74", "#67E8F9",
]


def dark_palette(n):
    """n colors from the dark-optimized categorical set, cycling if n exceeds its length."""
    if n <= 0:
        return []
    return [DARK_CATEGORICAL[i % len(DARK_CATEGORICAL)] for i in range(n)]


def style_figure(fig, y_zero_line=False):
    """Apply the dark theme to a Bokeh figure: plot/border fill, grid, axes, title. Figure-level
    color properties are plain Bokeh model attributes (not CSS) and have always worked - this
    just centralizes what value they're set to instead of leaving Bokeh's light-mode defaults."""
    fig.background_fill_color = SURFACE
    fig.border_fill_color = VOID
    fig.outline_line_color = LINE

    fig.grid.grid_line_color = LINE
    fig.grid.grid_line_alpha = 0.6

    fig.xaxis.axis_line_color = LINE
    fig.yaxis.axis_line_color = LINE
    fig.xaxis.major_tick_line_color = LINE
    fig.yaxis.major_tick_line_color = LINE
    fig.xaxis.minor_tick_line_color = None
    fig.yaxis.minor_tick_line_color = None
    fig.xaxis.major_label_text_color = INK_MUTED
    fig.yaxis.major_label_text_color = INK_MUTED
    fig.xaxis.axis_label_text_color = INK_MUTED
    fig.yaxis.axis_label_text_color = INK_MUTED

    fig.title.text_color = INK
    fig.title.text_font = "Oswald, Arial Narrow, sans-serif"

    if y_zero_line:
        fig.line([-10000, 10000], [0, 0], line_color=LINE, line_width=1, line_dash="dashed", level="underlay")

    return fig


def style_legend(legend):
    legend.background_fill_color = SURFACE_RAISED
    legend.background_fill_alpha = 0.92
    legend.border_line_color = LINE
    legend.label_text_color = INK
    legend.title_text_color = INK_MUTED
    return legend


def legend_toggle_button(*legends):
    """A small button that shows/hides one or more Legend annotations, hidden by default.

    Legends render *inside* the plot frame (see style_figure's docstring on figures, and the
    per-chart comments on why side panels were dropped: an outside 'right'/'left' panel adds its
    own fixed pixel width that sizing_mode can't compensate for, pushing the whole figure wider
    than a phone viewport). That fixed the width-overflow bug, but left a new one: on a narrow
    phone screen an always-visible inside-frame legend can sit directly on top of the chart data
    it's describing - real user report: "the legends overlay too much on mobile so i can't see
    the graph." Defaulting every legend to hidden and making it an explicit tap-to-reveal action
    fixes that without losing the click-a-legend-item-to-isolate-a-series interaction entirely -
    it's just opt-in instead of a permanent overlay.
    """
    for legend in legends:
        legend.visible = False

    button = Button(label="Show Legend", sizing_mode="stretch_width", height=44,
                     stylesheets=[button_stylesheet("muted")])
    button.js_on_event("button_click", CustomJS(args=dict(legends=list(legends)), code="""
        const newVisible = !legends[0].visible;
        for (const legend of legends) { legend.visible = newVisible; }
        cb_obj.label = newVisible ? "Hide Legend" : "Show Legend";
    """))
    return button


# ---- widget stylesheets (the real shadow-DOM-reaching mechanism, see module docstring) ----

def button_stylesheet(variant="primary"):
    """variant: 'primary' (filled accent), 'ghost' (outline), or 'muted' (quiet secondary)."""
    if variant == "ghost":
        css = f"""
        .bk-btn {{
            background-color: transparent !important;
            color: {INK} !important;
            border: 1px solid {LINE} !important;
            border-radius: 999px !important;
            font-family: 'Inter', sans-serif !important;
            font-weight: 600 !important;
            transition: border-color .15s ease, background-color .15s ease;
        }}
        .bk-btn:hover {{ background-color: {SURFACE_RAISED} !important; border-color: {INK_MUTED} !important; }}
        """
    elif variant == "muted":
        css = f"""
        .bk-btn {{
            background-color: {SURFACE_RAISED} !important;
            color: {INK_MUTED} !important;
            border: 1px solid {LINE} !important;
            border-radius: 999px !important;
            font-family: 'Inter', sans-serif !important;
            font-weight: 600 !important;
        }}
        .bk-btn:hover {{ color: {INK} !important; border-color: {INK_MUTED} !important; }}
        """
    else:
        css = f"""
        .bk-btn {{
            background-color: {ACCENT} !important;
            color: {VOID} !important;
            border: none !important;
            border-radius: 999px !important;
            font-family: 'Inter', sans-serif !important;
            font-weight: 700 !important;
            transition: background-color .15s ease;
        }}
        .bk-btn:hover {{ background-color: #FF7E47 !important; }}
        """
    return InlineStyleSheet(css=css)


def select_stylesheet():
    css = f"""
    :host {{ font-family: 'Inter', sans-serif !important; }}
    select {{
        background-color: {VOID} !important;
        color: {INK} !important;
        border: 1px solid {LINE} !important;
        border-radius: 10px !important;
        font-family: 'Inter', sans-serif !important;
        font-weight: 600 !important;
        padding: 6px 10px !important;
    }}
    select:focus {{ border-color: {ACCENT} !important; outline: none !important; }}
    label {{ color: {INK_MUTED} !important; font-family: 'Inter', sans-serif !important; font-weight: 600 !important; }}
    """
    return InlineStyleSheet(css=css)


def multiselect_stylesheet():
    css = f"""
    :host {{ font-family: 'Inter', sans-serif !important; }}
    select {{
        background-color: {VOID} !important;
        color: {INK} !important;
        border: 1px solid {LINE} !important;
        border-radius: 10px !important;
        font-family: 'Inter', sans-serif !important;
    }}
    select option:checked {{ background-color: {ACCENT} !important; color: {VOID} !important; }}
    label {{ color: {INK_MUTED} !important; font-family: 'Inter', sans-serif !important; font-weight: 600 !important; }}
    """
    return InlineStyleSheet(css=css)


def slider_stylesheet():
    css = f"""
    :host {{ font-family: 'Inter', sans-serif !important; }}
    .noUi-target {{ background: {SURFACE_RAISED} !important; border: 1px solid {LINE} !important; box-shadow: none !important; }}
    .noUi-connect {{ background: {ACCENT} !important; }}
    .noUi-handle {{ background: {ACCENT} !important; border: 2px solid {VOID} !important; box-shadow: 0 0 0 3px rgba(255,106,43,0.25) !important; }}
    label {{ color: {INK_MUTED} !important; font-family: 'Inter', sans-serif !important; font-weight: 600 !important; }}
    """
    return InlineStyleSheet(css=css)


# ---- shared Div-panel HTML fragments (light-DOM content strings - not blocked by shadow DOM,
# see bokeh_mobile.py, so plain inline style="" attributes on the HTML a Div renders work fine) ----

PANEL_STYLE = (
    f"background-color: {SURFACE}; border: 1px solid {LINE}; border-radius: 16px; "
    f"padding: 18px 20px; margin: 8px 0; color: {INK};"
)
CALLOUT_STYLE = (
    f"background-color: {SURFACE_RAISED}; border-left: 4px solid {ACCENT}; border-radius: 12px; "
    f"padding: 16px 18px; margin: 8px 0; color: {INK};"
)
HEADING_STYLE = f"margin: 0 0 12px 0; color: {INK}; font-family: 'Oswald', sans-serif; font-weight: 600; font-size: 19px;"
# The "make the description larger, in a different place" description text style - explicit
# user request, applied to every report's own explanatory copy the same way it was applied to
# src/ai_overview.py's .section-caption.
DESCRIPTION_STYLE = f"margin: 0; color: {INK_MUTED}; font-size: 16px; line-height: 1.55;"
LABEL_STYLE = f"margin: 3px 0; color: {INK_MUTED}; font-size: 14px; line-height: 1.5;"


def collapsible_description_html(short_html, full_extra_html, toggle_id):
    """Wraps `full_extra_html` so it's collapsed by default behind a 'Read more' toggle on a
    narrow (phone-width) viewport, while `short_html` stays always visible - on a wider viewport
    everything just shows, same as before, with no toggle button at all. A media query, not a
    fixed screen-size check, decides which mode applies - since this is a standalone report
    page rendered inside an iframe, "narrow" means the iframe's own rendered width, not the
    outer app shell's window width.

    `toggle_id` must be unique per call on the page - each report typically calls this once for
    its main explanation panel, so the report's own name (e.g. "power-rating-expl") is enough.
    """
    # The onclick handler below deliberately doesn't use document.getElementById() - Bokeh
    # renders this whole Div inside its own shadow root (see this module's docstring), and
    # getElementById on the top-level `document` can't see across that boundary, so it would
    # silently return null and the handler would throw and do nothing (confirmed empirically:
    # the click registered, but nothing toggled). Reaching the sibling div through the button's
    # own local DOM position (previousElementSibling) works regardless of which shadow root -
    # or none - this ends up in.
    return f"""
    {short_html}
    <div id="{toggle_id}-full" style="display:none;">{full_extra_html}</div>
    <button id="{toggle_id}-btn" type="button" onclick="
        var full = this.previousElementSibling;
        var expanded = full.style.display !== 'none';
        full.style.display = expanded ? 'none' : 'block';
        this.textContent = expanded ? 'Read more ▾' : 'Show less ▴';
    " style="display:none; background:none; border:none; color:{ACCENT}; font-weight:600; font-size:14px; cursor:pointer; padding:8px 0 0; text-align:left;">Read more &#9662;</button>
    <style>
        @media (max-width: 640px) {{ #{toggle_id}-btn {{ display: inline-block !important; }} }}
        @media (min-width: 641px) {{ #{toggle_id}-full {{ display: block !important; }} }}
    </style>
    """


def responsive_table_toggle_html(table_id):
    """A 'Show all columns'/'Fewer columns' toggle for a table that marks its less-critical
    `<th>`/`<td>` cells with `class="col-secondary"`. On a narrow (phone-width) viewport those
    cells are hidden by default; on a wider viewport they're always shown and this toggle stays
    hidden, matching collapsible_description_html's split. Call this once immediately after the
    `</table>` tag it applies to - the toggle finds the table via `this.previousElementSibling`
    (see collapsible_description_html's docstring for why not document.getElementById).

    The `<table>` itself must carry `id="{table_id}"` - `table_id` must be unique per call on
    the page.
    """
    return f"""
    <button id="{table_id}-toggle" type="button" onclick="
        var table = this.previousElementSibling;
        var expanded = table.classList.toggle('col-secondary-visible');
        this.textContent = expanded ? 'Fewer columns' : 'Show all columns ▸';
    " style="display:none; background:none; border:none; color:{ACCENT}; font-weight:600; font-size:13px; cursor:pointer; padding:6px 0 0; text-align:left;">Show all columns &#9656;</button>
    <style>
        @media (max-width: 640px) {{
            #{table_id}-toggle {{ display: inline-block !important; }}
            #{table_id}:not(.col-secondary-visible) .col-secondary {{ display: none; }}
        }}
    </style>
    """
