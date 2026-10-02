"""Validação de transcricao.json antes do envio.

ERRO impede o envio (o banco também recusaria); AVISO vai para a revisão humana.
Além da estrutura, confere a transcrição contra o texto do próprio PDF: números
e palavras do PDF que sumiram da transcrição costumam indicar trecho cortado ou
valor trocado.
"""

import json
import re
import unicodedata
from pathlib import Path

from . import topicos
from .modelo import Lista

FAIXA_ETAPA = {"Fixação": (1, 2), "Treinamento": (2, 3), "Aprofundamento": (3, 4), "Desafios": (4, 5)}
RE_MATH = re.compile(r"\$\$.+?\$\$|\$.+?\$", re.S)
RE_FIGURA = re.compile(r'(?:!\[[^\]]*\]\(|src=")figura:([A-Za-z0-9_]+)')
PROIBIDOS = [r"\ce{", r"\SI{", r"\usepackage", r"\begin{document}"]
UNICODE_MAT = "²³¹⁰⁴⁵⁶⁷⁸⁹₀₁₂₃₄₅₆₇₈₉√≤≥≠±×÷∞∫∑πΔ≈"
# aviso que a IA às vezes escreve no lugar de um trecho que não leu (fórmula em imagem, por exemplo)
RE_NAO_LIDO = re.compile(r"n[ãa]o\s+(?:[ée]\s+)?leg[ií]ve|ileg[ií]ve|n[ãa]o\s+(?:foi\s+)?(?:capturad|extra[ií]d|identificad)"
                         r"|n[ãa]o\s+dispon[ií]vel\s+no\s+texto|\((?:express[ãa]o|f[óo]rmula)[^)]*\)", re.I)


def sem_math(texto: str) -> str:
    return RE_MATH.sub(" ", texto.replace(r"\$", ""))


def checar_latex(campo: str, texto: str) -> tuple[list[str], list[str]]:
    erros, avisos = [], []
    limpo = texto.replace(r"\$", "")
    if limpo.count("$") % 2:
        erros.append(f"{campo}: quantidade ímpar de '$' (fórmula aberta ou R$ sem escape)")
    if re.search(r"R\$\s?\d", limpo):
        erros.append(f"{campo}: 'R$' sem escape (use R\\$)")
    for m in RE_MATH.finditer(limpo):
        f = m.group(0)
        if f.count("{") != f.count("}"):
            erros.append(f"{campo}: chaves desbalanceadas em {f[:40]}")
        for p in PROIBIDOS:
            if p in f:
                erros.append(f"{campo}: comando não suportado {p}")
    fora = sem_math(texto)
    achados = sorted({c for c in fora if c in UNICODE_MAT})
    if achados:
        avisos.append(f"{campo}: símbolo fora de LaTeX ({' '.join(achados)})")
    return erros, avisos


