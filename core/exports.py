"""
Exports du plan d'un élève : Excel, CSV et document imprimable (HTML A4).
"""

from __future__ import annotations

import html
import io
from datetime import date, datetime

import pandas as pd
from openpyxl.styles import Alignment, Font, PatternFill

from .calculs import Pace, format_minutes, format_race_time, fr_number, ratio_formula
from .config import DISPLAY_NAMES, DISTANCES, FREQ_LABELS, PACE_LABELS, ZONE_COLORS
from .plan import week_summary

EXPORT_COLUMNS = ["semaine", "debut", "fin", "phase", "seance", "km_env", "duree_env", "contenu", "km_spe",
                  "allure", "allure_txt", "allure_dec", "vitesse", "temps_spe_min", "frequence", "remarque"]

MONTHS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]


def fr_date(d: date | None, year: bool = False) -> str:
    if d is None:
        return ""
    return f"{d.day} {MONTHS[d.month - 1]}" + (f" {d.year}" if year else "")


def export_table(table: pd.DataFrame) -> pd.DataFrame:
    out = table.reindex(columns=EXPORT_COLUMNS).copy()
    out["allure"] = [PACE_LABELS.get(c, "") if isinstance(c, str) else "" for c in out["allure"]]
    out["frequence"] = [FREQ_LABELS.get(f, "") for f in out["frequence"]]
    out["temps_spe_min"] = pd.to_numeric(out["temps_spe_min"], errors="coerce").round(0)
    return out.rename(columns=DISPLAY_NAMES)


def paces_table(paces: dict[str, Pace], ratios: dict[str, float]) -> pd.DataFrame:
    return pd.DataFrame([{
        "Zone": i, "Allure": p.label, "Correspond à": p.description, "Formule": ratio_formula(p.code, ratios),
        "Vitesse (km/h)": round(p.kmh, 1), "Allure (min/km)": p.pace_str,
        "Équivalence": f"{p.ref_label} en {format_minutes(p.ref_time_minutes)}" if p.ref_time_minutes else "",
    } for i, p in enumerate(paces.values(), start=1)])


def profile_rows(student, objective_seconds: int) -> list[tuple[str, str]]:
    dist = DISTANCES[student.distance]
    return [
        ("Élève", student.display_name), ("E-mail", student.email), ("Distance", dist.label),
        ("Objectif", format_race_time(objective_seconds)),
        ("Date de course", student.date_course.strftime("%d/%m/%Y") if student.date_course else "non renseignée"),
        ("Séances par semaine", str(student.frequence)), ("Semaines de plan", str(student.plan.n_weeks)),
        ("Généré le", datetime.now().strftime("%d/%m/%Y %H:%M")),
    ]


def export_excel(student, table: pd.DataFrame, paces: dict[str, Pace], objective_seconds: int) -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        export_table(table).to_excel(writer, sheet_name="Plan", index=False)
        paces_table(paces, student.ratios).to_excel(writer, sheet_name="Allures", index=False)
        pd.DataFrame(profile_rows(student, objective_seconds), columns=["", "Valeur"]).to_excel(
            writer, sheet_name="Profil", index=False)
        header_fill, band = PatternFill("solid", fgColor="1B4F8C"), PatternFill("solid", fgColor="EAF0F7")
        for ws in writer.book.worksheets:
            for cell in ws[1]:
                cell.font = Font(bold=True, color="FFFFFF")
                cell.fill = header_fill
                cell.alignment = Alignment(vertical="center", wrap_text=True)
            ws.freeze_panes = "A2"
            for col_cells in ws.columns:
                length = max((len(str(c.value)) for c in col_cells if c.value is not None), default=8)
                ws.column_dimensions[col_cells[0].column_letter].width = min(max(9, length + 2), 42)
        ws = writer.book["Plan"]
        headers = [c.value for c in ws[1]]
        date_cols = {headers.index(DISPLAY_NAMES[k]) + 1 for k in ("debut", "fin")}
        shade, previous = False, None
        for row in ws.iter_rows(min_row=2):
            if row[0].value != previous:
                shade, previous = not shade, row[0].value
            for cell in row:
                if shade:
                    cell.fill = band
                if cell.column in date_cols:
                    cell.number_format = "DD/MM/YYYY"
    return buffer.getvalue()


