"""Monta o artefato do claude.ai: upq/web/importador.html + upq/web/recorte.js + upq/web/formulas.js
+ o prompt de upq/prompt.py e a base de tópicos, embutidos como dados. Publicados junto com a
página: dist/ocr/ (scripts/preparar_ocr.sh) e dist/formula/ (scripts/preparar_formulas.py).

O artefato faz o fluxo inteiro sem servidor e sem chave de API: recorta o PDF no navegador
(pdf.js), transcreve com o Claude do próprio claude.ai (capacidade "sample", no plano de quem
usa) e guarda questões, listas e imagens no banco do artefato (capacidades "db" e "assets").

Uso:
    python -m upq.artefato            # → dist/importador-questoes.html
"""

import json
from pathlib import Path

from . import prompt, topicos

RAIZ = Path(__file__).resolve().parent
DESTINO = RAIZ.parent / "dist" / "importador-questoes.html"
# Capacidades que o artefato declara ao ser publicado (ver README).
CAPACIDADES = {"db": {}, "assets": {}, "sample": {}, "downloads": True, "user": {}}


def montar(destino: Path = DESTINO) -> Path:
    pagina = (RAIZ / "web" / "importador.html").read_text(encoding="utf-8")
    recorte = (RAIZ / "web" / "recorte.js").read_text(encoding="utf-8")
    formulas = (RAIZ / "web" / "formulas.js").read_text(encoding="utf-8")
    dados = {
        "sistema": prompt.SISTEMA_LOTE,
        "gabarito": prompt.GABARITO,
        "classificacao": prompt.CLASSIFICACAO,
        "base": [[d, t, assuntos] for (d, t), assuntos in topicos.carregar().items()],
    }
    texto = json.dumps(dados, ensure_ascii=False).replace("</", "<\\/")
    for marca in ("/*__RECORTE__*/", "/*__FORMULAS__*/", "/*__UPQ_DADOS__*/null"):
        if pagina.count(marca) != 1:
            raise ValueError(f"marcador {marca} ausente ou repetido em importador.html")
    pagina = (pagina.replace("/*__RECORTE__*/", recorte).replace("/*__FORMULAS__*/", formulas)
              .replace("/*__UPQ_DADOS__*/null", texto))
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(pagina, encoding="utf-8")
    return destino


if __name__ == "__main__":
    d = montar()
    print(f"{d} ({d.stat().st_size // 1024} KB) · capacidades: {json.dumps(CAPACIDADES)}")
