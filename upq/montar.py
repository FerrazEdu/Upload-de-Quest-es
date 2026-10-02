"""Junta manifesto.json + ia/*.json em transcricao.json (formato `Lista`).

O que é determinístico vem do código, não da IA: título no padrão, etapa, página,
figuras e o gabarito oficial.
"""

import json
import re
from pathlib import Path

from .modelo import Figura, Lista, Questao, QuestaoIA, titulo_padrao


def dados_simulado(manifesto: dict) -> tuple[int | None, int | None]:
    """Número do simulado e dia de prova, do nome do arquivo (ex.: 13_Simulado_1_DIA.pdf)."""
    nome = manifesto["arquivo"].replace("_", " ")
    sim = re.search(r"(\d+)\s*[ºo°]?\s*Simulado", nome, re.I)
    dia = re.search(r"(\d+)\s*[ºo°]?\s*DIA|DIA\s*(\d+)", nome, re.I)
    return (int(sim.group(1)) if sim else None,
            int(next(g for g in dia.groups() if g)) if dia else None)


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
        observacoes = [ia.observacoes] if ia.observacoes else []
        oficial = gabarito.get(f"{q['numero']:02d}")
        if oficial and oficial != ia.gabarito:
            observacoes.append(f"IA indicou {ia.gabarito}, gabarito oficial é {oficial}")
        questoes.append(Questao(
            numero=q["numero"],
            titulo=titulo_padrao(manifesto["tipo"], manifesto["titulo_lista"], q["numero"],
                                 ia.instituicao, ia.ano, sim, dia),
            instituicao=ia.instituicao,
            ano=ia.ano,
            disciplina=ia.disciplina,
            topico=ia.topico,
            etapa=q.get("etapa"),
            dificuldade=ia.dificuldade,
            enunciado=ia.enunciado.strip(),
            alternativas={a.letra: a.texto.strip() for a in ia.alternativas},
            gabarito=oficial or ia.gabarito,
            explicacao=ia.explicacao.strip(),
            figuras=[Figura(nome=f["nome"], arquivo=f["arquivo"]) for f in q["figuras"]],
            pagina=q["pagina"],
            imagem=q["imagem"],
            revisar=ia.revisar or bool(oficial and oficial != ia.gabarito) or not oficial,
            observacoes="; ".join(observacoes) or (None if oficial else "gabarito oficial não encontrado"),
        ))

    lista = Lista(
        arquivo=manifesto["arquivo"],
        hash_pdf=manifesto["hash_pdf"],
        tipo=manifesto["tipo"],
        titulo=manifesto["titulo_lista"],
        disciplina=classe.get("disciplina"),
        topico=classe.get("topico"),
        questoes=questoes,
    )
    (pasta / "transcricao.json").write_text(lista.model_dump_json(indent=2), encoding="utf-8")
    return lista


if __name__ == "__main__":
    import sys
    lista = montar(Path(sys.argv[1]))
    print(f"{lista.titulo}: {len(lista.questoes)} questões → transcricao.json")
