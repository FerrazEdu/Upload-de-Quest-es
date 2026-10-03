"""Recorta uma lista em PDF (modelo Plataforma Assaad) em questões e figuras.

A camada de texto dessas listas é selecionável, mas não é confiável como fonte
final: com as fontes Type3 do PDF, símbolos trocam de caractere (π vira "À",
≈ vira "H"), expoentes e índices perdem a posição (10⁸ vira "108", N₁ vira
"N1") e palavras se partem. A delimitação usa só a GEOMETRIA da página:

  - cada questão começa numa barra "Questão NN";
  - a questão vai até a próxima barra da mesma coluna (ou o fim da coluna);
  - figuras são as imagens grandes dentro da região da questão.

O texto da região entra no manifesto como `texto_pdf`: serve de apoio para a IA
(ordem das palavras, nomes próprios) e para conferir números na validação.

Saída (pasta --saida):
  manifesto.json            lista, etapas e, por questão: página, região, texto_pdf, figuras
  questoes/QNN.png          recorte da questão inteira (entrada para a IA e para revisão)
  figuras/QNN_figK.png      cada figura em alta resolução, como aparece no PDF
  paginas/pN.png            páginas sem questões (capa, sumário, gabarito)

Uso:
    python -m upq.segmentar LISTA.pdf --saida saida/LISTA
"""

import argparse
import hashlib
import json
import re
from pathlib import Path

import pymupdf

ETAPAS = ["Fixação", "Treinamento", "Aprofundamento", "Desafios"]
RE_QUESTAO = re.compile(r"^\s*Quest[aã]o\s*(\d[\d ]*)")
MARGEM_TOPO = 30          # abaixo da faixa de cabeçalho da página
FIGURA_MIN = 30           # lado mínimo (pt) para uma imagem contar como figura (alternativas em imagem são pequenas)
DPI_QUESTAO = 200
DPI_FIGURA = 300


def linhas(pagina):
    for bloco in pagina.get_text("dict")["blocks"]:
        for linha in bloco.get("lines", []):
            yield "".join(s["text"] for s in linha["spans"]), pymupdf.Rect(linha["bbox"])


def duas_colunas(pagina):
    """Faixas x do modelo de 2 colunas, separadas por um fio vertical (ou o meio da página)."""
    meio = pagina.rect.width / 2
    for im in pagina.get_image_info():
        r = pymupdf.Rect(im["bbox"])
        if r.width < 3 and r.height > pagina.rect.height * 0.6:
            meio = (r.x0 + r.x1) / 2
            break
    return [(0, meio), (meio, pagina.rect.width)]


def limites_colunas(pagina):
    """Palpite do modelo da página: uma coluna (questões na largura toda: várias linhas de texto
    atravessam o meio) ou duas. O recorte confere se algo ficou de fora e tenta o outro."""
    meio = pagina.rect.width / 2
    cruzam = sum(1 for texto, r in linhas(pagina)
                 if len(texto.strip()) >= 8 and r.x0 < meio - 15 and r.x1 > meio + 15)
    return [(0, pagina.rect.width)] if cruzam >= 3 else duas_colunas(pagina)


def fim_da_barra(pagina, r) -> float | None:
    """Até onde vai a barra colorida da "Questão NN" (retângulo preenchido atrás do texto)."""
    y = (r.y0 + r.y1) / 2
    fins = [d["rect"].x1 for d in pagina.get_drawings()
            if d.get("fill") and d["rect"].y0 - 1 <= y <= d["rect"].y1 + 1 and d["rect"].x0 - 1 <= r.x0 + 2 <= d["rect"].x1
            and d["rect"].height < 40 and max(d["fill"]) - min(d["fill"]) > 0.1]
    return max(fins) if fins else None


def cabecalhos_da_pagina(pagina, colunas):
    saida = []
    for texto, r in linhas(pagina):
        m = RE_QUESTAO.match(texto)
        if m and r.y0 > MARGEM_TOPO:
            col = 0 if len(colunas) == 1 or r.x0 < colunas[0][1] else 1
            saida.append({"col": col, "y": r.y0, "r": r, "numero": int(m.group(1).replace(" ", ""))})
    return saida


