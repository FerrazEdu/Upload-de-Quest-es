"""App web local: envio de PDFs, banco geral de questões e listas virtuais.

    python -m upq.web                   # abre em http://localhost:8000
    python -m upq.web --porta 8080
    python -m upq.web --demo demo.html  # HTML único, sem servidor, com os dados de saida/

Só usa a biblioteca padrão. Modelo de dados (igual ao do Supabase):

  - cada PDF enviado é uma importação: vai para entrada/ e passa pelo fluxo
    (recorte → transcrição → validação), com o resultado em saida/<nome>/;
  - as questões de todas as importações formam o BANCO GERAL;
  - LISTAS são virtuais: apontam para questões do banco, em ordem. Cada importação
    ganha a sua lista padrão ("Lista de <título>"); outras são montadas por filtro.
    Ficam em saida/_listas.json.

Sem ANTHROPIC_API_KEY a importação para em "Aguardando transcrição" (ver CLAUDE.md).
"""

import argparse
import asyncio
import base64
import io
import json
import mimetypes
import os
import re
import threading
import traceback
import uuid
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

from . import montar, segmentar, validar

RAIZ = Path(__file__).resolve().parent
PAGINA = RAIZ / "web" / "app.html"
SAIDA = Path(os.environ.get("UPQ_SAIDA", "saida"))
ENTRADA = Path(os.environ.get("UPQ_ENTRADA", "entrada"))
CABECA = ('<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
          '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">')

ENVIOS: dict[str, dict] = {}
TRAVA = threading.Lock()


def agora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------- banco geral (importações)

def importacoes_prontas() -> list[Path]:
    """Pastas de saida/ com a transcrição completa."""
    if not SAIDA.exists():
        return []
    prontas = []
    for p in sorted(SAIDA.iterdir()):
        if not (p / "transcricao.json").exists() or not (p / "manifesto.json").exists():
            continue
        total = json.loads((p / "manifesto.json").read_text(encoding="utf-8"))["total_questoes"]
        if len(list((p / "ia").glob("Q*.json"))) >= total:
            prontas.append(p)
    return prontas


_cache_validacao: dict[str, tuple[float, dict]] = {}


def questoes_da_importacao(pasta: Path) -> list[dict]:
    """Questões completas de uma importação, com id estável e o resultado da validação."""
    marca = (pasta / "transcricao.json").stat().st_mtime
    em_cache = _cache_validacao.get(pasta.name)
    if not em_cache or em_cache[0] != marca:
        lista, res = validar.validar(pasta)
        questoes = []
        for q in lista.questoes:
            v = res.get(q.numero, {"erros": [], "avisos": []})
            questoes.append({**q.model_dump(), "id": f"{pasta.name}/{q.numero:02d}", "origem": pasta.name,
                             "hash_pdf": lista.hash_pdf, "lista_origem": lista.titulo,
                             "erros": v["erros"], "avisos": v["avisos"]})
        _cache_validacao[pasta.name] = (marca, {"lista": lista, "questoes": questoes})
    return _cache_validacao[pasta.name][1]["questoes"]


def banco() -> list[dict]:
    return [q for p in importacoes_prontas() for q in questoes_da_importacao(p)]


def resumo_questao(q: dict) -> dict:
    """Campos leves para a tabela do banco e para os filtros."""
    texto = re.sub(r"!\[[^\]]*\]\([^)]*\)|[$*_#>|\\]", " ", q["enunciado"])
    return {k: q[k] for k in ("id", "origem", "numero", "titulo", "instituicao", "ano", "disciplina",
                              "topico", "assuntos", "dificuldade", "etapa", "lista_origem")} | {
        "busca": " ".join(texto.split())[:400], "erros": len(q["erros"]), "avisos": len(q["avisos"])}


def questao_por_id(qid: str) -> dict:
    origem = qid.split("/", 1)[0]
    pasta = (SAIDA / origem).resolve()
    if pasta.parent != SAIDA.resolve():
        raise FileNotFoundError(qid)
    for q in questoes_da_importacao(pasta):
        if q["id"] == qid:
            return q
    raise FileNotFoundError(qid)


# ---------------------------------------------------------------- listas virtuais

ARQ_LISTAS = lambda: SAIDA / "_listas.json"  # noqa: E731


def ler_listas() -> dict:
    try:
        return json.loads(ARQ_LISTAS().read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"listas": [], "origens": []}


def gravar_listas(dados: dict):
    SAIDA.mkdir(parents=True, exist_ok=True)
    tmp = ARQ_LISTAS().with_suffix(".tmp")
    tmp.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(ARQ_LISTAS())


