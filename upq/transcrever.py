"""Transcrição com a API do Claude: lê o gabarito, classifica a lista e transcreve
cada questão em paralelo. Resultado em <pasta>/ia/ (lista.json + QNN.json), o mesmo
formato que o modo manual produz (ver CLAUDE.md).

Requer ANTHROPIC_API_KEY (ou `ant auth login`).

Uso:
    python -m upq.transcrever saida/MCU [--paralelo 8] [--esforco low] [--refazer]
"""

import argparse
import asyncio
import base64
import json
import sys
from pathlib import Path

import anthropic
from pydantic import BaseModel, ValidationError

from . import prompt, topicos
from .modelo import QuestaoIA, schema_json

MODELO = "claude-opus-5-5"
BETAS = ["server-side-fallback-2026-07-01"]


class ItemGabarito(BaseModel):
    numero: int
    letra: str


class Gabarito(BaseModel):
    itens: list[ItemGabarito]


class Classificacao(BaseModel):
    disciplina: str
    topico: str
    assunto: str
    descartados: list[str]
    confiante: bool
    justificativa: str


def imagem(caminho: Path) -> dict:
    return {"type": "image", "source": {
        "type": "base64", "media_type": "image/png",
        "data": base64.standard_b64encode(caminho.read_bytes()).decode()}}


class Motor:
    def __init__(self, pasta: Path, paralelo: int, esforco: str):
        self.pasta = pasta
        self.cliente = anthropic.AsyncAnthropic(max_retries=6)
        self.limite = asyncio.Semaphore(paralelo)
        self.esforco = esforco
        self.uso = {"input_tokens": 0, "output_tokens": 0,
                    "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}
        # Prompt de sistema longo (regras + base de tópicos) fica em cache entre as chamadas.
        self.sistema = [{"type": "text", "text": prompt.SISTEMA,
                         "cache_control": {"type": "ephemeral"}}]

    async def chamar(self, conteudo: list, esquema: type[BaseModel], max_tokens=16000):
        async with self.limite:
            resp = await self.cliente.beta.messages.create(
                model=MODELO,
                max_tokens=max_tokens,
                betas=BETAS,
                fallbacks="default",
                system=self.sistema,
                output_config={"effort": self.esforco,
                               "format": {"type": "json_schema", "schema": schema_json(esquema)}},
                messages=[{"role": "user", "content": conteudo}],
            )
        for k in self.uso:
            self.uso[k] += getattr(resp.usage, k, 0) or 0
        if resp.stop_reason == "refusal":
            raise RuntimeError(f"recusado: {resp.stop_details}")
        if resp.stop_reason == "max_tokens":
            raise RuntimeError("resposta cortada (max_tokens)")
        texto = next(b.text for b in resp.content if b.type == "text")
        return esquema.model_validate_json(texto)

    async def gabarito(self, manifesto: dict) -> dict[str, str]:
        if manifesto.get("gabarito_pdf"):
            return manifesto["gabarito_pdf"]
        if not manifesto.get("pagina_gabarito"):
            return {}
        g = await self.chamar([imagem(self.pasta / manifesto["pagina_gabarito"]),
                               {"type": "text", "text": prompt.GABARITO}], Gabarito, 4000)
        return {f"{i.numero:02d}": i.letra.strip().upper() for i in g.itens}

    async def classificar(self, manifesto: dict) -> Classificacao:
        amostras = "\n".join(
            f"- {q['numero']:02d}: {' '.join(q['texto_pdf'].split()[:40])}"
            for q in manifesto["questoes"])
        texto = prompt.CLASSIFICACAO.format(titulo=manifesto["titulo_lista"], amostras=amostras)
        c = await self.chamar([{"type": "text", "text": texto}], Classificacao, 4000)
        if (c.disciplina, c.topico) not in topicos.carregar():
            raise ValueError(f"par fora da base: {c.disciplina} / {c.topico}")
        return c

    async def questao(self, q: dict, contexto: dict) -> QuestaoIA:
        conteudo = [{"type": "text", "text": "Recorte da questão no PDF:"},
                    imagem(self.pasta / q["imagem"])]
        for f in q["figuras"]:
            conteudo += [{"type": "text", "text": f"Figura {f['nome']}:"},
                         imagem(self.pasta / f["arquivo"])]
        conteudo.append({"type": "text", "text": prompt.mensagem_questao(q, contexto)})
        for tentativa in range(2):
            try:
                r = await self.chamar(conteudo, QuestaoIA)
                if (r.disciplina, r.topico) not in topicos.carregar():
                    raise ValueError(f"par fora da base: {r.disciplina} / {r.topico}")
                return r
            except (ValidationError, ValueError) as e:
                if tentativa:
                    raise
                conteudo.append({"type": "text", "text": f"Atenção, a resposta anterior foi rejeitada: {e}"})


async def executar(pasta: Path, paralelo: int, esforco: str, refazer: bool):
    manifesto = json.loads((pasta / "manifesto.json").read_text(encoding="utf-8"))
    ia = pasta / "ia"
    ia.mkdir(exist_ok=True)
    motor = Motor(pasta, paralelo, esforco)

    arq_lista = ia / "lista.json"
    if refazer or not arq_lista.exists():
        gabarito, classe = await asyncio.gather(
            motor.gabarito(manifesto),
            motor.classificar(manifesto) if manifesto["tipo"] == "lista" else asyncio.sleep(0))
        dados = {"gabarito": gabarito,
                 "classificacao": classe.model_dump() if classe else None}
        arq_lista.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    dados = json.loads(arq_lista.read_text(encoding="utf-8"))
    classe = dados["classificacao"] or {}
    contexto = {"titulo": manifesto["titulo_lista"], "gabarito": dados["gabarito"],
                "disciplina": classe.get("disciplina"), "topico": classe.get("topico")}
    print(f"gabarito: {len(dados['gabarito'])} itens · "
          f"tópico: {classe.get('disciplina')} / {classe.get('topico')}")

    async def uma(q):
        destino = ia / f"Q{q['numero']:02d}.json"
        if destino.exists() and not refazer:
            return "existente"
        try:
            r = await motor.questao(q, contexto)
        except Exception as e:  # registra e segue com as demais
            print(f"  Q{q['numero']:02d}: ERRO {e}", file=sys.stderr)
            return "erro"
        destino.write_text(r.model_dump_json(indent=2), encoding="utf-8")
        print(f"  Q{q['numero']:02d}: ok{' (revisar)' if r.revisar else ''}")
        return "ok"

    resultados = await asyncio.gather(*(uma(q) for q in manifesto["questoes"]))
    print({r: resultados.count(r) for r in set(resultados)})
    print(f"tokens: {motor.uso}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pasta", type=Path, help="pasta gerada por upq.segmentar")
    ap.add_argument("--paralelo", type=int, default=8, help="chamadas simultâneas")
    ap.add_argument("--esforco", default="low", choices=["low", "medium", "high", "xhigh", "max"])
    ap.add_argument("--refazer", action="store_true", help="refaz questões já transcritas")
    args = ap.parse_args()
    asyncio.run(executar(args.pasta, args.paralelo, args.esforco, args.refazer))


if __name__ == "__main__":
    main()
