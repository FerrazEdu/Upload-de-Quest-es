"""Junta manifesto.json + ia/*.json em transcricao.json (formato `Lista`).

O que é determinístico vem do código, não da IA: título no padrão, etapa, página,
figuras e o gabarito oficial.
"""

import json
import re
from pathlib import Path

from . import referencias
from .modelo import Figura, Lista, Questao, QuestaoIA, titulo_padrao


def dados_simulado(manifesto: dict) -> tuple[int | None, int | None]:
    """Número do simulado e dia de prova, do nome do arquivo (ex.: 13_Simulado_1_DIA.pdf)."""
    nome = manifesto["arquivo"].replace("_", " ")
    sim = re.search(r"(\d+)\s*[ºo°]?\s*Simulado", nome, re.I)
    dia = re.search(r"(\d+)\s*[ºo°]?\s*DIA|DIA\s*(\d+)", nome, re.I)
    return (int(sim.group(1)) if sim else None,
            int(next(g for g in dia.groups() if g)) if dia else None)


def cabecalho_da_barra(texto_pdf: str) -> tuple[str | None, int | None]:
    """Banca e ano da barra "Questão NN  BANCA ANO" (1ª linha do texto do PDF), pelo código.
    "(ADAPTADO)" sai; o ano é o último 19xx/20xx. Sem texto legível na barra → (None, None)."""
    linhas = (texto_pdf or "").split("\n")
    linha = next((l for l in linhas if re.match(r"^\s*Quest[aã]o\s*\d", l, re.I)), linhas[0])   # a barra, nunca outra linha
    resto = re.sub(r"^\s*Quest[aã]o\s*\d[\d ]*", "", linha, flags=re.I).strip()
    if not re.search(r"[A-Za-z]{2,}", resto):
        return None, None
    resto = re.sub(r"\(\s*ADAPTAD[OA]\s*\)", " ", resto, flags=re.I).strip()
    anos = list(re.finditer(r"(?:19|20)\d{2}", resto))
    ano = int(anos[-1].group(0)) if anos else None
    inst = (resto[: anos[-1].start()] if anos else resto)
    inst = re.sub(r"[\s\-–—|,/]+$", "", inst).strip() or None
    return inst, ano


def montar(pasta: Path) -> Lista:
    manifesto = json.loads((pasta / "manifesto.json").read_text(encoding="utf-8"))
    dados_lista = json.loads((pasta / "ia" / "lista.json").read_text(encoding="utf-8"))
    gabarito = dados_lista["gabarito"]
    classe = dados_lista.get("classificacao") or {}
    sim, dia = dados_simulado(manifesto) if manifesto["tipo"] == "simulado" else (None, None)

    questoes = []
    for q in manifesto["questoes"]:
        arq = pasta / "ia" / f"Q{q['numero']:02d}.json"
        if not arq.exists():
            raise FileNotFoundError(f"falta a transcrição de Q{q['numero']:02d} ({arq})")
        ia = QuestaoIA.model_validate_json(arq.read_text(encoding="utf-8"))
        centradas = {f["nome"] for f in q["figuras"] if f.get("centralizada")}
        inst_barra, ano_barra = cabecalho_da_barra(q.get("texto_pdf", ""))
        instituicao, ano = inst_barra or ia.instituicao, ano_barra or ia.ano
        observacoes = [ia.observacoes] if ia.observacoes else []
        oficial = gabarito.get(f"{q['numero']:02d}")
        if not oficial:   # o gabarito vem só da tabela do fim da lista, nunca da IA
            raise ValueError(f"Q{q['numero']:02d} sem gabarito na tabela do PDF: preencha ia/lista.json")
        if oficial and oficial != ia.gabarito:
            observacoes.append(f"IA indicou {ia.gabarito}, gabarito oficial é {oficial}")
        questoes.append(Questao(
            numero=q["numero"],
            titulo=titulo_padrao(manifesto["tipo"], manifesto["titulo_lista"], q["numero"],
                                 instituicao, ano, sim, dia),
            instituicao=instituicao,
            ano=ano,
            disciplina=ia.disciplina,
            topico=ia.topico,
            assuntos=ia.assuntos,
            etapa=q.get("etapa"),
            dificuldade=ia.dificuldade,
            enunciado=referencias.normalizar(ia.enunciado.strip(), centradas),
            alternativas={a.letra: referencias.normalizar(a.texto.strip(), centradas) for a in ia.alternativas},
            gabarito=oficial,
            figuras=[Figura(nome=f["nome"], arquivo=f["arquivo"]) for f in q["figuras"]],
            pagina=q["pagina"],
            imagem=q["imagem"],
            revisar=ia.revisar or oficial != ia.gabarito,
            observacoes="; ".join(observacoes) or None,
        ))

    lista = Lista(
        arquivo=manifesto["arquivo"],
        hash_pdf=manifesto["hash_pdf"],
        tipo=manifesto["tipo"],
        titulo=manifesto["titulo_lista"],
        nome=f"Lista de {manifesto['titulo_lista']}",
        descricao=f"Lista completa de {manifesto['titulo_lista']}",
        disciplina=classe.get("disciplina"),
        topico=classe.get("topico"),
        tags=list(dict.fromkeys(a for q in questoes for a in q.assuntos)),
        questoes=questoes,
    )
    (pasta / "transcricao.json").write_text(lista.model_dump_json(indent=2), encoding="utf-8")
    return lista


if __name__ == "__main__":
    import sys
    lista = montar(Path(sys.argv[1]))
    print(f"{lista.titulo}: {len(lista.questoes)} questões → transcricao.json")
