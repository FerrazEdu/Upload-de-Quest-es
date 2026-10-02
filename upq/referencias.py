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


def separar_tabelas(texto: str) -> str:
    """Linha em branco antes e depois de toda tabela Markdown (sem ela, o texto colado vira
    linha da tabela ou fica grudado nela)."""
    if not texto:
        return texto
    linhas = texto.split("\n")
    saida = []
    for i, l in enumerate(linhas):
        tab = l.strip().startswith("|")
        ant = saida[-1] if saida else ""
        if tab and ant.strip() and not ant.strip().startswith("|"):
            saida.append("")
        elif not tab and l.strip() and ant.strip().startswith("|"):
            saida.append("")
        saida.append(l)
    return "\n".join(saida)


# ---------------------------------------------------------------- alinhamento centralizado
# A IA marca o que está centralizado no PDF com um bloco
#     ::: centro
#     ...
#     :::
# e o código o converte em HTML (Markdown não centraliza): parágrafo → <p style="text-align:
# center;">, tabela → <table style="margin-left: auto; margin-right: auto;">, figura →
# <p style="text-align: center;"><img src="figura:NOME" alt="...">. O LaTeX fica intacto.
P_CENTRO = '<p style="text-align: center;">'
T_CENTRO = '<table style="margin-left: auto; margin-right: auto;">'
_FIG_SO = re.compile(r"^!\[([^\]]*)\]\((figura:[A-Za-z0-9_]+)\)$")
_MATH = re.compile(r"\$\$[\s\S]+?\$\$|\\\$|\$[^$\n]+?\$")


def _esc_attr(t: str) -> str:
    return t.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")


def inline_html(t: str) -> str:
    """Markdown em linha → HTML (negrito, itálico), sem tocar no LaTeX."""
    guardadas = []

    def guardar(m):
        guardadas.append(m.group(0))
        return f"\x02{len(guardadas) - 1}\x02"
    t = _MATH.sub(guardar, t)
    t = t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t, flags=re.S)
    t = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>", t, flags=re.S)
    return re.sub(r"\x02(\d+)\x02", lambda m: guardadas[int(m.group(1))], t)


def tabela_html(linhas: list[str], centralizada: bool = True) -> str:
    def celulas(l):
        l = l.strip()
        if l.startswith("|"):
            l = l[1:]
        if l.endswith("|") and not l.endswith("\\|"):
            l = l[:-1]
        return [c.strip() for c in re.split(r"(?<!\\)\|", l)]
    cab = celulas(linhas[0])
    sep = celulas(linhas[1]) if len(linhas) > 1 and re.fullmatch(r"\s*\|?[\s:\-|]+\|?\s*", linhas[1]) else None
    corpo = linhas[2:] if sep else linhas[1:]
    alinh = []
    for c in (sep or []):
        alinh.append("center" if c.startswith(":") and c.endswith(":") else "right" if c.endswith(":") else
                     "left" if c.startswith(":") else None)
    # texto das células centralizado, como nas tabelas das listas (salvo alinhamento explícito)
    st = lambda i: f' style="text-align: {alinh[i] if i < len(alinh) and alinh[i] else "center"};"'
    html = (T_CENTRO if centralizada else "<table>") + "<thead><tr>"
    html += "".join(f"<th{st(i)}>{inline_html(c)}</th>" for i, c in enumerate(cab)) + "</tr></thead><tbody>"
    for l in corpo:
        html += "<tr>" + "".join(f"<td{st(i)}>{inline_html(c)}</td>" for i, c in enumerate(celulas(l))) + "</tr>"
    return html + "</tbody></table>"


_FIGS = re.compile(r"!\[([^\]]*)\]\((figura:[A-Za-z0-9_]+)\)")
_SO_FIGS = re.compile(r"^\s*(?:!\[[^\]]*\]\(figura:[A-Za-z0-9_]+\)\s*)+$")


def _imgs_centralizadas(bloco: str) -> str:
    imgs = " ".join(f'<img src="{m.group(2)}" alt="{_esc_attr(m.group(1))}">' for m in _FIGS.finditer(bloco))
    return f"{P_CENTRO}{imgs}</p>"


def _bloco_centralizado(bloco: str) -> str:
    linhas = [l for l in bloco.split("\n") if l.strip()]
    if not linhas:
        return ""
    if all(l.strip().startswith("|") for l in linhas):
        return tabela_html(linhas)
    if _SO_FIGS.match(bloco):
        return _imgs_centralizadas(bloco)
    if linhas[0].lstrip().startswith("<"):   # já é HTML
        return "\n".join(linhas)
    return P_CENTRO + "<br>".join(inline_html(l.strip()) for l in linhas) + "</p>"


def _blocos(texto: str) -> list[str]:
    """Parágrafos, com tabela e texto colados separados em blocos próprios."""
    blocos = []
    for parte in re.split(r"\n\s*\n", texto.strip("\n")):
        atual = []
        for l in parte.split("\n"):
            if atual and atual[-1].strip().startswith("|") != l.strip().startswith("|"):
                blocos.append("\n".join(atual))
                atual = []
            atual.append(l)
        if atual:
            blocos.append("\n".join(atual))
    return [b for b in blocos if b.strip()]


def centralizar(texto: str, figuras_centralizadas: set[str] = frozenset()) -> str:
    """Converte os blocos ::: centro em HTML centralizado. Fora deles: toda tabela sai
    centralizada (no modelo das listas as tabelas são centralizadas) e as figuras que estão
    no centro da questão no PDF (sozinhas ou lado a lado) ficam centralizadas."""
    if not texto:
        return texto
    texto = re.sub(r"(?m)^[ \t]*:::[ \t]*centro[ \t]*\n([\s\S]*?)\n[ \t]*:::[ \t]*$",
                   lambda m: "\n\n" + "\n\n".join(_bloco_centralizado(b) for b in _blocos(m.group(1))) + "\n\n", texto)
    saida = []
    for b in _blocos(texto):
        linhas = [l for l in b.split("\n") if l.strip()]
        if all(l.strip().startswith("|") for l in linhas):
            b = tabela_html(linhas)
        elif _SO_FIGS.match(b) and all(m.group(2).removeprefix("figura:") in figuras_centralizadas for m in _FIGS.finditer(b)):
            b = _imgs_centralizadas(b)
        saida.append(b)
    return "\n\n".join(saida)


def normalizar(texto: str, figuras_centralizadas: set[str] = frozenset()) -> str:
    """Formatação aplicada pelo código a enunciados e alternativas."""
    return separar_tabelas(centralizar(formatar(texto), figuras_centralizadas))
