"""KPI cards, source badges and status boxes (HTML rendered via st.markdown).

Colours use translucent greys and `inherit` so the same markup reads well in
both Streamlit's light and dark themes.
"""

from __future__ import annotations

from html import escape
from typing import Literal

import streamlit as st

Kind = Literal["observed", "forecast", "model", "derived"]

_BADGE_TEXT: dict[Kind, str] = {
    "observed": "Observed",
    "forecast": "Forecast",
    "model": "Model comparison",
    "derived": "Derived",
}

_CSS = """
<style>
.block-container { padding-top: 2.2rem; max-width: 1400px; }
.wx-header h1 { font-size: 1.9rem; font-weight: 650; margin: 0; letter-spacing: -0.01em; }
.wx-header .wx-meta { opacity: .72; font-size: .92rem; margin-top: .25rem; }
.wx-card {
  border: 1px solid rgba(128,128,128,.24); border-radius: 12px;
  background: rgba(128,128,128,.05); padding: .85rem 1rem .8rem; height: 100%;
}
.wx-card-label { font-size: .78rem; display: flex; flex-direction: column-reverse;
  align-items: flex-start; gap: .35rem; text-transform: uppercase; letter-spacing: .04em; }
.wx-card-label > span:first-child { opacity: .75; }
.wx-card-value { font-size: 1.65rem; font-weight: 650; margin-top: .3rem; line-height: 1.2; }
.wx-card-sub { font-size: .78rem; opacity: .68; margin-top: .25rem; }
.wx-badge { font-size: .64rem; font-weight: 600; letter-spacing: .03em; text-transform: uppercase;
  padding: .08rem .45rem; border-radius: 999px; border: 1px solid; white-space: nowrap; }
.wx-badge.observed { color: #0ca30c; border-color: rgba(12,163,12,.5); }
.wx-badge.forecast { color: #3987e5; border-color: rgba(57,135,229,.5); }
.wx-badge.model    { color: #d95926; border-color: rgba(217,89,38,.5); }
.wx-badge.derived  { color: #898781; border-color: rgba(137,135,129,.6); }
.wx-panel { border: 1px solid rgba(128,128,128,.24); border-radius: 12px; padding: 1rem 1.1rem; height: 100%; }
.wx-panel h4 { margin: 0 0 .5rem 0; font-size: 1rem; font-weight: 600; display: flex; gap: .5rem; align-items: center; }
.wx-kv { display: grid; grid-template-columns: max-content 1fr; gap: .2rem 1rem; font-size: .9rem; }
.wx-kv .k { opacity: .68; }
.wx-unavailable { border: 1px dashed rgba(208,59,59,.6); border-radius: 12px; padding: .9rem 1rem; }
.wx-unavailable b { color: #d03b3b; }
.wx-day { border: 1px solid rgba(128,128,128,.24); border-radius: 12px; padding: .8rem .7rem;
  text-align: center; height: 100%; }
.wx-day .d1 { font-weight: 600; font-size: .95rem; }
.wx-day .d2 { font-size: .75rem; opacity: .65; }
.wx-day .ic { font-size: 2rem; margin: .35rem 0 .15rem; }
.wx-day .cond { font-size: .78rem; min-height: 2.1em; opacity: .85; }
.wx-day .temps { font-size: 1.05rem; font-weight: 600; margin: .3rem 0; }
.wx-day .temps .lo { opacity: .6; font-weight: 500; }
.wx-day .meta { font-size: .76rem; opacity: .75; line-height: 1.5; }
.wx-day .strip { height: 4px; border-radius: 4px; margin: -.8rem -.7rem .6rem; }
table.wx-cond { border-collapse: separate; border-spacing: 3px; width: 100%; font-size: .82rem; }
table.wx-cond th { font-weight: 600; opacity: .7; text-align: center; padding: .2rem; }
table.wx-cond td { text-align: center; padding: .45rem .3rem; border-radius: 6px; }
table.wx-cond td.rowh { text-align: left; font-weight: 600; opacity: .85; white-space: nowrap; }
.wx-legend { display: flex; flex-wrap: wrap; gap: .8rem; font-size: .8rem; margin-top: .4rem; opacity: .85; }
.wx-legend span.sw { display: inline-block; width: 10px; height: 10px; border-radius: 3px; margin-right: 4px; }
.wx-table-wrap { overflow-x: auto; }
table.wx-table { border-collapse: collapse; width: 100%; font-size: .82rem; }
table.wx-table th { text-align: left; font-weight: 600; opacity: .75; padding: .4rem .55rem;
  border-bottom: 1px solid rgba(128,128,128,.35); white-space: nowrap; }
table.wx-table td { padding: .38rem .55rem; border-bottom: 1px solid rgba(128,128,128,.15); vertical-align: top; }
table.wx-table td.num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
table.wx-table th.num { text-align: right; }
.wx-disclaimer { font-size: .8rem; opacity: .7; border-left: 3px solid rgba(128,128,128,.4); padding-left: .7rem; }
</style>
"""


