"""Fluxo completo: PDF → questões no Supabase.

    python -m upq processar LISTA.pdf          segmenta, transcreve (API), monta, valida e gera a revisão
    python -m upq processar pasta_de_pdfs/     o mesmo para todos os PDFs da pasta (em lote)
    python -m upq revisar saida/LISTA          refaz montagem + validação + revisao.html
    python -m upq enviar saida/LISTA           envia ao Supabase (ver upq/enviar.py)
    python -m upq exportar saida/LISTA         gera o .xlsx de 15 colunas

Sem chave de API, a transcrição pode ser feita pelo Claude Code (ver CLAUDE.md);
depois rode `revisar` e `enviar` normalmente.
"""

import asyncio
import os
import sys
import time
from pathlib import Path

from . import enviar, exportar, montar, revisao, segmentar, validar


def tem_credencial() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


def revisar(pasta: Path):
    montar.montar(pasta)
    destino = revisao.gerar(pasta)
    _, res = validar.validar(pasta)
    erros, avisos = validar.resumo(res)
    print(f"  validação: {erros} erro(s), {avisos} aviso(s) → {destino}")


def processar_pdf(pdf: Path, saida: Path):
    inicio = time.time()
    pasta = saida / pdf.stem
    m = segmentar.segmentar(pdf, pasta)
    print(f"{pdf.name}: {m['total_questoes']} questões segmentadas ({time.time() - inicio:.0f}s)")
    if not tem_credencial():
        print("  sem ANTHROPIC_API_KEY: transcreva pelo Claude Code (CLAUDE.md) e rode "
              f"`python -m upq revisar {pasta}`")
        return
    from . import transcrever
    asyncio.run(transcrever.executar(pasta, paralelo=8, esforco="low", refazer=False))
    revisar(pasta)
    print(f"  total: {time.time() - inicio:.0f}s")


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    comando, alvo = sys.argv[1], Path(sys.argv[2])
    saida = Path(os.environ.get("UPQ_SAIDA", "saida"))
    if comando == "processar":
        pdfs = sorted(alvo.glob("*.pdf")) if alvo.is_dir() else [alvo]
        for pdf in pdfs:
            try:
                processar_pdf(pdf, saida)
            except Exception as e:  # em lote, uma lista com problema não para as outras
                print(f"{pdf.name}: FALHOU — {e}", file=sys.stderr)
    elif comando == "revisar":
        revisar(alvo)
    elif comando == "enviar":
        sys.argv = [sys.argv[0], *sys.argv[2:]]
        enviar.main()
    elif comando == "exportar":
        print(exportar.exportar(alvo))
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