def normalizar(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def _so_alnum(s: str) -> str:
    """Texto comparável: sem comandos LaTeX, tags, acentos, pontuação e espaços."""
    s = re.sub(r"\\[a-zA-Z]+|<[^>]+>", " ", s)
    return re.sub(r"[^a-z0-9]", "", normalizar(s))


def _trechos_negrito(t: str) -> str:
    partes = re.findall(r"\*\*(.+?)\*\*", t, re.S) + re.findall(r"<strong>(.+?)</strong>", t, re.S)
    partes += re.findall(r"<thead>(.*?)</thead>", t, re.S)   # cabeçalho de tabela HTML
    linhas = t.split("\n")
    for i, l in enumerate(linhas):   # 1ª linha de tabela Markdown = cabeçalho (sai em negrito)
        if l.strip().startswith("|") and (i == 0 or not linhas[i - 1].strip().startswith("|")):
            partes.append(l)
    return "|".join(_so_alnum(x) for x in partes)


def _trechos_centralizados(t: str) -> str:
    partes = re.findall(r'<p style="text-align: center;">(.*?)</p>', t, re.S)
    partes += re.findall(r'<table style="margin-left: auto; margin-right: auto;">(.*?)</table>', t, re.S)
    return "|".join(_so_alnum(x) for x in partes)


def conferir_formatacao(texto_pdf: str, transcricao: str) -> list[str]:
    """Negrito e centralização do PDF (marcados no texto extraído) têm de estar na transcrição."""
    erros = []
    linhas = texto_pdf.splitlines()[1:]   # a 1ª é a barra "Questão NN"
    negrito, centro = _trechos_negrito(transcricao), _trechos_centralizados(transcricao)
    faltam_n, faltam_c = [], []
    for l in linhas:
        cent = l.startswith("[centralizado] ")
        l = l.removeprefix("[centralizado] ")
        for run in re.findall(r"\*\*(.+?)\*\*", l):
            n = _so_alnum(run)
            if len(re.sub(r"[0-9]", "", n)) >= 4 and n not in negrito:
                faltam_n.append(run.strip())
        limpo = l.replace("**", "")
        n = _so_alnum(limpo)
        if cent and len(n) >= 3 and not re.match(r"\s*\(?(fonte|dispon[ií]vel)", limpo, re.I) and n not in centro:
            faltam_c.append(limpo.strip())
    if faltam_n:
        erros.append("negrito do PDF ausente na transcrição: " + "; ".join(f"«{t[:60]}»" for t in faltam_n[:4]))
    if faltam_c:
        erros.append("texto centralizado no PDF sem centralizar: " + "; ".join(f"«{t[:60]}»" for t in faltam_c[:4]))
    return erros


def conferir_repeticoes(texto_pdf: str, transcricao: str) -> list[str]:
    """Trava contra vazamento: nenhum trecho do PDF aparece na transcrição mais vezes do que no
    PDF (ex.: cabeçalho de tabela repetido como título)."""
    originais = [l.removeprefix("[centralizado] ").replace("**", "").strip() for l in texto_pdf.splitlines()[1:]]
    linhas = [_so_alnum(l) for l in originais]
    pdf, tr = "".join(linhas), _so_alnum(transcricao)
    repetidos = [n for n in dict.fromkeys(linhas) if len(n) >= 12 and tr.count(n) > pdf.count(n)]
    if not repetidos:
        return []
    nomes = [next((o for o in originais if _so_alnum(o) == n), n)[:60] for n in repetidos[:3]]
    return ["trecho repetido na transcrição (aparece mais vezes do que no PDF): " + "; ".join(f"«{t}»" for t in nomes)]


def conferir_com_pdf(texto_pdf: str, transcricao: str) -> list[str]:
    """Compara números e palavras do PDF com a transcrição: o que falta é erro (trecho perdido)."""
    avisos = []
    texto_pdf = texto_pdf.replace("[centralizado] ", "").replace("**", "")
    # 1ª linha é a barra "Questão NN  BANCA ANO"; créditos de figura podem estar dentro da imagem.
    corpo = "\n".join(l for l in texto_pdf.splitlines()[1:]
                      if not re.match(r"\s*\(?(Fonte|Disponível em)", l))
    digitos_trans = re.sub(r"\D", "", transcricao)
    faltando = [n for n in re.findall(r"\d+", corpo.replace(".", ""))
                if len(n) >= 2 and n not in digitos_trans]
    if faltando:
        avisos.append(f"números do PDF ausentes na transcrição: {', '.join(sorted(set(faltando)))}")
    palavras_pdf = {w for w in re.findall(r"[a-zà-ú]{5,}", normalizar(corpo))}
    trans = normalizar(transcricao)
    if palavras_pdf:
        cobertura = sum(w in trans for w in palavras_pdf) / len(palavras_pdf)
        if cobertura < 0.85:
            avisos.append(f"só {cobertura:.0%} das palavras do PDF aparecem na transcrição "
                          "(trecho cortado?)")
    return avisos


def validar(pasta: Path) -> tuple[Lista, dict[int, dict[str, list[str]]]]:
    lista = Lista.model_validate_json((pasta / "transcricao.json").read_text(encoding="utf-8"))
    manifesto = json.loads((pasta / "manifesto.json").read_text(encoding="utf-8"))
    texto_pdf = {q["numero"]: q["texto_pdf"] for q in manifesto["questoes"]}
    fora_do_recorte = {q["numero"]: q.get("fora_do_recorte") for q in manifesto["questoes"]}
    figuras_manifesto = {q["numero"]: q.get("figuras", []) for q in manifesto["questoes"]}
    base = topicos.carregar()
    resultado = {}

    for q in lista.questoes:
        erros, avisos = [], []
        if (q.disciplina, q.topico) not in base:
            erros.append(f"par fora da base de tópicos: {q.disciplina} / {q.topico}")
        if lista.tipo == "lista" and (q.disciplina, q.topico) != (lista.disciplina, lista.topico):
            erros.append("disciplina/tópico diferente do resto da lista")
        letras = list(q.alternativas)
        if letras != list("ABCDE"[: len(letras)]) or len(letras) < 2:
            erros.append(f"alternativas fora de ordem ou insuficientes: {letras}")
        if q.gabarito not in q.alternativas:
            erros.append(f"gabarito {q.gabarito} não está entre as alternativas")
        for nome, texto in [("enunciado", q.enunciado), *((f"alternativa {k}", v) for k, v in q.alternativas.items())]:
            achado = RE_NAO_LIDO.search(texto or "")
            if achado:
                erros.append(f"{nome}: trecho não transcrito (a IA escreveu «{achado.group(0)}»)")
        for letra, texto in q.alternativas.items():
            if not texto.strip():
                erros.append(f"alternativa {letra} vazia")
            elif re.match(r"^\(?[a-eA-E][\)\.]\s", texto):
                avisos.append(f"alternativa {letra} parece começar com a letra")
        faixa = FAIXA_ETAPA.get(q.etapa or "")
        if faixa and not faixa[0] <= q.dificuldade <= faixa[1]:
            avisos.append(f"dificuldade {q.dificuldade} fora da faixa {faixa[0]}–{faixa[1]} de {q.etapa}")
        validos = base.get((q.disciplina, q.topico)) or [q.topico]
        if not q.assuntos:
            erros.append("sem assunto")
        for a in q.assuntos:
            if a not in validos:
                erros.append(f"assunto fora da base para {q.topico}: {a}")

        fora = fora_do_recorte.get(q.numero) or []
        if fora:
            erros.append("recorte incompleto: trecho da página fora da questão ("
                         + "; ".join(f"«{t}»" for t in fora[:3]) + ")")
        campos = {"enunciado": q.enunciado,
                  **{f"alternativa {k}": v for k, v in q.alternativas.items()}}
        for nome, texto in campos.items():
            e, a = checar_latex(nome, texto)
            erros += e
            avisos += a
        nomes = {f.nome for f in q.figuras}
        usadas = {n for t in campos.values() for n in RE_FIGURA.findall(t)}
        if usadas - nomes:
            erros.append(f"figura inexistente referenciada: {', '.join(sorted(usadas - nomes))}")
        # tabela colada como imagem (print) no PDF: tem de virar tabela de verdade, nunca imagem
        tabelas_img = {f["nome"] for f in figuras_manifesto.get(q.numero, []) if f.get("tabela")}
        if tabelas_img & usadas:
            erros.append(f"tabela colada como imagem no PDF usada como figura ({', '.join(sorted(tabelas_img & usadas))}): "
                         "transcreva-a como tabela")
        elif tabelas_img and not any(re.search(r"<table|^\s*\|", t, re.M) for t in campos.values()):
            erros.append(f"tabela da imagem não foi transcrita ({', '.join(sorted(tabelas_img))})")
        if nomes - usadas - tabelas_img:
            erros.append(f"figura recortada mas não usada no texto: {', '.join(sorted(nomes - usadas - tabelas_img))}")

        transcrito = "\n".join([q.enunciado, *q.alternativas.values()])
        erros += conferir_com_pdf(texto_pdf.get(q.numero, ""), transcrito)
        erros += conferir_formatacao(texto_pdf.get(q.numero, ""), transcrito)
        erros += conferir_repeticoes(texto_pdf.get(q.numero, ""), transcrito)
        if q.revisar:
            avisos.insert(0, f"IA pediu revisão: {q.observacoes or '(sem motivo)'}")
        resultado[q.numero] = {"erros": erros, "avisos": avisos}
    return lista, resultado


def resumo(resultado: dict) -> tuple[int, int]:
    return (sum(len(r["erros"]) for r in resultado.values()),
            sum(len(r["avisos"]) for r in resultado.values()))


if __name__ == "__main__":
    import sys
    pasta = Path(sys.argv[1])
    lista, res = validar(pasta)
    for n, r in res.items():
        for e in r["erros"]:
            print(f"Q{n:02d} ERRO  {e}")
        for a in r["avisos"]:
            print(f"Q{n:02d} AVISO {a}")
    e, a = resumo(res)
    print(f"{len(lista.questoes)} questões · {e} erro(s) · {a} aviso(s)")
    sys.exit(1 if e else 0)
