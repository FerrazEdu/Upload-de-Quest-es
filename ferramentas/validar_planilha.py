#!/usr/bin/env python3
"""Valida uma planilha de questões contra docs/ESPECIFICACAO_PLANILHA.md.

Uso:
    python ferramentas/validar_planilha.py LISTA.xlsx            # só valida
    python ferramentas/validar_planilha.py LISTA.csv --preview   # valida e gera LISTA.preview.html

O preview mostra cada questão renderizada (LaTeX via MathJax, negrito, tabelas,
marcadores de imagem) para revisão visual antes do envio ao banco.
"""

import argparse
import csv
import html
import re
import sys
from pathlib import Path

COLUNAS = [
    "codigo_lista", "numero", "pagina", "tipo", "disciplina", "topico", "assunto",
    "dificuldade", "ano", "fonte", "enunciado", "alt_a", "alt_b", "alt_c", "alt_d",
    "alt_e", "gabarito", "resolucao", "revisar", "observacoes",
]
OBRIGATORIAS = [
    "codigo_lista", "numero", "pagina", "tipo", "disciplina", "topico", "assunto",
    "dificuldade", "enunciado", "gabarito",
]
ALTERNATIVAS = ["alt_a", "alt_b", "alt_c", "alt_d", "alt_e"]
CAMPOS_RICOS = ["enunciado", *ALTERNATIVAS, "gabarito", "resolucao"]
TIPOS = {"objetiva", "discursiva", "verdadeiro_falso"}
DIFICULDADES = {"facil", "media", "dificil"}
TAGS_PERMITIDAS = {"br", "u", "sup", "sub", "table", "tr", "th", "td"}

RE_IMG = re.compile(r"\[\[IMG:p(\d+):(\d+)(?:\|([^\]]*))?\]\]")
RE_IMG_SOLTO = re.compile(r"\[\[IMG[^\]]*\]\]")
RE_TAG = re.compile(r"</?\s*([a-zA-Z][a-zA-Z0-9]*)[^>]*>")
RE_UNICODE_MAT = re.compile(r"[²³¹⁰⁴-⁹₀-₉√≤≥≠±×÷∞∫∑πΔ°]")


def ler_planilha(caminho: Path) -> list[dict]:
    if caminho.suffix.lower() == ".xlsx":
        try:
            import openpyxl
        except ImportError:
            sys.exit("Instale o openpyxl: pip install openpyxl")
        aba = openpyxl.load_workbook(caminho, read_only=True, data_only=True).active
        linhas = [["" if c is None else str(c) for c in l] for l in aba.iter_rows(values_only=True)]
    else:
        with open(caminho, encoding="utf-8-sig", newline="") as f:
            linhas = list(csv.reader(f, delimiter=";"))
    if not linhas:
        return []
    cabecalho = [c.strip().lower() for c in linhas[0]]
    return [
        {cabecalho[i]: (v or "").strip() for i, v in enumerate(l) if i < len(cabecalho)}
        for l in linhas[1:]
        if any((v or "").strip() for v in l)
    ]


def sem_formulas(texto: str) -> str:
    """Remove o conteúdo das fórmulas, para checar o texto ao redor."""
    texto = texto.replace(r"\$", "")
    return re.sub(r"\$\$.*?\$\$|\$.*?\$", " ", texto, flags=re.S)


def checar_texto(campo: str, texto: str, erros: list, avisos: list) -> list[tuple[int, int]]:
    if "\n" in texto or "\r" in texto:
        erros.append(f"{campo}: tem quebra de linha real (use <br>)")
    if texto.replace(r"\$", "").count("$") % 2:
        erros.append(f"{campo}: quantidade ímpar de '$' (fórmula aberta ou R$ sem escape '\\$')")
    if re.search(r"R\$(?!\$)", texto.replace(r"\$", "")):
        erros.append(f"{campo}: 'R$' sem escape (escreva R\\$)")
    fora = sem_formulas(texto)
    for tag in RE_TAG.findall(fora):
        if tag.lower() not in TAGS_PERMITIDAS:
            erros.append(f"{campo}: tag HTML não permitida <{tag}>")
    if RE_UNICODE_MAT.search(fora):
        avisos.append(f"{campo}: símbolo matemático em Unicode fora de LaTeX "
                      f"({', '.join(sorted(set(RE_UNICODE_MAT.findall(fora))))})")
    imagens = [(int(p), int(n)) for p, n, _ in RE_IMG.findall(texto)]
    if len(RE_IMG_SOLTO.findall(texto)) != len(imagens):
        erros.append(f"{campo}: marcador de imagem mal formado (use [[IMG:p4:1|descrição]])")
    return imagens


