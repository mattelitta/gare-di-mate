"""Esportazione in PDF dei risultati di una gara terminata.

Pagine: classifica finale (la fotografia calcolata dall'Admin) e valori dei problemi come barre
orizzontali, poi lo stato della gara
(griglia squadre × problemi come nel display, in orizzontale, su più pagine se le squadre sono tante).
"""
from datetime import datetime
from pathlib import Path

from fpdf import FPDF

from gdm import formato
from gdm.engine import compute_state, rank_teams
from gdm.models import Competition

# Caratteri: Arial di Windows se c'è (tutti i caratteri), altrimenti Helvetica (solo latin-1).
_FONT_DIR = Path("C:/Windows/Fonts")
_ARIAL = {"": _FONT_DIR / "arial.ttf", "B": _FONT_DIR / "arialbd.ttf"}

VERDE = (134, 239, 172)     # risolto
ROSSO = (252, 165, 165)     # solo risposte sbagliate
GIALLO = (234, 179, 8)      # bordo del jolly
QUALIFICATA = (220, 252, 231)
GRIGIO_RIGA = (243, 244, 246)
INTESTAZIONE = (226, 232, 240)


class ClassificaNonAggiornata(Exception):
    """La classifica finale salvata non corrisponde più ai punteggi attuali."""