def inject_css() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)


def badge(kind: Kind, text: str | None = None) -> str:
    return f'<span class="wx-badge {kind}">{escape(text or _BADGE_TEXT[kind])}</span>'


def kpi_card(label: str, value: str, kind: Kind, sub: str = "") -> str:
    """HTML for a single KPI card. `sub` should state the source and timestamp."""
    return (
        f'<div class="wx-card"><div class="wx-card-label"><span>{escape(label)}</span>{badge(kind)}</div>'
        f'<div class="wx-card-value">{escape(value)}</div>'
        f'<div class="wx-card-sub">{escape(sub)}</div></div>'
    )


def render_kpi_row(cards: list[str]) -> None:
    for col, card in zip(st.columns(len(cards)), cards):
        col.markdown(card, unsafe_allow_html=True)


def key_value_panel(title: str, kind: Kind, rows: list[tuple[str, str]], footer: str = "") -> str:
    body = "".join(f'<div class="k">{escape(k)}</div><div>{escape(v)}</div>' for k, v in rows)
    foot = f'<div class="wx-card-sub" style="margin-top:.6rem">{escape(footer)}</div>' if footer else ""
    return (f'<div class="wx-panel"><h4>{escape(title)} {badge(kind)}</h4>'
            f'<div class="wx-kv">{body}</div>{foot}</div>')


def render_table(rows: list[dict[str, str]], numeric_cols: tuple[str, ...] = ()) -> None:
    """Render rows of pre-formatted strings as an HTML table.

    Plain HTML is used instead of st.dataframe so tables work without pyarrow
    (its native DLL is blocked on some locked-down Windows machines).
    """
    if not rows:
        return
    cols = list(rows[0])

    def cls(c: str) -> str:
        return ' class="num"' if c in numeric_cols else ""

    head = "".join(f"<th{cls(c)}>{escape(c)}</th>" for c in cols)
    body = "".join("<tr>" + "".join(f"<td{cls(c)}>{escape(str(r.get(c, '')))}</td>" for c in cols) + "</tr>"
                   for r in rows)
    st.markdown(f'<div class="wx-table-wrap"><table class="wx-table"><thead><tr>{head}</tr></thead>'
                f"<tbody>{body}</tbody></table></div>", unsafe_allow_html=True)


def unavailable(what: str, reason: str, last_success: str | None = None) -> str:
    last = (f"<br><span style='opacity:.75'>Last successful update: {escape(last_success)}</span>"
            if last_success else "<br><span style='opacity:.75'>No successful update in this session.</span>")
    return f'<div class="wx-unavailable"><b>Data unavailable</b> — {escape(what)}<br>{escape(reason)}{last}</div>'


def render_unavailable(what: str, reason: str, last_success: str | None = None) -> None:
    st.markdown(unavailable(what, reason, last_success), unsafe_allow_html=True)