def validar(linhas: list[dict]) -> tuple[list[str], list[str]]:
    problemas, alertas = [], []
    if not linhas:
        return ["planilha vazia"], []
    faltando = [c for c in COLUNAS if c not in linhas[0]]
    if faltando:
        problemas.append(f"colunas ausentes no cabeçalho: {', '.join(faltando)}")
    numeros = set()
    for i, q in enumerate(linhas, start=2):
        rotulo = f"linha {i} (questão {q.get('numero') or '?'})"
        erros, avisos = [], []
        for c in OBRIGATORIAS:
            if not q.get(c) and not (c == "gabarito" and q.get("revisar", "").upper() == "SIM"):
                erros.append(f"{c}: vazio")
        num = q.get("numero", "")
        if num and not num.isdigit():
            erros.append("numero: não é inteiro")
        elif num in numeros:
            erros.append("numero: repetido")
        numeros.add(num)
        if q.get("pagina") and not q["pagina"].isdigit():
            erros.append("pagina: não é inteiro")
        if q.get("ano") and not re.fullmatch(r"\d{4}", q["ano"]):
            erros.append("ano: deve ter 4 dígitos")
        tipo = q.get("tipo", "")
        if tipo and tipo not in TIPOS:
            erros.append(f"tipo: '{tipo}' inválido (use {', '.join(sorted(TIPOS))})")
        if q.get("dificuldade") and q["dificuldade"] not in DIFICULDADES:
            erros.append(f"dificuldade: '{q['dificuldade']}' inválida")
        if tipo == "objetiva":
            preenchidas = [a for a in ALTERNATIVAS if q.get(a)]
            if len(preenchidas) < 2:
                erros.append("objetiva com menos de 2 alternativas")
            if preenchidas != ALTERNATIVAS[: len(preenchidas)]:
                erros.append("alternativas fora de ordem (há lacuna entre elas)")
            gab = q.get("gabarito", "")
            if gab and gab not in "ABCDE"[: len(preenchidas)]:
                erros.append(f"gabarito '{gab}' não corresponde a uma alternativa preenchida")
            for a in preenchidas:
                if re.match(r"^\(?[a-eA-E][\)\.]\s", q[a]):
                    avisos.append(f"{a}: parece começar com a letra da alternativa")
        if tipo == "verdadeiro_falso" and q.get("gabarito") and not re.fullmatch(r"[VF]+", q["gabarito"]):
            erros.append("gabarito de V/F deve ser uma sequência de V e F")
        if re.match(r"^\s*\d+\s*[\.\)\-]", q.get("enunciado", "")):
            avisos.append("enunciado: parece começar com o número da questão")
        for c in CAMPOS_RICOS:
            if q.get(c):
                checar_texto(c, q[c], erros, avisos)
        if q.get("revisar", "").upper() == "SIM":
            avisos.append(f"marcada para revisão: {q.get('observacoes') or '(sem observação)'}")
        problemas += [f"{rotulo}: {e}" for e in erros]
        alertas += [f"{rotulo}: {a}" for a in avisos]
    return problemas, alertas


# ---------------------------------------------------------------- preview

def para_html(texto: str) -> str:
    """Converte a marcação da especificação para HTML, preservando o LaTeX para o MathJax."""
    formulas = []

    def guardar(m):
        formulas.append(m.group(0))
        return f"\x00{len(formulas) - 1}\x00"

    t = texto.replace(r"\$", "\x01")
    t = re.sub(r"\$\$.*?\$\$|\$.*?\$", guardar, t, flags=re.S)
    t = html.escape(t, quote=False)
    for tag in TAGS_PERMITIDAS:
        t = re.sub(rf"&lt;(/?){tag}&gt;", rf"<\1{tag}>", t)
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"\*(.+?)\*", r"<em>\1</em>", t)
    t = RE_IMG.sub(
        lambda m: f'<span class="img">🖼 imagem p.{m[1]} nº {m[2]}'
                  f'{": " + m[3] if m[3] else ""}</span>', t)
    t = re.sub(r"\x00(\d+)\x00", lambda m: html.escape(formulas[int(m[1])], quote=False), t)
    return t.replace("\x01", "\\$")  # MathJax exibe \$ como cifrão literal