class _PDF(FPDF):
    def __init__(self, titolo: str):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.titolo = titolo
        self.esportato = datetime.now().strftime("%d/%m/%Y %H:%M")
        self.unicode = all(p.exists() for p in _ARIAL.values())
        if self.unicode:
            for stile, percorso in _ARIAL.items():
                self.add_font("Testo", stile, str(percorso))
            self.famiglia = "Testo"
        else:
            self.famiglia = "Helvetica"
        self.set_auto_page_break(auto=False)
        self.set_margins(12, 12, 12)

    def t(self, testo) -> str:
        """Testo stampabile con il carattere in uso."""
        testo = str(testo)
        if self.unicode:
            return testo
        return testo.replace("—", "-").replace("×", "x").encode("latin-1", "replace").decode("latin-1")

    def carattere(self, dimensione: float, grassetto: bool = False):
        self.set_font(self.famiglia, "B" if grassetto else "", dimensione)

    def footer(self):
        self.set_y(-10)
        self.carattere(8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 5, self.t(f"{self.titolo} — Gare di Mate, esportato il {self.esportato}"), align="L")
        self.set_x(self.l_margin)
        self.cell(0, 5, self.t(f"Pagina {self.page_no()}"), align="R")
        self.set_text_color(0, 0, 0)

    def intestazione(self, sottotitolo: str, nota: str = ""):
        self.carattere(16, True)
        self.cell(0, 8, self.t(self.titolo), new_x="LMARGIN", new_y="NEXT")
        self.carattere(12, True)
        self.set_text_color(60, 60, 60)
        self.cell(0, 7, self.t(sottotitolo), new_x="LMARGIN", new_y="NEXT")
        if nota:
            self.carattere(9)
            self.set_text_color(110, 110, 110)
            self.multi_cell(0, 4.5, self.t(nota), new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(0, 0, 0)
        self.ln(3)

    def riga(self, celle, larghezze, altezza, allineamenti, riempimento=None, grassetto=False, dimensione=10):
        self.carattere(dimensione, grassetto)
        if riempimento:
            self.set_fill_color(*riempimento)
        for testo, w, a in zip(celle, larghezze, allineamenti):
            self.cell(w, altezza, self.t(testo), border="B", align=a, fill=bool(riempimento))
        self.ln(altezza)


def _verifica_aggiornata(comp: Competition, team_scores) -> None:
    attuale = [(ts.team_id, ts.total) for ts in rank_teams(team_scores, comp)]
    salvata = [(t["id"], t["total"]) for t in comp.final_ranking]
    if attuale != salvata:
        raise ClassificaNonAggiornata(
            "I punteggi sono cambiati dopo il calcolo della classifica finale: "
            "ricalcolarla prima di esportare il PDF.")


def _scala(massimo: float) -> float:
    """Passo "tondo" per le linee della griglia (circa 5 linee)."""
    grezzo = max(1.0, massimo / 5)
    potenza = 10 ** len(str(int(grezzo))) / 10
    for m in (1, 2, 2.5, 5, 10):
        if m * potenza >= grezzo:
            return m * potenza
    return 10 * potenza


def _barre(pdf: _PDF, voci: list, linea_dopo: int | None = None):
    """Grafico a barre orizzontali (tutte dello stesso colore) nella pagina verticale corrente.

    voci: {"valore", "pos", "num", "nome"} oppure None per uno spazio (separatore).
    linea_dopo: indice della riga sotto cui tracciare la linea rossa (es. ultima qualificata)."""
    x_pos, x_num, x_nome = pdf.l_margin, pdf.l_margin + 11, pdf.l_margin + 21
    y_scala = pdf.get_y() + 2
    y0, y_fine = y_scala + 5, 282.0
    # Un po' di spazio in più dove passa la linea rossa delle qualificate.
    con_linea = linea_dopo is not None and 0 <= linea_dopo < len(voci) - 1
    stacco = 2.5 if con_linea else 0.0
    h = min(8.0, (y_fine - y0 - stacco) / max(len(voci), 1))
    y_riga = lambda i: y0 + i * h + (stacco if con_linea and i > linea_dopo else 0.0)
    dim = max(5.0, min(10.0, h * 1.8))
    # La colonna dei nomi è larga quanto il nome più lungo della pagina (al massimo 63 mm):
    # con nomi corti le barre prendono tutto lo spazio che resta.
    pdf.carattere(dim)
    w_nomi = max([pdf.get_string_width(pdf.t(v["nome"])) for v in voci if v] + [10.0])
    x0 = x_nome + min(63.0, w_nomi) + 3
    x1 = 210 - pdf.r_margin - 12                              # a destra resta lo spazio per il valore
    valori = [v["valore"] for v in voci if v]
    vmax, vmin = max(valori + [1]), min(valori + [0])
    passo = _scala(vmax - vmin)
    alto = passo * (int(vmax / passo) + 1)
    basso = -passo * (int(-vmin / passo) + 1) if vmin < 0 else 0.0
    x_di = lambda v: x0 + (v - basso) / (alto - basso) * (x1 - x0)

    # griglia verticale con la scala in alto
    pdf.set_draw_color(225, 225, 225)
    pdf.set_line_width(0.2)
    pdf.carattere(7)
    pdf.set_text_color(130, 130, 130)
    y_ultima = y_riga(len(voci))
    v = basso
    while v <= alto + 1e-9:
        x = x_di(v)
        pdf.line(x, y0, x, y_ultima)
        pdf.set_xy(x - 10, y_scala)
        pdf.cell(20, 4, f"{v + 0.0:g}", align="C")
        v += passo
    pdf.set_text_color(0, 0, 0)

    x_zero = x_di(0)
    for i, voce in enumerate(voci):
        if not voce:
            continue
        y = y_riga(i)
        # etichette a sinistra: posizione, numero, nome (accorciato se non ci sta)
        pdf.carattere(dim, True)
        pdf.set_xy(x_pos, y)
        pdf.cell(x_num - x_pos - 1, h, pdf.t(voce["pos"]), align="R")
        pdf.carattere(dim)
        pdf.set_text_color(110, 110, 110)
        pdf.set_xy(x_num, y)
        pdf.cell(x_nome - x_num, h, voce["num"], align="C")
        pdf.set_text_color(0, 0, 0)
        nome = pdf.t(voce["nome"])
        while pdf.get_string_width(nome) > x0 - x_nome - 2 and len(nome) > 3:
            nome = nome[:-2] + ("…" if pdf.unicode else ".")
        pdf.set_xy(x_nome, y)
        pdf.cell(x0 - x_nome - 1, h, nome)
        # barra e valore in fondo
        x_val = x_di(voce["valore"])
        pdf.set_fill_color(*BLU)
        pdf.rect(min(x_val, x_zero), y + h * 0.15, max(0.3, abs(x_val - x_zero)), h * 0.7, style="F")
        pdf.carattere(dim, True)
        if voce["valore"] >= 0:
            pdf.set_xy(x_val + 1, y)
            pdf.cell(12, h, str(voce["valore"]))
        else:
            pdf.set_xy(x_val - 13, y)
            pdf.cell(12, h, str(voce["valore"]), align="R")
    pdf.set_draw_color(120, 120, 120)
    pdf.line(x_zero, y0, x_zero, y_ultima)
    if con_linea:
        y = y_riga(linea_dopo + 1) - stacco / 2   # a metà dello spazio
        pdf.set_draw_color(220, 38, 38)
        pdf.set_line_width(0.5)
        pdf.line(pdf.l_margin, y, 210 - pdf.r_margin, y)
        pdf.set_line_width(0.2)
    pdf.set_draw_color(0, 0, 0)


BLU = (59, 130, 246)
PER_PAGINA = 50   # righe al massimo in una pagina


def _pagina_classifica(pdf: _PDF, comp: Competition):
    nota = f"Calcolata alle {formato.ora_locale(comp.final_computed_at)}."
    if comp.num_qualified:
        nota += f" La linea rossa separa le prime {comp.num_qualified} squadre, qualificate."
    in_gara = [t for t in comp.final_ranking if not t["is_guest"]]
    ospiti = [t for t in comp.final_ranking if t["is_guest"]]
    voci = [{"valore": t["total"], "pos": f"{pos}°", "num": f"{t['number']:02d}", "nome": t["name"]}
            for pos, t in enumerate(in_gara, start=1)]
    if ospiti:
        nota += " In fondo, dopo uno spazio, le squadre ospiti (fuori classifica)."
        voci.append(None)  # spazio tra la classifica e gli ospiti
        voci += [{"valore": t["total"], "pos": "osp.", "num": f"{t['number']:02d}", "nome": t["name"]}
                 for t in ospiti]
    for inizio in range(0, max(1, len(voci)), PER_PAGINA):
        pdf.add_page(orientation="P")
        pdf.intestazione("Classifica finale" + (" (continua)" if inizio else ""), nota)
        # linea rossa sotto l'ultima qualificata, come nel display
        linea = comp.num_qualified - 1 - inizio if comp.num_qualified else None
        _barre(pdf, voci[inizio:inizio + PER_PAGINA], linea)


def _pagina_valori(pdf: _PDF, comp: Competition, prob_states):
    answers = {p.id: p.answer for p in comp.problems}
    voci = [{"valore": ps.value, "pos": "", "num": f"{ps.number:02d}",
             "nome": f"{ps.name} ({answers.get(ps.problem_id, '')})"}
            for ps in sorted(prob_states.values(), key=lambda p: p.number)]
    for inizio in range(0, max(1, len(voci)), PER_PAGINA):
        pdf.add_page(orientation="P")
        pdf.intestazione("Valori dei problemi" + (" (continua)" if inizio else ""),
                         "Valore di ogni problema alla fine della gara; tra parentesi la risposta.")
        _barre(pdf, voci[inizio:inizio + PER_PAGINA])


def _pagine_stato(pdf: _PDF, comp: Competition, prob_states, team_scores):
    probs = sorted(prob_states.values(), key=lambda p: p.number)
    teams = sorted(team_scores.values(), key=lambda t: t.number)
    larghezza = 297 - 24
    # La colonna "Bonus" (e la sua spiegazione) c'è solo se qualcuno ha un bonus di completamento
    # o se l'Admin ha assegnato bonus o penalizzazioni.
    con_admin = bool(comp.penalties)
    con_full = any(t.full_bonus_earned for t in teams)
    w_tot = 15
    w_bonus = 15 if (con_admin or con_full) else 0
    # Celle tra 5 e 14 mm; con pochi problemi lo spazio avanzato va alla colonna dei nomi.
    w_cella = max(5.0, min(14.0, (larghezza - 58 - w_tot - w_bonus) / max(1, len(probs))))
    w_nome = max(58.0, larghezza - w_tot - w_bonus - w_cella * len(probs))
    h = 6.0
    dim = max(5.5, min(9.0, w_cella * 0.75))
    righe_per_pagina = int((210 - 12 - 12 - 36 - 2 * h - 8) // h)  # titolo, legenda su due righe, testata, piede

    def cella(testo, w, grassetto=False, fondo=None):
        """Cella centrata; il testo si rimpicciolisce se non ci sta."""
        d = dim
        pdf.carattere(d, grassetto)
        while pdf.get_string_width(testo) > w - 0.8 and d > 3.5:
            d -= 0.25
            pdf.carattere(d, grassetto)
        if fondo:
            pdf.set_fill_color(*fondo)
        pdf.cell(w, h, testo, border=1, align="C", fill=bool(fondo))
        pdf.carattere(dim, grassetto)

    def testata():
        pdf.carattere(dim, True)
        pdf.set_fill_color(*INTESTAZIONE)
        pdf.cell(w_nome, h, pdf.t("Squadra"), border=1, fill=True)
        for ps in probs:
            cella(f"{ps.number:02d}", w_cella, True, INTESTAZIONE)
        if w_bonus:
            cella("Bonus", w_bonus, True, INTESTAZIONE)
        cella(pdf.t("Totale"), w_tot, True, INTESTAZIONE)
        pdf.ln(h)
        pdf.carattere(dim)
        pdf.cell(w_nome, h, pdf.t("Valore"), border=1)
        for ps in probs:
            cella(str(ps.value), w_cella)
        if w_bonus:
            pdf.cell(w_bonus, h, "", border=1)
        pdf.cell(w_tot, h, "", border=1)
        pdf.ln(h)

    totale = f"Totale = punteggio iniziale ({comp.effective_starting_score}) + caselle"
    if con_full and con_admin:
        totale += " + bonus (completamento di tutti i problemi e bonus o penalizzazioni dell'Admin)"
    elif con_full:
        totale += " + bonus per aver risolto tutti i problemi"
    elif con_admin:
        totale += " + bonus o penalizzazioni dell'Admin"
    for inizio in range(0, max(1, len(teams)), righe_per_pagina):
        pdf.add_page(orientation="L")
        pdf.intestazione("Stato della gara",
                         "Verde: risolto · rosso: solo risposte sbagliate (tra parentesi gli errori) · "
                         "bordo giallo: jolly · in arancione: squadre ospiti. " + totale + ".")
        testata()
        for t in teams[inizio:inizio + righe_per_pagina]:
            pdf.carattere(dim, True)
            if t.is_guest:
                pdf.set_text_color(194, 65, 12)
            nome = f"{t.number:02d}  {t.name}"
            while pdf.get_string_width(pdf.t(nome)) > w_nome - 2 and len(nome) > 4:
                nome = nome[:-2] + "…" if pdf.unicode else nome[:-2]
            pdf.cell(w_nome, h, pdf.t(nome), border=1)
            pdf.set_text_color(0, 0, 0)
            pdf.carattere(dim)
            for ps in probs:
                risolto = t.problem_solved.get(ps.problem_id)
                errori = t.problem_errors.get(ps.problem_id, 0)
                testo, fondo = "", None
                if risolto:
                    testo, fondo = f"{int(t.problem_contributions.get(ps.problem_id, 0)):+d}", VERDE
                elif errori:
                    testo, fondo = f"{int(t.problem_contributions.get(ps.problem_id, 0)):+d} ({errori})", ROSSO
                x, y = pdf.get_x(), pdf.get_y()
                cella(testo, w_cella, fondo=fondo)
                if t.jolly_problem_id == ps.problem_id:
                    pdf.set_draw_color(*GIALLO)
                    pdf.set_line_width(0.7)
                    pdf.rect(x + 0.4, y + 0.4, w_cella - 0.8, h - 0.8)
                    pdf.set_draw_color(0, 0, 0)
                    pdf.set_line_width(0.2)
            if w_bonus:
                altro = t.full_bonus_earned + t.penalty_total
                cella(f"{altro:+d}" if altro else "", w_bonus)
            cella(str(t.total), w_tot, True)
            pdf.ln(h)
        pdf.carattere(dim, True)
        pdf.cell(w_nome, h, pdf.t(f"Risolutori (n = {comp.n})"), border=1)
        pdf.carattere(dim)
        for ps in probs:
            cella(str(len(ps.solvers)), w_cella)
        if w_bonus:
            pdf.cell(w_bonus, h, "", border=1)
        pdf.cell(w_tot, h, "", border=1)
        pdf.ln(h)


def crea_pdf(comp: Competition) -> bytes:
    """PDF dei risultati. Richiede gara terminata, classifica finale calcolata e ancora aggiornata,
    e tutte le relazioni caricate (load_comp_full)."""
    prob_states, team_scores = compute_state(comp)
    _verifica_aggiornata(comp, team_scores)
    titolo = comp.name + (f" — {comp.date}" if comp.date else "")
    pdf = _PDF(titolo)
    pdf.set_title(titolo)
    pdf.set_author("Gare di Mate")
    _pagina_classifica(pdf, comp)
    _pagina_valori(pdf, comp, prob_states)
    _pagine_stato(pdf, comp, prob_states, team_scores)
    return bytes(pdf.output())
