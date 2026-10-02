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
RE_FIGURA = re.compile(r"!\[[^\]]*\]\(figura:([A-Za-z0-9_]+)\)")
PROIBIDOS = [r"\ce{", r"\SI{", r"\usepackage", r"\begin{document}"]
UNICODE_MAT = "²³¹⁰⁴⁵⁶⁷⁸⁹₀₁₂₃₄₅₆₇₈₉√≤≥≠±×÷∞∫∑πΔ≈"


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


def conferir_com_pdf(texto_pdf: str, transcricao: str) -> list[str]:
    """Compara números e palavras do PDF com a transcrição (só gera avisos)."""
    avisos = []
    corpo = "\n".join(texto_pdf.splitlines()[1:])  # 1ª linha é a barra "Questão NN  BANCA ANO"
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
        for letra, texto in q.alternativas.items():
            if not texto.strip():
                erros.append(f"alternativa {letra} vazia")
            elif re.match(r"^\(?[a-eA-E][\)\.]\s", texto):
                avisos.append(f"alternativa {letra} parece começar com a letra")
        faixa = FAIXA_ETAPA.get(q.etapa or "")
        if faixa and not faixa[0] <= q.dificuldade <= faixa[1]:
            avisos.append(f"dificuldade {q.dificuldade} fora da faixa {faixa[0]}–{faixa[1]} de {q.etapa}")
        if not q.explicacao.rstrip().endswith(f"**Gabarito: {q.gabarito}**"):
            avisos.append("explicação não termina com **Gabarito: X** igual ao gabarito")

        campos = {"enunciado": q.enunciado, "explicacao": q.explicacao,
                  **{f"alternativa {k}": v for k, v in q.alternativas.items()}}
        for nome, texto in campos.items():
            e, a = checar_latex(nome, texto)
            erros += e
            avisos += a
        nomes = {f.nome for f in q.figuras}
        usadas = {n for t in campos.values() for n in RE_FIGURA.findall(t)}
        if usadas - nomes:
            erros.append(f"figura inexistente referenciada: {', '.join(sorted(usadas - nomes))}")
        if nomes - usadas:
            avisos.append(f"figura recortada mas não usada no texto: {', '.join(sorted(nomes - usadas))}")

        transcrito = "\n".join([q.enunciado, *q.alternativas.values()])
        avisos += conferir_com_pdf(texto_pdf.get(q.numero, ""), transcrito)
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