def gerar_preview(linhas: list[dict], problemas: list[str], alertas: list[str], destino: Path):
    def marcas(q):
        prefixo = f"(questão {q.get('numero') or '?'})"
        return [p for p in problemas + alertas if prefixo in p]

    cartoes = []
    for q in linhas:
        alts = ""
        if q.get("tipo") == "objetiva":
            itens = "".join(
                f'<li class="{"certa" if q.get("gabarito") == a[-1].upper() else ""}">'
                f'<b>{a[-1].upper()})</b> {para_html(q[a])}</li>'
                for a in ALTERNATIVAS if q.get(a))
            alts = f"<ol class='alts'>{itens}</ol>"
        else:
            alts = f"<p><b>Gabarito:</b> {para_html(q.get('gabarito', ''))}</p>"
        avisos = "".join(f"<li>{html.escape(m.split(': ', 1)[1])}</li>" for m in marcas(q))
        meta = " · ".join(html.escape(q.get(c, "")) for c in
                          ("topico", "assunto", "dificuldade", "fonte", "ano") if q.get(c))
        cartoes.append(f"""
<section class="q">
  <header><span class="n">Questão {html.escape(q.get('numero', '?'))}</span>
  <span class="meta">p.{html.escape(q.get('pagina', '?'))} · {meta}</span></header>
  {f'<ul class="avisos ignorar-tex">{avisos}</ul>' if avisos else ''}
  <div class="enun">{para_html(q.get('enunciado', ''))}</div>
  {alts}
  {f'<details><summary>Resolução</summary>{para_html(q["resolucao"])}</details>' if q.get('resolucao') else ''}
</section>""")
    destino.write_text(f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Preview das questões</title>
<script>MathJax={{tex:{{inlineMath:[['$','$']],displayMath:[['$$','$$']]}},options:{{ignoreHtmlClass:'ignorar-tex'}}}};</script>
<script src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-chtml.js" async></script>
<style>
body{{font-family:system-ui,sans-serif;max-width:860px;margin:0 auto;padding:16px;background:#f6f6f4;color:#222}}
.q{{background:#fff;border:1px solid #ddd;border-radius:8px;padding:16px;margin:14px 0}}
header{{display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap;margin-bottom:8px}}
.n{{font-weight:700}} .meta{{color:#777;font-size:.85em}}
.alts{{list-style:none;padding:0}} .alts li{{padding:4px 8px;border-radius:4px}}
.certa{{background:#e3f5e3}} .img{{display:inline-block;border:1px dashed #999;padding:6px 10px;margin:4px 0;color:#555;background:#fafafa}}
.avisos{{background:#fff4e0;border-left:4px solid #e0a020;padding:6px 6px 6px 28px;font-size:.9em}}
table{{border-collapse:collapse;margin:6px 0}} td,th{{border:1px solid #bbb;padding:4px 8px}}
</style></head><body>
<h1>{len(linhas)} questões — {len(problemas)} erro(s), {len(alertas)} aviso(s)</h1>
{''.join(cartoes)}
</body></html>""", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("planilha", type=Path)
    ap.add_argument("--preview", action="store_true", help="gera um HTML para revisão visual")
    args = ap.parse_args()

    linhas = ler_planilha(args.planilha)
    problemas, alertas = validar(linhas)
    print(f"{args.planilha.name}: {len(linhas)} questões")
    for p in problemas:
        print(f"  ERRO  {p}")
    for a in alertas:
        print(f"  AVISO {a}")
    if args.preview:
        destino = args.planilha.with_suffix(".preview.html")
        gerar_preview(linhas, problemas, alertas, destino)
        print(f"preview: {destino}")
    print("OK" if not problemas else f"{len(problemas)} erro(s) — corrija antes de importar")
    sys.exit(1 if problemas else 0)


if __name__ == "__main__":
    main()