def garantir_listas_padrao(dados: dict) -> dict:
    """Cada importação pronta ganha uma lista padrão uma única vez (se for excluída, não volta)."""
    for pasta in importacoes_prontas():
        if pasta.name in dados["origens"]:
            continue
        qs = questoes_da_importacao(pasta)
        meta = _cache_validacao[pasta.name][1]["lista"]
        dados["listas"].append({
            "id": str(uuid.uuid4()), "nome": meta.nome, "descricao": meta.descricao,
            "disciplina": meta.disciplina, "topico": meta.topico, "tags": meta.tags,
            "status": "rascunho", "origem": pasta.name, "id_banco": None,
            "questoes": [q["id"] for q in qs], "criado_em": agora(), "atualizado_em": agora()})
        dados["origens"].append(pasta.name)
    return dados


def listas_atuais() -> dict:
    with TRAVA:
        dados = ler_listas()
        antes = len(dados["origens"])
        dados = garantir_listas_padrao(dados)
        if len(dados["origens"]) != antes:
            gravar_listas(dados)
        return dados


def resumo_lista(lista: dict, indice: dict) -> dict:
    qs = [indice[i] for i in lista["questoes"] if i in indice]
    return {k: lista[k] for k in ("id", "nome", "descricao", "disciplina", "topico", "tags", "status", "origem")} | {
        "total_questoes": len(qs), "faltando": len(lista["questoes"]) - len(qs),
        "erros": sum(q["erros"] > 0 for q in qs), "avisos": sum(q["avisos"] > 0 for q in qs),
        "enviada": bool(lista.get("enviada_em")), "atualizado_em": lista["atualizado_em"]}


def salvar_lista_local(lista_id: str | None, dados_novos: dict) -> dict:
    campos = {k: dados_novos[k] for k in ("nome", "descricao", "disciplina", "topico", "tags", "questoes", "status")
              if k in dados_novos}
    if "nome" in campos and not str(campos["nome"]).strip():
        raise ValueError("Dê um nome para a lista.")
    if "questoes" in campos:
        campos["questoes"] = list(dict.fromkeys(campos["questoes"]))  # sem repetição, na ordem
    with TRAVA:
        dados = ler_listas()
        if lista_id is None:
            lista = {"id": str(uuid.uuid4()), "nome": "Nova lista", "descricao": "", "disciplina": None,
                     "topico": None, "tags": [], "status": "rascunho", "origem": None, "id_banco": None,
                     "questoes": [], "criado_em": agora()}
            dados["listas"].append(lista)
        else:
            lista = next((l for l in dados["listas"] if l["id"] == lista_id), None)
            if not lista:
                raise FileNotFoundError(lista_id)
        lista.update(campos, atualizado_em=agora())
        gravar_listas(dados)
        return lista


def excluir_lista_local(lista_id: str):
    with TRAVA:
        dados = ler_listas()
        dados["listas"] = [l for l in dados["listas"] if l["id"] != lista_id]
        gravar_listas(dados)


# ---------------------------------------------------------------- processamento de um PDF

def processar(job_id: str, pdf: Path):
    job = ENVIOS[job_id]
    pasta = SAIDA / pdf.stem

    def passo(etapa, mensagem, estado="rodando"):
        with TRAVA:
            job.update(etapa=etapa, mensagem=mensagem, estado=estado)

    try:
        passo(0, "Recortando questões e figuras…")
        m = segmentar.segmentar(pdf, pasta)
        job["origem"] = pasta.name
        transcritas = len(list((pasta / "ia").glob("Q*.json"))) if (pasta / "ia").exists() else 0
        if (pasta / "ia" / "lista.json").exists() and transcritas >= m["total_questoes"]:
            pass  # já transcrita antes (reenvio do mesmo PDF): segue para a validação
        elif not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
            passo(1, f"{m['total_questoes']} questões recortadas. Sem chave de API: transcreva pelo "
                     "Claude Code (CLAUDE.md) e as questões entram no banco.", "parado")
            return
        else:
            passo(1, f"Transcrevendo {m['total_questoes']} questões com a IA…")
            from . import transcrever
            asyncio.run(transcrever.executar(pasta, paralelo=8, esforco="low", refazer=False))
        passo(2, "Validando LaTeX, figuras e base de tópicos…")
        montar.montar(pasta)
        _, res = validar.validar(pasta)
        erros, avisos = validar.resumo(res)
        dados = listas_atuais()
        job["lista"] = next((l["id"] for l in dados["listas"] if l["origem"] == pasta.name), None)
        passo(3, f"{m['total_questoes']} questões no banco · {erros} erro(s) e {avisos} aviso(s) para revisar.",
              "concluido")
    except Exception as e:  # mostra o erro na tela de envio
        traceback.print_exc()
        passo(job.get("etapa", 0), f"Falhou: {e}", "falhou")


