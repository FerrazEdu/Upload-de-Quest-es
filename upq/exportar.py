"""Exporta transcricao.json para o .xlsx de 15 colunas do Prompt Mestre (aba "Questões"),
para quem ainda usa o importador antigo. O texto mantém Markdown + LaTeX; a coluna
"Explicação do Professor" fica vazia.

Uso:
    python -m upq.exportar saida/MCU   # → saida/MCU/<nome do pdf>.xlsx
"""

import sys
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Font

from .modelo import Lista

COLUNAS = ["Nº", "Título", "Instituição", "Ano", "Disciplina", "Tópico", "Dificuldade",
           "Enunciado", "Alternativa A", "Alternativa B", "Alternativa C", "Alternativa D",
           "Alternativa E", "Gabarito", "Explicação do Professor"]


def exportar(pasta: Path) -> Path:
    lista = Lista.model_validate_json((pasta / "transcricao.json").read_text(encoding="utf-8"))
    wb = openpyxl.Workbook()
    aba = wb.active
    aba.title = "Questões"
    aba.append(COLUNAS)
    for c in aba[1]:
        c.font = Font(bold=True)
    for q in lista.questoes:
        a = q.alternativas
        aba.append([f"{q.numero:02d}", q.titulo, q.instituicao or "", q.ano or "", q.disciplina,
                    q.topico, q.dificuldade, q.enunciado, a.get("A", ""), a.get("B", ""),
                    a.get("C", ""), a.get("D", ""), a.get("E", ""), q.gabarito, ""])
    for linha in aba.iter_rows(min_row=2):
        for c in linha:
            c.alignment = Alignment(wrap_text=True, vertical="top")
    for letra, largura in zip("ABCDEFGHIJKLMNO", [5, 50, 14, 6, 12, 18, 10, 70, 30, 30, 30, 30, 30, 9, 70]):
        aba.column_dimensions[letra].width = largura
    destino = pasta / (Path(lista.arquivo).stem + ".xlsx")
    wb.save(destino)
    return destino


if __name__ == "__main__":
    print(exportar(Path(sys.argv[1])))
