"""Formato padrão das referências (créditos de figura e fontes de texto): parágrafo próprio,
alinhado à direita e em subscrito. Aplicado pelo código, não pela IA, para sair sempre igual.

    Fonte: UNICAMP, 2014.  →  <p style="text-align: right;"><sub>Fonte: UNICAMP, 2014.</sub></p>
"""

import re

ABRE = '<p style="text-align: right;"><sub>'
FECHA = "</sub></p>"
_INICIO = re.compile(r"^\(?\s*(fontes?\s*(\([^)]*\)\s*)?:|dispon[ií]vel em|adaptad[oa] de|texto adaptado|extra[ií]d[oa] d[eo]|"
                     r"retirad[oa] d[eo]|imagem dispon[ií]vel|foto:|ilustra[cç][aã]o:|cr[eé]dito)", re.I)
_MEIO = re.compile(r"acesso em\s*:|dispon[ií]vel em\s*:", re.I)


def _limpar(p: str) -> str:
    t = p.strip()
    while True:   # tira o itálico/negrito que envolve o parágrafo inteiro
        m = re.fullmatch(r"(\*{1,3}|_{1,3})(.+?)\1", t, re.S)
        if not m:
            break
        t = m.group(2).strip()
    t = re.sub(r"<(https?://[^>\s]+)>", r"\1", t)            # autolink do Markdown
    t = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r"\1", t)
    return t.replace("<", "&lt;").replace(">", "&gt;")


def e_referencia(p: str) -> bool:
    t = p.strip().strip("*_").strip()
    if not t or t.startswith(("<p", "!", "|", "$$")) or "$" in t or "\n\n" in t:
        return False
    return bool(_INICIO.match(t)) or (len(t) < 500 and bool(_MEIO.search(t)))


def formatar(texto: str) -> str:
    """Põe cada parágrafo de referência no formato padrão (idempotente)."""
    if not texto:
        return texto
    partes = re.split(r"(\n\s*\n)", texto)
    for i in range(0, len(partes), 2):
        p = partes[i]
        if e_referencia(p):
            lead = p[: len(p) - len(p.lstrip())]
            partes[i] = lead + ABRE + _limpar(p) + FECHA
    return "".join(partes)