def enviar_ao_banco(lista_id: str) -> str:
    """Envia ao Supabase as importações usadas pela lista e depois a própria lista."""
    from . import enviar
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    chave = os.environ.get("SUPABASE_SECRET_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not chave:
        raise RuntimeError("Defina SUPABASE_URL e SUPABASE_SECRET_KEY antes de iniciar o app.")
    lista = next((l for l in listas_atuais()["listas"] if l["id"] == lista_id), None)
    if not lista:
        raise FileNotFoundError(lista_id)
    qs = [questao_por_id(i) for i in lista["questoes"]]
    if any(q["erros"] for q in qs):
        raise RuntimeError("Há questões com erro de validação nesta lista; corrija antes de enviar.")
    id_banco = lista.get("id_banco")
    for origem in dict.fromkeys(q["origem"] for q in qs):
        id_padrao = enviar.enviar(SAIDA / origem, url, chave)  # idempotente (hash do PDF)
        if origem == lista.get("origem"):
            id_banco = id_padrao  # a lista padrão da importação já existe no banco com esse id
    id_banco = enviar.salvar_lista(url, chave, {
        "id": id_banco or lista["id"], "nome": lista["nome"], "descricao": lista["descricao"],
        "disciplina": lista["disciplina"], "topico": lista["topico"], "tags": lista["tags"],
        "status": lista["status"], "questoes": [{"hash_pdf": q["hash_pdf"], "numero": q["numero"]} for q in qs]})
    with TRAVA:
        dados = ler_listas()
        for l in dados["listas"]:
            if l["id"] == lista_id:
                l.update(id_banco=id_banco, enviada_em=agora())
        gravar_listas(dados)
    return id_banco


# ---------------------------------------------------------------- HTTP

class App(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def responder(self, dados, status=HTTPStatus.OK):
        corpo = json.dumps(dados, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def corpo_json(self) -> dict:
        tamanho = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(tamanho) or b"{}")

    def tratar(self, metodo: str):
        try:
            rota = self.path.split("?", 1)[0]
            resposta = self.rotear(metodo, rota)
            if resposta is not None:
                self.responder(*resposta) if isinstance(resposta, tuple) else self.responder(resposta)
        except FileNotFoundError as e:
            self.responder({"erro": f"não encontrado: {e}"}, HTTPStatus.NOT_FOUND)
        except ValueError as e:
            self.responder({"erro": str(e)}, HTTPStatus.BAD_REQUEST)
        except Exception as e:
            traceback.print_exc()
            self.responder({"erro": str(e)}, HTTPStatus.INTERNAL_SERVER_ERROR)

    do_GET = lambda self: self.tratar("GET")        # noqa: E731
    do_POST = lambda self: self.tratar("POST")      # noqa: E731
    do_PUT = lambda self: self.tratar("PUT")        # noqa: E731
    do_DELETE = lambda self: self.tratar("DELETE")  # noqa: E731

    def rotear(self, metodo: str, rota: str):
        if metodo == "GET" and rota in ("/", "/index.html"):
            return self.arquivo((CABECA + "</head><body>" + PAGINA.read_text(encoding="utf-8")
                                 + "</body></html>").encode(), "text/html; charset=utf-8")
        if metodo == "GET" and rota == "/api/banco":
            return {"questoes": [resumo_questao(q) for q in banco()]}
        if metodo == "GET" and (m := re.fullmatch(r"/api/questoes/(.+)", rota)):
            return questao_por_id(unquote(m.group(1)))
        if metodo == "GET" and (m := re.fullmatch(r"/api/arquivos/([^/]+)/(.+)", rota)):
            pasta = (SAIDA / unquote(m.group(1))).resolve()
            arq = (pasta / unquote(m.group(2))).resolve()
            if pasta.parent != SAIDA.resolve() or pasta not in arq.parents or not arq.is_file():
                raise FileNotFoundError(m.group(2))
            return self.arquivo(arq.read_bytes(), mimetypes.guess_type(arq.name)[0] or "application/octet-stream")
        if rota == "/api/listas" and metodo == "GET":
            indice = {q["id"]: resumo_questao(q) for q in banco()}
            return {"listas": [resumo_lista(l, indice) for l in listas_atuais()["listas"]]}
        if rota == "/api/listas" and metodo == "POST":
            return salvar_lista_local(None, self.corpo_json()), HTTPStatus.CREATED
        if m := re.fullmatch(r"/api/listas/([^/]+)", rota):
            lista_id = unquote(m.group(1))
            if metodo == "GET":
                lista = next((l for l in listas_atuais()["listas"] if l["id"] == lista_id), None)
                if not lista:
                    raise FileNotFoundError(lista_id)
                indice = {q["id"]: resumo_questao(q) for q in banco()}
                return {"lista": lista, "resumo": resumo_lista(lista, indice),
                        "questoes": [indice[i] for i in lista["questoes"] if i in indice]}
            if metodo == "PUT":
                return salvar_lista_local(lista_id, self.corpo_json())
            if metodo == "DELETE":
                excluir_lista_local(lista_id)
                return {"ok": True}
        if metodo == "POST" and (m := re.fullmatch(r"/api/listas/([^/]+)/enviar", rota)):
            return {"id_banco": enviar_ao_banco(unquote(m.group(1)))}
        if rota == "/api/envios" and metodo == "GET":
            with TRAVA:
                return {"envios": sorted(ENVIOS.values(), key=lambda e: -e["ordem"])}
        if rota == "/api/envios" and metodo == "POST":
            return self.receber_pdf()
        raise FileNotFoundError(rota)

    def arquivo(self, corpo: bytes, tipo: str):
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def receber_pdf(self):
        nome = Path(unquote(self.headers.get("X-Nome-Arquivo", "lista.pdf"))).name
        if not nome.lower().endswith(".pdf") or nome.startswith((".", "_")):
            raise ValueError("Envie um arquivo .pdf.")
        dados = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        if not dados.startswith(b"%PDF"):
            raise ValueError(f"{nome} não é um PDF válido.")
        ENTRADA.mkdir(parents=True, exist_ok=True)
        pdf = ENTRADA / nome
        pdf.write_bytes(dados)
        job_id = uuid.uuid4().hex[:8]
        with TRAVA:
            ENVIOS[job_id] = {"id": job_id, "arquivo": nome, "etapa": 0, "estado": "rodando",
                              "mensagem": "Na fila…", "origem": None, "lista": None, "ordem": len(ENVIOS)}
        threading.Thread(target=processar, args=(job_id, pdf), daemon=True).start()
        return ENVIOS[job_id], HTTPStatus.ACCEPTED


# ---------------------------------------------------------------- demonstração em arquivo único

def gerar_demo(destino: Path):
    """HTML único com o banco e as listas embutidos (figuras e recortes como data: URI)."""
    try:
        from PIL import Image
    except ImportError:
        Image = None

    def data_uri(arq: Path, jpeg: bool) -> str:
        if jpeg and Image:  # recortes viram JPEG para o arquivo ficar leve
            buf = io.BytesIO()
            img = Image.open(arq).convert("RGB")
            img.thumbnail((1100, 1600))
            img.save(buf, "JPEG", quality=82)
            return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
        return "data:image/png;base64," + base64.b64encode(arq.read_bytes()).decode()

    questoes = banco()
    arquivos: dict[str, dict] = {}
    for q in questoes:
        a = arquivos.setdefault(q["origem"], {})
        a[q["imagem"]] = data_uri(SAIDA / q["origem"] / q["imagem"], jpeg=True)
        for f in q["figuras"]:
            a[f["arquivo"]] = data_uri(SAIDA / q["origem"] / f["arquivo"], jpeg=False)
    listas = listas_atuais()["listas"]
    if not any(l["origem"] is None for l in listas):  # mostra também uma lista virtual montada por filtro
        dificeis = [q for q in questoes if q["dificuldade"] >= 4]
        listas.append({"id": "exemplo-dificeis", "nome": "Exemplo: questões difíceis",
                       "descricao": "Lista virtual de exemplo: filtro de dificuldade Difícil e Muito Difícil",
                       "disciplina": None, "topico": None,
                       "tags": list(dict.fromkeys(a for q in dificeis for a in q["assuntos"])),
                       "status": "rascunho", "origem": None, "questoes": [q["id"] for q in dificeis]})
    dados = json.dumps({"questoes": questoes, "listas": listas, "arquivos": arquivos},
                       ensure_ascii=False).replace("</", "<\\/")
    html = PAGINA.read_text(encoding="utf-8")
    html = html.replace("<script>\nconst DEMO", f"<script>window.UPQ_DEMO = {dados};</script>\n<script>\nconst DEMO", 1)
    destino.write_text(html, encoding="utf-8")
    return destino


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--porta", type=int, default=8000)
    ap.add_argument("--demo", type=Path, help="gera um HTML de demonstração em vez de abrir o servidor")
    args = ap.parse_args()
    if args.demo:
        print(gerar_demo(args.demo))
        return
    servidor = ThreadingHTTPServer(("127.0.0.1", args.porta), App)
    print(f"Importador de Questões em http://localhost:{args.porta}  (Ctrl+C para sair)")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