def export_csv(table: pd.DataFrame) -> bytes:
    """CSV pour Excel en français : séparateur « ; », virgule décimale, UTF-8 avec BOM."""
    df = export_table(table)
    for col in (DISPLAY_NAMES["debut"], DISPLAY_NAMES["fin"]):
        df[col] = [d.strftime("%d/%m/%Y") if isinstance(d, date) else "" for d in df[col]]
    return df.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig")


# ----------------------------------------------------------------------------
# Document imprimable
# ----------------------------------------------------------------------------
PRINT_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Barlow:wght@400;500;600&family=Barlow+Condensed:wght@600;700;800&display=swap');
@page { size: A4; margin: 12mm 11mm; }
.doc { font-family: Barlow, Arial, sans-serif; color: #14233A; font-size: 10.5pt; line-height: 1.35; }
.doc * { -webkit-print-color-adjust: exact; print-color-adjust: exact; box-sizing: border-box; }
.doc h1 { font-family: 'Barlow Condensed', Arial Narrow, sans-serif; font-weight: 800; font-size: 26pt;
          margin: 0; line-height: 1; }
.doc .head { display: flex; justify-content: space-between; align-items: flex-end; gap: 16px;
             border-bottom: 3px solid #1B4F8C; padding-bottom: 8px; margin-bottom: 10px; }
.doc .goal { text-align: right; }
.doc .goal b { font-family: 'Barlow Condensed', sans-serif; font-size: 22pt; font-weight: 800; color: #1B4F8C; }
.doc .meta { color: #5B6B80; font-size: 9.5pt; }
.doc table { width: 100%; border-collapse: collapse; }
.doc th { text-align: left; font-weight: 600; font-size: 8.5pt; color: #5B6B80; border-bottom: 1px solid #C9D3DF;
          padding: 3px 5px; }
.doc td { padding: 4px 5px; border-bottom: 1px solid #E3E9F0; vertical-align: top; }
.doc .paces td { padding: 3px 5px; }
.doc .zone { display: inline-block; min-width: 18px; text-align: center; border-radius: 3px; font-weight: 700;
             padding: 0 4px; margin-right: 6px; }
.doc .week { break-inside: avoid; page-break-inside: avoid; margin-top: 12px; }
.doc .week h2 { font-family: 'Barlow Condensed', sans-serif; font-size: 13.5pt; margin: 0 0 2px; font-weight: 700; }
.doc .week h2 small { font-family: Barlow, sans-serif; font-size: 9pt; color: #5B6B80; font-weight: 500; }
.doc .phase { color: #1B4F8C; font-size: 9pt; margin-bottom: 3px; }
.doc .race td { font-weight: 600; background: #FFF4D1; }
.doc .num { white-space: nowrap; font-variant-numeric: tabular-nums; }
.doc .foot { margin-top: 14px; color: #5B6B80; font-size: 8.5pt; }
"""


def _zone_badge(code: str | None, text: str = "") -> str:
    if not code:
        return ""
    bg, fg = ZONE_COLORS[code]
    label = html.escape(PACE_LABELS.get(code, code))
    return (f"<span class='zone' style='background:{bg};color:{fg}'>{html.escape(label)}</span>"
            f"<span class='num'>{html.escape(text)}</span>")


def print_document(student, table: pd.DataFrame, paces: dict[str, Pace], objective_seconds: int) -> str:
    """Corps HTML du plan imprimable (sans <html>), utilisé par le bouton et par le téléchargement."""
    e = html.escape
    dist = DISTANCES[student.distance]
    race = f"Course le {fr_date(student.date_course, True)}" if student.date_course else "Date de course non renseignée"
    parts = [f"<div class='doc'><div class='head'><div><h1>{e(student.display_name)}</h1>"
             f"<div class='meta'>{e(dist.label)} — {e(race)} — {student.frequence} séances par semaine</div></div>"
             f"<div class='goal'><div class='meta'>Objectif</div><b>{e(format_race_time(objective_seconds))}</b></div></div>"]
    rows = "".join(
        f"<tr><td>{_zone_badge(p.code, '')}</td><td class='num'><b>{e(p.pace_str)} /km</b></td>"
        f"<td class='num'>{e(fr_number(p.kmh))} km/h</td><td>{e(p.description)}</td>"
        f"<td class='num'>{e(f'{p.ref_label} en {format_minutes(p.ref_time_minutes)}') if p.ref_time_minutes else ''}</td></tr>"
        for p in paces.values())
    parts.append(f"<table class='paces'><tr><th>Allure</th><th>Rythme</th><th>Vitesse</th><th>Usage</th>"
                 f"<th>Équivalence</th></tr>{rows}</table>")
    if not table.empty:
        for position in sorted(table["position"].unique()):
            sub = table[table["position"] == position]
            first = sub.iloc[0]
            dates = (f" <small>du {fr_date(first['debut'])} au {fr_date(first['fin'])}</small>"
                     if isinstance(first["debut"], date) else "")
            summary = week_summary(sub)
            volume = " — ".join(x for x in (summary.km_str, summary.duration_str) if x)
            parts.append(f"<div class='week'><h2>Semaine {int(position) + 1}{dates}"
                         f"{f' <small>{e(volume)}</small>' if volume else ''}</h2>")
            if first["phase"]:
                parts.append(f"<div class='phase'>{e(first['phase'])}</div>")
            parts.append("<table><tr><th style='width:9%'>Séance</th><th>Contenu</th><th style='width:8%'>Km</th>"
                         "<th style='width:9%'>Durée</th><th style='width:24%'>Allure</th><th style='width:9%'>Temps spé.</th>"
                         "<th style='width:17%'>Remarque</th></tr>")
            for _, r in sub.iterrows():
                cls = " class='race'" if str(r["seance"]).upper().replace(" ", "") == "JOURJ" else ""
                parts.append(
                    f"<tr{cls}><td>{e(str(r['seance']))}</td><td>{e(str(r['contenu']))}</td>"
                    f"<td class='num'>{e(str(r['km_env']))}</td><td class='num'>{e(str(r['duree_env']))}</td>"
                    f"<td>{_zone_badge(r['allure'], r['allure_txt'] + ' /km' if r['allure_txt'] else '')}</td>"
                    f"<td class='num'>{e(str(r['temps_spe']))}</td><td>{e(str(r['remarque']))}</td></tr>")
            parts.append("</table></div>")
    parts.append(f"<div class='foot'>Plan généré le {datetime.now():%d/%m/%Y}. Allures calculées à partir de "
                 f"l'objectif et des formules de ton coach.</div></div>")
    return "".join(parts)


def print_page(body: str, title: str) -> str:
    """Page HTML autonome (téléchargeable), qui s'imprime directement depuis le navigateur."""
    return (f"<!doctype html><html lang='fr'><head><meta charset='utf-8'><title>{html.escape(title)}</title>"
            f"<meta name='viewport' content='width=device-width, initial-scale=1'>"
            f"<style>{PRINT_CSS} body{{margin:24px;background:#fff}} @media print{{body{{margin:0}}}}</style>"
            f"</head><body>{body}</body></html>")


def print_button_html(body: str, label: str = "Imprimer le plan") -> str:
    """Bouton à intégrer dans l'application : imprime le document (masqué à l'écran)."""
    return f"""
<style>
{PRINT_CSS}
html, body {{ margin: 0; background: transparent; }}
.btn {{ font-family: Barlow, Arial, sans-serif; font-size: 15px; font-weight: 600; color: #fff; background: #1B4F8C;
        border: 1.5px solid #1B4F8C; border-radius: 8px; padding: 0 16px; height: 40px; width: 100%; cursor: pointer; }}
.btn:hover {{ background: #0F2A4A; }}
.btn:focus-visible {{ outline: 3px solid #FFC629; outline-offset: 2px; }}
@media screen {{ .doc {{ display: none; }} }}
@media print {{ .btn {{ display: none; }} html, body {{ background: #fff; }} }}
</style>
<button class="btn" onclick="window.print()">🖨️ {html.escape(label)}</button>
{body}
"""
