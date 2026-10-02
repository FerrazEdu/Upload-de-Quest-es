"""Envia transcricao.json ao Supabase: figuras no Storage (bucket "figuras") e a
lista inteira pela função importar_lista (uma transação; reenviar atualiza).

Variáveis de ambiente (Dashboard → Project Settings → API Keys):
    SUPABASE_URL           https://<ref>.supabase.co
    SUPABASE_SECRET_KEY    chave secreta (sb_secret_...) ou a service_role legada

Uso:
    python -m upq.enviar saida/MCU [--forcar]   # --forcar envia mesmo com avisos
"""

import argparse
import os
import re
import sys
from pathlib import Path

import requests

from .modelo import Lista
from .validar import RE_FIGURA, resumo, validar

BUCKET = "figuras"


def cabecalhos(chave: str) -> dict:
    h = {"apikey": chave}
    if chave.startswith("eyJ"):  # chave legada (JWT) também vai no Authorization
        h["Authorization"] = f"Bearer {chave}"
    return h


def enviar(pasta: Path, url: str, chave: str) -> str:
    lista = Lista.model_validate_json((pasta / "transcricao.json").read_text(encoding="utf-8"))
    h = cabecalhos(chave)
    prefixo = lista.hash_pdf[:16]

    for q in lista.questoes:
        for f in q.figuras:
            caminho = f"{prefixo}/{f.nome}.png"
            r = requests.post(
                f"{url}/storage/v1/object/{BUCKET}/{caminho}",
                headers={**h, "Content-Type": "image/png", "x-upsert": "true"},
                data=(pasta / f.arquivo).read_bytes(), timeout=60)
            r.raise_for_status()
            f.url = f"{url}/storage/v1/object/public/{BUCKET}/{caminho}"
        urls = {f.nome: f.url for f in q.figuras}

        def trocar(texto: str) -> str:
            return RE_FIGURA.sub(lambda m: m.group(0).replace(f"figura:{m.group(1)}", urls[m.group(1)]), texto)

        q.enunciado = trocar(q.enunciado)
        q.explicacao = trocar(q.explicacao)
        q.alternativas = {k: trocar(v) for k, v in q.alternativas.items()}

    payload = {
        "arquivo": lista.arquivo, "hash_pdf": lista.hash_pdf, "tipo": lista.tipo,
        "titulo": lista.titulo, "disciplina": lista.disciplina, "topico": lista.topico,
        "questoes": [
            {**q.model_dump(exclude={"imagem"}),
             "figuras": [{"nome": f.nome, "url": f.url} for f in q.figuras]}
            for q in lista.questoes
        ],
    }
    r = requests.post(f"{url}/rest/v1/rpc/importar_lista", json={"p": payload},
                      headers={**h, "Content-Type": "application/json"}, timeout=120)
    if not r.ok:
        raise RuntimeError(f"importar_lista falhou ({r.status_code}): {r.text}")
    return r.json()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pasta", type=Path)
    ap.add_argument("--forcar", action="store_true", help="envia mesmo com avisos pendentes")
    args = ap.parse_args()

    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    chave = os.environ.get("SUPABASE_SECRET_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not chave:
        sys.exit("Defina SUPABASE_URL e SUPABASE_SECRET_KEY (veja o README).")
    if not re.match(r"https://[a-z0-9]+\.supabase\.co$", url):
        print(f"atenção: URL incomum: {url}")

    lista, res = validar(args.pasta)
    erros, avisos = resumo(res)
    if erros:
        sys.exit(f"{erros} erro(s) na validação — corrija antes de enviar (python -m upq.validar).")
    if avisos and not args.forcar:
        sys.exit(f"{avisos} aviso(s) pendentes — revise em revisao.html e reenvie com --forcar.")
    lista_id = enviar(args.pasta, url, chave)
    print(f"enviada: {lista.titulo} ({len(lista.questoes)} questões) · lista_id {lista_id}")


if __name__ == "__main__":
    main()
