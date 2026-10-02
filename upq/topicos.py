"""Base de tópicos da plataforma (dados/base_topicos.txt).

Formato do arquivo, igual ao anexo do Prompt Mestre:
    DISCIPLINA: Física
    - Cinemática II: Acoplamento no MCU; Cinemática vetorial; ...
"""

import re
from functools import lru_cache
from pathlib import Path

ARQUIVO = Path(__file__).resolve().parent.parent / "dados" / "base_topicos.txt"


@lru_cache
def carregar(caminho: Path = ARQUIVO) -> dict[tuple[str, str], list[str]]:
    base: dict[tuple[str, str], list[str]] = {}
    disciplina = None
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        m = re.match(r"DISCIPLINA:\s*(.+)", linha)
        if m:
            disciplina = m.group(1).strip()
            continue
        m = re.match(r"-\s*([^:]+?)(?::\s*(.*))?$", linha.strip())
        if m and disciplina:
            assuntos = [a.strip() for a in (m.group(2) or "").split(";") if a.strip()]
            base[(disciplina, m.group(1).strip())] = assuntos
    return base


def texto_para_prompt(caminho: Path = ARQUIVO) -> str:
    return caminho.read_text(encoding="utf-8").strip()


def sql_carga(caminho: Path = ARQUIVO) -> str:
    """Gera o INSERT da tabela public.topicos (supabase/migrations/003_base_topicos.sql)."""
    def q(s: str) -> str:
        return "'" + s.replace("'", "''") + "'"

    linhas = [
        f"({q(d)}, {q(t)}, ARRAY[{', '.join(q(a) for a in assuntos)}]::text[])"
        for (d, t), assuntos in carregar(caminho).items()
    ]
    return (
        "-- Base de tópicos da plataforma. Gerado por: python -m upq.topicos\n"
        "insert into public.topicos (disciplina, topico, assuntos) values\n"
        + ",\n".join(linhas)
        + "\non conflict (disciplina, topico) do update set assuntos = excluded.assuntos;\n"
    )


if __name__ == "__main__":
    destino = ARQUIVO.parent.parent / "supabase" / "migrations" / "003_base_topicos.sql"
    destino.write_text(sql_carga(), encoding="utf-8")
    print(f"{len(carregar())} pares disciplina/tópico → {destino}")
