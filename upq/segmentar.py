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


def limites_colunas(pagina):
    """Retorna as faixas x das colunas. O modelo usa 2 colunas separadas por um fio vertical."""
    meio = pagina.rect.width / 2
    for im in pagina.get_image_info():
        r = pymupdf.Rect(im["bbox"])
        if r.width < 3 and r.height > pagina.rect.height * 0.6:
            meio = (r.x0 + r.x1) / 2
            break
    return [(0, meio), (meio, pagina.rect.width)]


def fim_da_coluna(pagina):
    """y do fio do rodapé (linha horizontal longa perto do fim da página)."""
    candidatos = [
        pymupdf.Rect(im["bbox"]).y0
        for im in pagina.get_image_info()
        if pymupdf.Rect(im["bbox"]).height < 4
        and pymupdf.Rect(im["bbox"]).width > pagina.rect.width * 0.8
        and pymupdf.Rect(im["bbox"]).y0 > pagina.rect.height * 0.8
    ]
    return min(candidatos) if candidatos else pagina.rect.height - 30


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
        if t.y0 < r.y1 < t.y1:        # cruza a borda de baixo
            r.y1 = t.y0 - 1
        elif t.y0 < r.y0 < t.y1:      # cruza a borda de cima
            r.y0 = t.y1 + 1
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


def segmentar(caminho_pdf: Path, saida: Path) -> dict:
    doc = pymupdf.open(caminho_pdf)
    (saida / "questoes").mkdir(parents=True, exist_ok=True)
    (saida / "figuras").mkdir(exist_ok=True)
    (saida / "paginas").mkdir(exist_ok=True)

    titulo_lista = ""
    questoes = []
    paginas_sem_questao = []

    for pn, pagina in enumerate(doc, start=1):
        colunas = limites_colunas(pagina)
        fundo = fim_da_coluna(pagina)
        cabecalhos = []
        linhas_texto = []
        for texto, r in linhas(pagina):
            if texto.strip():
                linhas_texto.append(r)
            if not titulo_lista and texto.startswith("Lista de Exercícios"):
                titulo_lista = texto.split("|", 1)[-1].strip()
            m = RE_QUESTAO.match(texto)
            if m and r.y0 > MARGEM_TOPO:
                col = 0 if r.x0 < colunas[0][1] else 1
                cabecalhos.append((col, r.y0, int(m.group(1).replace(" ", ""))))

        if not cabecalhos:
            paginas_sem_questao.append(pn)
            pagina.get_pixmap(dpi=DPI_QUESTAO).save(saida / "paginas" / f"p{pn}.png")
            continue

        figuras_pagina = [
            pymupdf.Rect(im["bbox"]) for im in pagina.get_image_info()
            if pymupdf.Rect(im["bbox"]).width >= FIGURA_MIN
            and pymupdf.Rect(im["bbox"]).height >= FIGURA_MIN
            and pymupdf.Rect(im["bbox"]).y0 > MARGEM_TOPO
        ]

        for col in (0, 1):
            na_coluna = sorted((y, n) for c, y, n in cabecalhos if c == col)
            x0, x1 = colunas[col]
            for i, (y, numero) in enumerate(na_coluna):
                y_fim = na_coluna[i + 1][0] - 2 if i + 1 < len(na_coluna) else fundo - 2
                regiao = pymupdf.Rect(x0 + 2, y - 2, x1 - 2, y_fim)
                figuras = []
                for k, f in enumerate(
                    ordem_de_leitura([f for f in figuras_pagina
                                      if regiao.contains(pymupdf.Point((f.x0 + f.x1) / 2, (f.y0 + f.y1) / 2))]), start=1):
                    f = aparar_figura(f, linhas_texto)
                    nome = f"Q{numero:02d}_fig{k}.png"
                    # Renderiza o recorte em vez de extrair o arquivo da imagem: assim
                    # entram também rótulos desenhados por cima (vetores, ângulos, letras).
                    pagina.get_pixmap(dpi=DPI_FIGURA, clip=f).save(saida / "figuras" / nome)
                    figuras.append({"nome": nome.removesuffix(".png"),
                                    "arquivo": f"figuras/{nome}",
                                    "regiao": [round(v, 1) for v in f]})
                nome_q = f"Q{numero:02d}.png"
                pagina.get_pixmap(dpi=DPI_QUESTAO, clip=regiao).save(saida / "questoes" / nome_q)
                questoes.append({
                    "numero": numero,
                    "pagina": pn,
                    "coluna": col + 1,
                    "regiao": [round(v, 1) for v in regiao],
                    "imagem": f"questoes/{nome_q}",
                    "texto_pdf": pagina.get_text("text", clip=regiao, sort=True).strip(),
                    "figuras": figuras,
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