def tem_conteudo(pagina, regiao, figuras_pagina) -> bool:
    for texto, r in linhas(pagina):
        t = texto.strip()
        if len(t) >= 2 and t not in ETAPAS and regiao.contains(pymupdf.Point((r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2)):
            return True
    return any(regiao.contains(pymupdf.Point((f.x0 + f.x1) / 2, (f.y0 + f.y1) / 2)) for f in figuras_pagina)


def partes_da_pagina(pagina, colunas, fundo, figuras_pagina):
    """Partes em ordem de leitura: "nova" (começa numa barra Questão NN) ou "continuacao" (topo
    de coluna antes da 1ª barra, ou coluna sem barra: o resto da questão anterior)."""
    cabs = cabecalhos_da_pagina(pagina, colunas)
    partes = []
    for col, (x0, x1) in enumerate(colunas):
        na_coluna = sorted((c for c in cabs if c["col"] == col), key=lambda c: c["y"])
        topo = pymupdf.Rect(x0 + 2, MARGEM_TOPO, x1 - 2, (na_coluna[0]["y"] if na_coluna else fundo) - 2)
        if topo.height > 6 and tem_conteudo(pagina, topo, figuras_pagina):
            partes.append({"tipo": "continuacao", "col": col, "regiao": topo})
        for i, c in enumerate(na_coluna):
            y_fim = na_coluna[i + 1]["y"] - 2 if i + 1 < len(na_coluna) else fundo - 2
            partes.append({"tipo": "nova", "col": col, "numero": c["numero"], "regiao": pymupdf.Rect(x0 + 2, c["y"] - 2, x1 - 2, y_fim)})
    return partes, cabs


def fora_do_recorte(pagina, partes, fundo, figuras_pagina) -> list[tuple[pymupdf.Rect, str]]:
    """Texto ou imagem da página fora de todas as partes (a barra Questão NN e faixas de etapa
    não contam)."""
    dentro = lambda r: any(r.x0 >= pt["regiao"].x0 - 6 and r.x1 <= pt["regiao"].x1 + max(8, 0.08 * pt["regiao"].width)
                           and pt["regiao"].y0 <= (r.y0 + r.y1) / 2 <= pt["regiao"].y1 + 2 for pt in partes)
    saida = []
    for texto, r in linhas(pagina):
        t = texto.strip()
        if len(t) < 2 or t in ETAPAS or RE_QUESTAO.match(texto) or not (MARGEM_TOPO <= r.y0 < fundo - 2):
            continue
        if not dentro(r):
            saida.append((r, t[:80]))
    saida += [(f, "[imagem]") for f in figuras_pagina if MARGEM_TOPO <= f.y0 < fundo and not dentro(f)]
    return saida


def fim_da_coluna(pagina):
    """y do fio do rodapé (linha horizontal longa perto do fim da página)."""
    candidatos = [
        pymupdf.Rect(im["bbox"]).y0
        for im in pagina.get_image_info()
        if pymupdf.Rect(im["bbox"]).height < 4
        and pymupdf.Rect(im["bbox"]).width > pagina.rect.width * 0.8
        and pymupdf.Rect(im["bbox"]).y0 > pagina.rect.height * 0.8
    ]
    # sem o fio: o texto do rodapé ("Plataforma Assaad"), como no recorte do navegador
    if not candidatos:
        candidatos = [r.y0 - 8 for t, r in linhas(pagina) if r.y0 > pagina.rect.height * 0.85 and re.search("Plataforma|Assaad", t)]
    return min(candidatos) if candidatos else pagina.rect.height - 30


NEGRITO = re.compile(r"bold|black|heavy|semibold|demibold|extrabold|,b$", re.I)


def mancha(pagina, regiao, com_cabecalho: bool = True) -> tuple[float, float]:
    """Extensão horizontal do texto da questão (sem a barra do cabeçalho)."""
    rs = [pymupdf.Rect(sp["bbox"]) for b in pagina.get_text("dict", clip=regiao)["blocks"]
          for l in b.get("lines", []) for sp in l["spans"] if sp["text"].strip()]
    rs = [r for r in rs if regiao.contains(pymupdf.Point((r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2))]
    if len(rs) < 2:
        return regiao.x0, regiao.x1
    topo = min(r.y0 for r in rs)
    corpo = ([r for r in rs if r.y0 > topo + 3] or rs) if com_cabecalho else rs
    return min(r.x0 for r in corpo), max(r.x1 for r in corpo)


def figuras_centralizadas(figs, regiao, esq: float, dir_: float) -> set[int]:
    """Índices das figuras centralizadas no PDF. Figuras lado a lado contam como um grupo."""
    largura = max(1.0, dir_ - esq)
    faixas = []
    for k, f in enumerate(figs):
        if faixas and f.y0 < faixas[-1]["y1"] - 0.5 * min(f.height, faixas[-1]["y1"] - faixas[-1]["y0"]):
            u = faixas[-1]
            u["k"].append(k); u["x0"] = min(u["x0"], f.x0); u["x1"] = max(u["x1"], f.x1); u["y1"] = max(u["y1"], f.y1)
        else:
            faixas.append({"k": [k], "x0": f.x0, "x1": f.x1, "y0": f.y0, "y1": f.y1})
    saida = set()
    for u in faixas:
        meio = (u["x0"] + u["x1"]) / 2
        # figura quase da largura do texto também conta como centralizada (é como aparece)
        if (u["x1"] - u["x0"] >= 0.85 * largura
                or abs(meio - (esq + dir_) / 2) < 0.05 * largura or abs(meio - (regiao.x0 + regiao.x1) / 2) < 0.05 * largura):
            saida.update(u["k"])
    return saida


def texto_marcado(pagina, regiao, com_cabecalho: bool = True) -> str:
    """Texto da questão com a formatação do PDF: trechos em **negrito** (fonte negrito) e
    "[centralizado] " nas linhas cujo centro coincide com o centro da questão (mesma regra
    de upq/web/recorte.js). A 1ª linha (barra "Questão NN  BANCA ANO") sai sem marcas."""
    pedacos = []
    for bloco in pagina.get_text("dict", clip=regiao)["blocks"]:
        for linha in bloco.get("lines", []):
            for sp in linha["spans"]:
                if not sp["text"].strip():
                    continue
                r = pymupdf.Rect(sp["bbox"])
                if not regiao.contains(pymupdf.Point((r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2)):
                    continue
                pedacos.append({"t": sp["text"], "r": r, "base": sp["origin"][1],
                                "negrito": bool(sp["flags"] & 16) or bool(NEGRITO.search(sp["font"]))})
    pedacos.sort(key=lambda p: (p["base"], p["r"].x0))
    linhas_ = []
    for p in pedacos:
        if linhas_ and abs(linhas_[-1][0]["base"] - p["base"]) < 2.5:
            linhas_[-1].append(p)
        else:
            linhas_.append([p])
    # Referência: a mancha de texto da questão (sem a barra do cabeçalho), não a caixa da coluna.
    corpo = [p for ps in (linhas_[1:] if com_cabecalho else linhas_) for p in ps]
    esq = min((p["r"].x0 for p in corpo), default=regiao.x0)
    dir_ = max((p["r"].x1 for p in corpo), default=regiao.x1)
    largura, centro = max(1.0, dir_ - esq), (esq + dir_) / 2
    saida = []
    for i, ps in enumerate(linhas_):
        ps.sort(key=lambda p: p["r"].x0)
        texto, marcado, fim, runs = "", "", None, []
        for p in ps:
            espaco = (" " if fim is not None and (p["r"].x0 - fim > 1.5 or fim - p["r"].x0 > 1)
                      and not texto.endswith(" ") and not p["t"].startswith(" ") else "")
            texto += espaco + p["t"]
            fim = p["r"].x1
            if runs and runs[-1][1] == p["negrito"]:
                runs[-1][0] += espaco + p["t"]
            else:
                runs.append([espaco + p["t"], p["negrito"]])
        for t, neg in runs:
            if neg and re.search(r"[0-9A-Za-zÀ-ú]", t):
                m = re.match(r"^(\s*)(.*?)(\s*)$", t, re.S)
                marcado += f"{m.group(1)}**{m.group(2)}**{m.group(3)}"
            else:
                marcado += t
        x0, x1 = min(p["r"].x0 for p in ps), max(p["r"].x1 for p in ps)
        centralizada = ((i > 0 or not com_cabecalho) and len(texto.strip()) >= 3 and x1 - x0 < 0.8 * largura
                        and x0 - esq > 0.06 * largura
                        and (abs((x0 + x1) / 2 - centro) < 0.04 * largura
                             or abs((x0 + x1) / 2 - (regiao.x0 + regiao.x1) / 2) < 0.04 * largura))
        saida.append(("[centralizado] " if centralizada else "") + (texto if i == 0 and com_cabecalho else marcado))
    return "\n".join(saida).strip()


def grade_da_tabela(pagina, f):
    """Tabela colada como imagem (print): procura a grade — fios horizontais com a mesma
    largura (faixas pintadas de cabeçalho contam), fios verticais fechando a caixa e miolo das
    células claro. Devolve a caixa da grade (pt) ou None. Igual a gradeDaTabela (recorte.js)."""
    esc = 3
    pix = pagina.get_pixmap(matrix=pymupdf.Matrix(esc, esc), clip=f, alpha=False)
    W, H, n, sm = pix.width, pix.height, pix.n, pix.samples
    if W < 60 or H < 40:
        return None
    cor = lambda x, y: sm[(y * W + x) * n:(y * W + x) * n + 3]
    cantos = sorted((cor(x, y) for x, y in [(2, 2), (W - 3, 2), (2, H - 3), (W - 3, H - 3)]), key=sum, reverse=True)
    fundo = cantos[1]
    tinta = bytearray(W * H)
    for i in range(W * H):
        j = i * n
        tinta[i] = abs(sm[j] - fundo[0]) + abs(sm[j + 1] - fundo[1]) + abs(sm[j + 2] - fundo[2]) > 120

    def linhas_de(n_, m, get, min_run):
        cand = []
        for a in range(n_):
            run = melhor = ini = m_ini = 0
            for b in range(m):
                if get(a, b):
                    if not run:
                        ini = b
                    run += 1
                    if run > melhor:
                        melhor, m_ini = run, ini
                else:
                    run = 0
            if melhor >= min_run:
                cand.append((a, m_ini, m_ini + melhor))
        grupos = []
        for a, b0, b1 in cand:
            if grupos and a - grupos[-1]["a1"] <= 2:
                g = grupos[-1]; g["a1"] = a; g["b0"] = min(g["b0"], b0); g["b1"] = max(g["b1"], b1)
            else:
                grupos.append({"a0": a, "a1": a, "b0": b0, "b1": b1})
        return grupos

    fina = lambda g: g["a1"] - g["a0"] + 1 <= 2 * esc
    hs = linhas_de(H, W, lambda y, x: tinta[y * W + x], round(0.4 * W))
    if len(hs) < 3 or sum(map(fina, hs)) < 2:
        return None
    larga = max((h for h in hs if fina(h)), key=lambda h: h["b1"] - h["b0"])
    grade = [h for h in hs if abs(h["b0"] - larga["b0"]) < 0.04 * W and abs(h["b1"] - larga["b1"]) < 0.04 * W]
    if len(grade) < 3 or sum(map(fina, grade)) < 2:
        return None
    topo, base, esq, dir_ = grade[0]["a0"], grade[-1]["a1"], larga["b0"], larga["b1"]
    finas = [g for g in grade if fina(g)]
    for a, b in zip(finas, finas[1:]):
        ya, yb = a["a1"] + 2, b["a0"] - 2
        if yb - ya < 4:
            continue
        amostra = [tinta[y * W + x] for y in range(ya, yb, 2) for x in range(esq, dir_, 2)]
        if amostra and sum(amostra) / len(amostra) > 0.35 and not any(
                not fina(g) and g["a0"] <= ya + 2 and g["a1"] >= yb - 2 for g in grade):
            return None
    vs = [v for v in linhas_de(W, H, lambda x, y: tinta[y * W + x], round(0.8 * (base - topo)))
          if v["a0"] >= esq - 4 and v["a1"] <= dir_ + 4 and fina(v)]
    if len(vs) < 2 or vs[0]["a0"] - esq > 0.05 * W or dir_ - vs[-1]["a1"] > 0.05 * W:
        return None
    m = 2 * esc
    return pymupdf.Rect(f.x0 + (esq - m) / esc, f.y0 + (topo - m) / esc, f.x0 + (dir_ + m) / esc, f.y0 + (base + m) / esc)


def ordem_de_leitura(figuras: list) -> list:
    """Figuras por faixas horizontais (lado a lado → esquerda para a direita), de cima para baixo."""
    faixas = []
    for f in sorted(figuras, key=lambda f: f.y0):
        if faixas and f.y0 < faixas[-1]["y1"] - 0.5 * min(f.height, faixas[-1]["h"]):
            faixas[-1]["f"].append(f)
            faixas[-1]["y1"] = max(faixas[-1]["y1"], f.y1)
        else:
            faixas.append({"y1": f.y1, "h": f.height, "f": [f]})
    return [f for u in faixas for f in sorted(u["f"], key=lambda f: f.x0)]


def aparar_figura(figura, linhas_texto):
    """A imagem embutida às vezes é maior que a área visível e invade o texto
    vizinho. Corta nas linhas de texto que cruzam a borda de cima ou de baixo;
    rótulos inteiros dentro da figura (ex.: "ponto P") são mantidos."""
    r = pymupdf.Rect(figura)
    for t in linhas_texto:
        if t.x1 < r.x0 or t.x0 > r.x1:
            continue
        # linha só de letras de alternativa ("A   B") ao lado dos desenhos: não corta (igual ao JS)
        if all(len(w) <= 2 for w in getattr(t, "texto", "x x x").split()):
            continue
        if t.y0 < r.y1 < t.y1:        # cruza a borda de baixo
            r.y1 = t.y0 - 1
        elif t.y0 < r.y0 < t.y1:      # cruza a borda de cima
            r.y0 = t.y1 + 1
    # Linha de texto corrido do PDF DENTRO da imagem (print grande escondido por clip ou coberto,
    # barra "Questão NN") não é da figura: a figura fica com o maior trecho sem texto corrido
    # (igual a aparar() em upq/web/recorte.js).
    dentro = sorted((t for t in linhas_texto
                     if t.x0 < r.x1 and t.x1 > r.x0 and t.y0 >= r.y0 - 1 and t.y1 <= r.y1 + 1
                     and (len(getattr(t, "texto", "").split()) >= 5 and t.width >= 0.5 * r.width
                          or RE_QUESTAO.match(getattr(t, "texto", "")))
                     and r.width >= 0.4 * t.width), key=lambda t: t.y0)   # imagem pequena no meio da frase fica
    if dentro:
        cortes = [r.y0] + [v for t in dentro for v in (t.y0 - 1, t.y1 + 1)] + [r.y1]
        trechos = [(cortes[k], cortes[k + 1]) for k in range(0, len(cortes) - 1, 2) if cortes[k + 1] > cortes[k]]
        if trechos:
            r.y0, r.y1 = max(trechos, key=lambda a: a[1] - a[0])
    return r


def etapas_pelo_sumario(doc):
    """Lê 'Fixação ... 03' do sumário → {etapa: página inicial}."""
    for pagina in doc:
        texto = pagina.get_text()
        if "Sumário" not in texto:
            continue
        nomes = [e for e in ETAPAS if e in texto]
        numeros = [int(n) for n in re.findall(r"^\s*(\d{1,3})\s*$", texto, re.M)]
        if nomes and len(numeros) >= len(nomes):
            return dict(zip(nomes, numeros[: len(nomes)]))
    return {}


def gabarito_em_texto(pagina) -> dict[str, str]:
    """Lê o quadro de gabarito quando ele está em texto (em algumas listas é imagem;
    aí volta vazio e a IA lê a página renderizada)."""
    texto = pagina.get_text()
    pares = re.findall(r"^\s*(\d{1,3})\s*\n\s*([A-E])\s*$", texto, re.M)
    return {f"{int(n):02d}": letra for n, letra in pares}


def juntar_recortes(doc, partes) -> "pymupdf.Pixmap":
    """Imagem da questão: as partes (colunas ou páginas) empilhadas, cada uma só até onde há
    conteúdo; uma parte só = o recorte da região."""
    util = []
    for pt in partes:
        pagina, r = doc[pt["pagina"] - 1], pt["regiao"]
        rs = [pymupdf.Rect(b[:4]) for b in pagina.get_text("blocks", clip=r) if b[4].strip()]
        rs += [pymupdf.Rect(im["bbox"]) & r for im in pagina.get_image_info() if r.intersects(pymupdf.Rect(im["bbox"]))]
        if rs:
            r = pymupdf.Rect(r.x0, r.y0 if pt["com_cab"] else max(r.y0, min(x.y0 for x in rs) - 6), r.x1, min(r.y1, max(x.y1 for x in rs) + 8))
        util.append((pagina, r))
    if len(util) == 1:
        return util[0][0].get_pixmap(dpi=DPI_QUESTAO, clip=util[0][1])
    vao = 6
    largura = max(r.width for _, r in util)
    novo = pymupdf.open()
    folha = novo.new_page(width=largura, height=sum(r.height for _, r in util) + vao * (len(util) - 1))
    y = 0
    for i, (pagina, r) in enumerate(util):
        folha.show_pdf_page(pymupdf.Rect(0, y, r.width, y + r.height), pagina.parent, pagina.number, clip=r)
        y += r.height
        if i + 1 < len(util):
            folha.draw_line((0, y + vao / 2), (largura, y + vao / 2), color=(0.8, 0.8, 0.8), width=0.6)
            y += vao
    return folha.get_pixmap(dpi=DPI_QUESTAO)


def segmentar(caminho_pdf: Path, saida: Path) -> dict:
    doc = pymupdf.open(caminho_pdf)
    (saida / "questoes").mkdir(parents=True, exist_ok=True)
    (saida / "figuras").mkdir(exist_ok=True)
    (saida / "paginas").mkdir(exist_ok=True)

    titulo_lista = ""
    questoes = []
    paginas_sem_questao = []

    com_barra = [pn for pn, pg in enumerate(doc, start=1) if cabecalhos_da_pagina(pg, duas_colunas(pg))]
    ultima_com_questao = max(com_barra, default=0)
    aberta, uma_anterior = None, False
    for pn, pagina in enumerate(doc, start=1):
        fundo = fim_da_coluna(pagina)
        linhas_texto = []
        for texto, r in linhas(pagina):
            if texto.strip():
                r = pymupdf.Rect(r)
                r.texto = texto   # aparar_figura usa o texto (linha corrida dentro da imagem)
                linhas_texto.append(r)
            if not titulo_lista and texto.startswith("Lista de Exercícios"):
                titulo_lista = texto.split("|", 1)[-1].strip()
        figuras_pagina = [
            pymupdf.Rect(im["bbox"]) for im in pagina.get_image_info()
            if pymupdf.Rect(im["bbox"]).width >= FIGURA_MIN
            and pymupdf.Rect(im["bbox"]).height >= FIGURA_MIN
            and pymupdf.Rect(im["bbox"]).y0 > MARGEM_TOPO
        ]
        cabs2 = cabecalhos_da_pagina(pagina, duas_colunas(pagina))
        if not cabs2:
            # página sem barra: continuação da questão aberta se tiver texto e não for o gabarito
            conteudo = [t for t, r in linhas(pagina) if MARGEM_TOPO < r.y0 < fundo and len(t.strip()) >= 2 and t.strip() not in ETAPAS]
            continua = (aberta is not None and len(conteudo) >= 3 and not any(re.search("gabarito", t, re.I) for t in conteudo)
                        and not gabarito_em_texto(pagina))
            if not continua:
                paginas_sem_questao.append(pn)
                pagina.get_pixmap(dpi=DPI_QUESTAO).save(saida / "paginas" / f"p{pn}.png")
                if pn > ultima_com_questao:
                    aberta = None
                continue
        # Modelo da página pela largura da barra "Questão NN" (além do meio = largura toda); sem
        # barra desenhada, pelo texto que atravessa o meio; página só de continuação segue a anterior.
        # Voto por barra: começa na metade esquerda e passa do meio = largura toda; barra que começa na
        # coluna da direita (sempre passa do meio) prova duas colunas (igual a recorte.js).
        meio = pagina.rect.width / 2
        votos = [c["r"].x0 < meio - 30 and x > meio + 30 for c, x in ((c, fim_da_barra(pagina, c["r"])) for c in cabs2) if x is not None]
        fins = votos
        if any(c["col"] == 1 for c in cabs2):
            uma = False
        elif fins:
            uma = sum(votos) * 2 > len(votos)
        elif cabs2:
            uma = len(limites_colunas(pagina)) == 1
        else:
            uma = uma_anterior
        uma_anterior = uma
        colunas = [(0, pagina.rect.width)] if uma else duas_colunas(pagina)
        partes, _ = partes_da_pagina(pagina, colunas, fundo, figuras_pagina)
        for parte in partes:
            if parte["tipo"] == "nova":
                aberta = {"numero": parte["numero"], "pagina": pn, "coluna": parte["col"] + 1, "partes": [], "fora": []}
                questoes.append(aberta)
            elif aberta is None:
                continue   # texto antes da 1ª questão (capa, instruções)
            com_cab = parte["tipo"] == "nova"
            regiao = parte["regiao"]
            aparadas = [aparar_figura(f, linhas_texto) for f in ordem_de_leitura(
                [f for f in figuras_pagina if regiao.contains(pymupdf.Point((f.x0 + f.x1) / 2, (f.y0 + f.y1) / 2))])]
            # print de tabela: recorta só a grade (sem o texto que veio junto) e marca como tabela
            grades = [grade_da_tabela(pagina, f) for f in aparadas]
            aparadas = [g or f for f, g in zip(aparadas, grades)]
            centradas = figuras_centralizadas(aparadas, regiao, *mancha(pagina, regiao, com_cab))
            aberta["partes"].append({"pagina": pn, "regiao": regiao, "texto": texto_marcado(pagina, regiao, com_cab),
                                     "figuras": [(f, k in centradas, grades[k] is not None) for k, f in enumerate(aparadas)],
                                     "com_cab": com_cab})
            parte["dono"] = aberta
        for r, t in fora_do_recorte(pagina, partes, fundo, figuras_pagina):
            donos = [pt for pt in partes if pt.get("dono") and (r.y0 + r.y1) / 2 >= pt["regiao"].y0 - 2]
            dono = max(donos, key=lambda pt: pt["regiao"].y0)["dono"] if donos else next((pt["dono"] for pt in partes if pt.get("dono")), None)
            if dono:
                dono["fora"].append(t)

    # Junta as partes de cada questão: texto em ordem, figuras numeradas, imagem empilhada.
    for q in questoes:
        partes = q.pop("partes")
        figuras = []
        for pt in partes:
            pagina = doc[pt["pagina"] - 1]
            for f, centralizada, tabela in pt["figuras"]:
                nome = f"Q{q['numero']:02d}_fig{len(figuras) + 1}.png"
                # Renderiza o recorte em vez de extrair o arquivo da imagem: assim
                # entram também rótulos desenhados por cima (vetores, ângulos, letras).
                pagina.get_pixmap(dpi=DPI_FIGURA, clip=f).save(saida / "figuras" / nome)
                figuras.append({"nome": nome.removesuffix(".png"), "arquivo": f"figuras/{nome}",
                                "regiao": [round(v, 1) for v in f], "centralizada": centralizada, "tabela": tabela})
        nome_q = f"Q{q['numero']:02d}.png"
        juntar_recortes(doc, partes).save(saida / "questoes" / nome_q)
        q.update({
            "regiao": [round(v, 1) for v in partes[0]["regiao"]],
            "regioes": [{"pagina": pt["pagina"], "regiao": [round(v, 1) for v in pt["regiao"]]} for pt in partes],
            "imagem": f"questoes/{nome_q}",
            "texto_pdf": "\n".join(pt["texto"] for pt in partes if pt["texto"]),
            "figuras": figuras,
            "fora_do_recorte": q.pop("fora"),
        })

    inicio_etapas = etapas_pelo_sumario(doc)
    for q in questoes:
        anteriores = [e for e, p in inicio_etapas.items() if p <= q["pagina"]]
        q["etapa"] = anteriores[-1] if anteriores else None

    questoes.sort(key=lambda q: q["numero"])
    numeros = [q["numero"] for q in questoes]
    faltando = sorted(set(range(1, max(numeros) + 1)) - set(numeros)) if numeros else []
    repetidos = sorted({n for n in numeros if numeros.count(n) > 1})

    # O gabarito fica numa página sem questões depois da última questão.
    ultima = max((q["pagina"] for q in questoes), default=0)
    pag_gabarito = next((p for p in paginas_sem_questao if p > ultima), None)

    manifesto = {
        "arquivo": caminho_pdf.name,
        "hash_pdf": hashlib.sha256(caminho_pdf.read_bytes()).hexdigest(),
        "tipo": "simulado" if "simulado" in (caminho_pdf.name + titulo_lista).lower() else "lista",
        "titulo_lista": titulo_lista,
        "total_questoes": len(questoes),
        "numeros_faltando": faltando,
        "numeros_repetidos": repetidos,
        "etapas": inicio_etapas,
        "paginas_sem_questao": [f"paginas/p{p}.png" for p in paginas_sem_questao],
        "pagina_gabarito": f"paginas/p{pag_gabarito}.png" if pag_gabarito else None,
        "gabarito_pdf": gabarito_em_texto(doc[pag_gabarito - 1]) if pag_gabarito else {},
        "questoes": questoes,
    }
    (saida / "manifesto.json").write_text(
        json.dumps(manifesto, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifesto


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--saida", type=Path, help="pasta de saída (padrão: saida/<nome do pdf>)")
    args = ap.parse_args()
    saida = args.saida or Path("saida") / args.pdf.stem
    m = segmentar(args.pdf, saida)
    print(f"{m['titulo_lista']}: {m['total_questoes']} questões → {saida}")
    for etapa, pagina in m["etapas"].items():
        nums = [q["numero"] for q in m["questoes"] if q["etapa"] == etapa]
        if nums:
            print(f"  {etapa}: questões {min(nums):02d}–{max(nums):02d}")
    print(f"  figuras: {sum(len(q['figuras']) for q in m['questoes'])}")
    if m["numeros_faltando"]:
        print(f"  ATENÇÃO: números faltando: {m['numeros_faltando']}")
    if m["numeros_repetidos"]:
        print(f"  ATENÇÃO: números repetidos: {m['numeros_repetidos']}")


if __name__ == "__main__":
    main()
