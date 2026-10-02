"""App web local: tela de envio de PDFs e tela das listas cadastradas.

    python -m upq.web                 # abre em http://localhost:8000
    python -m upq.web --porta 8080
    python -m upq.web --demo demo.html  # gera um HTML único, sem servidor, com as listas de saida/

Só usa a biblioteca padrão. Cada PDF enviado vai para entrada/ e passa pelo fluxo
(recorte → transcrição → validação) numa thread; o resultado fica em saida/<nome>/.
Sem ANTHROPIC_API_KEY o fluxo para em "Aguardando transcrição" (ver CLAUDE.md).
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


# ---------------------------------------------------------------- dados das listas

def resumo_lista(pasta: Path) -> dict | None:
    """Situação de uma pasta de saida/ para a tabela de listas."""
    manifesto_arq = pasta / "manifesto.json"
    if not manifesto_arq.exists():
        return None
    manifesto = json.loads(manifesto_arq.read_text(encoding="utf-8"))
    base = {"id": pasta.name, "nome": f"Lista de {manifesto['titulo_lista']}",
            "descricao": f"Lista completa de {manifesto['titulo_lista']}",
            "total_questoes": manifesto["total_questoes"], "disciplina": None, "topico": None,
            "tags": [], "erros": 0, "avisos": 0}
    ia = pasta / "ia"
    feitas = len(list(ia.glob("Q*.json"))) if ia.exists() else 0
    if not (pasta / "transcricao.json").exists() or feitas < manifesto["total_questoes"]:
        return {**base, "status": "aguardando_transcricao"}
    lista, res = validar.validar(pasta)
    erros, avisos = validar.resumo(res)
    status = ("enviada" if (pasta / "enviada.json").exists() else
              "com_erros" if erros else "revisar" if avisos else "pronta")
    return {**base, "nome": lista.nome, "descricao": lista.descricao, "disciplina": lista.disciplina,
            "topico": lista.topico, "tags": lista.tags, "erros": erros, "avisos": avisos,
            "status": status}


def todas_listas() -> list[dict]:
    if not SAIDA.exists():
        return []
    resumos = [resumo_lista(p) for p in sorted(SAIDA.iterdir()) if p.is_dir()]
    return [r for r in resumos if r]


def detalhe_lista(pasta: Path) -> dict:
    resumo = resumo_lista(pasta)
    if not resumo or resumo["status"] == "aguardando_transcricao":
        raise FileNotFoundError("lista ainda sem transcrição")
    lista, res = validar.validar(pasta)
    return {"resumo": resumo, "lista": {**lista.model_dump(), "id": pasta.name},
            "validacao": {str(k): v for k, v in res.items()}}


# ---------------------------------------------------------------- processamento

def processar(job_id: str, pdf: Path):
    job = ENVIOS[job_id]
    pasta = SAIDA / pdf.stem

    def passo(etapa, mensagem, estado="rodando"):
        with TRAVA:
            job.update(etapa=etapa, mensagem=mensagem, estado=estado)

    try:
        passo(0, "Recortando questões e figuras…")
        m = segmentar.segmentar(pdf, pasta)
        job["lista"] = pasta.name
        transcritas = len(list((pasta / "ia").glob("Q*.json"))) if (pasta / "ia").exists() else 0
        if (pasta / "ia" / "lista.json").exists() and transcritas >= m["total_questoes"]:
            pass  # já transcrita antes (reenvio do mesmo PDF): segue para a validação
        elif not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
            passo(1, f"{m['total_questoes']} questões recortadas. Sem chave de API: transcreva pelo "
                     "Claude Code (CLAUDE.md) e a lista aparece em Listas.", "parado")
            return
        else:
            passo(1, f"Transcrevendo {m['total_questoes']} questões com a IA…")
            from . import transcrever
            asyncio.run(transcrever.executar(pasta, paralelo=8, esforco="low", refazer=False))
        passo(2, "Validando LaTeX, figuras e base de tópicos…")
        montar.montar(pasta)
        _, res = validar.validar(pasta)
        erros, avisos = validar.resumo(res)
        passo(3, f"Pronta: {erros} erro(s) e {avisos} aviso(s) para revisar.", "concluido")
    except Exception as e:  # mostra o erro na tela de envio
        traceback.print_exc()
        passo(job.get("etapa", 0), f"Falhou: {e}", "falhou")


def enviar_ao_banco(pasta: Path) -> str:
    from . import enviar
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    chave = os.environ.get("SUPABASE_SECRET_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not chave:
        raise RuntimeError("Defina SUPABASE_URL e SUPABASE_SECRET_KEY antes de iniciar o app.")
    _, res = validar.validar(pasta)
    if validar.resumo(res)[0]:
        raise RuntimeError("A lista tem erros de validação; corrija antes de enviar.")
    lista_id = enviar.enviar(pasta, url, chave)
    (pasta / "enviada.json").write_text(json.dumps({"lista_id": lista_id}), encoding="utf-8")
    return lista_id


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

    def pasta(self, nome: str) -> Path:
        p = (SAIDA / unquote(nome)).resolve()
        if p.parent != SAIDA.resolve() or not p.is_dir():
            raise FileNotFoundError(nome)
        return p

    def do_GET(self):
        try:
            if self.path in ("/", "/index.html"):
                corpo = (CABECA + "</head><body>" + PAGINA.read_text(encoding="utf-8") + "</body></html>").encode()
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(corpo)))
                self.end_headers()
                self.wfile.write(corpo)
            elif self.path == "/api/listas":
                self.responder({"listas": todas_listas()})
            elif self.path == "/api/envios":
                with TRAVA:
                    self.responder({"envios": sorted(ENVIOS.values(), key=lambda e: -e["ordem"])})
            elif m := re.fullmatch(r"/api/listas/([^/]+)/arquivos/(.+)", self.path):
                pasta = self.pasta(m.group(1))
                arq = (pasta / unquote(m.group(2))).resolve()
                if pasta not in arq.parents or not arq.is_file():
                    raise FileNotFoundError(m.group(2))
                corpo = arq.read_bytes()
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", mimetypes.guess_type(arq.name)[0] or "application/octet-stream")
                self.send_header("Content-Length", str(len(corpo)))
                self.end_headers()
                self.wfile.write(corpo)
            elif m := re.fullmatch(r"/api/listas/([^/]+)", self.path):
                self.responder(detalhe_lista(self.pasta(m.group(1))))
            else:
                self.responder({"erro": "não encontrado"}, HTTPStatus.NOT_FOUND)
        except FileNotFoundError as e:
            self.responder({"erro": f"não encontrado: {e}"}, HTTPStatus.NOT_FOUND)
        except Exception as e:
            traceback.print_exc()
            self.responder({"erro": str(e)}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_POST(self):
        try:
            if self.path == "/api/envios":
                nome = Path(unquote(self.headers.get("X-Nome-Arquivo", "lista.pdf"))).name
                if not nome.lower().endswith(".pdf"):
                    return self.responder({"erro": "envie um arquivo .pdf"}, HTTPStatus.BAD_REQUEST)
                tamanho = int(self.headers.get("Content-Length", 0))
                dados = self.rfile.read(tamanho)
                if not dados.startswith(b"%PDF"):
                    return self.responder({"erro": f"{nome} não é um PDF válido"}, HTTPStatus.BAD_REQUEST)
                ENTRADA.mkdir(parents=True, exist_ok=True)
                pdf = ENTRADA / nome
                pdf.write_bytes(dados)
                job_id = uuid.uuid4().hex[:8]
                with TRAVA:
                    ENVIOS[job_id] = {"id": job_id, "arquivo": nome, "etapa": 0, "estado": "rodando",
                                      "mensagem": "Na fila…", "lista": None, "ordem": len(ENVIOS)}
                threading.Thread(target=processar, args=(job_id, pdf), daemon=True).start()
                self.responder(ENVIOS[job_id], HTTPStatus.ACCEPTED)
            elif m := re.fullmatch(r"/api/listas/([^/]+)/enviar", self.path):
                self.responder({"lista_id": enviar_ao_banco(self.pasta(m.group(1)))})
            else:
                self.responder({"erro": "não encontrado"}, HTTPStatus.NOT_FOUND)
        except Exception as e:
            traceback.print_exc()
            self.responder({"erro": str(e)}, HTTPStatus.BAD_REQUEST)


# ---------------------------------------------------------------- demonstração em arquivo único

def gerar_demo(destino: Path, pastas: list[Path]):
    """HTML único com as listas embutidas (figuras e recortes como data: URI), sem servidor."""
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

    listas, arquivos = [], {}
    for pasta in pastas:
        d = detalhe_lista(pasta)
        listas.append(d)
        arquivos[pasta.name] = {}
        for q in d["lista"]["questoes"]:
            arquivos[pasta.name][q["imagem"]] = data_uri(pasta / q["imagem"], jpeg=True)
            for f in q["figuras"]:
                arquivos[pasta.name][f["arquivo"]] = data_uri(pasta / f["arquivo"], jpeg=False)
    dados = json.dumps({"listas": listas, "arquivos": arquivos}, ensure_ascii=False).replace("</", "<\\/")
    html = PAGINA.read_text(encoding="utf-8")
    html = html.replace("<script>\nconst DEMO", f"<script>window.UPQ_DEMO = {dados};</script>\n<script>\nconst DEMO", 1)
    destino.write_text(html, encoding="utf-8")
    return destino


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--porta", type=int, default=8000)
    ap.add_argument("--demo", type=Path, help="gera um HTML de demonstração em vez de abrir o servidor")
    ap.add_argument("--listas", type=Path, nargs="*", help="pastas para a demonstração (padrão: todas de saida/)")
    args = ap.parse_args()
    if args.demo:
        pastas = args.listas or [p for p in sorted(SAIDA.iterdir()) if (p / "transcricao.json").exists()]
        print(gerar_demo(args.demo, pastas))
        return
    servidor = ThreadingHTTPServer(("127.0.0.1", args.porta), App)
    print(f"Importador de Questões em http://localhost:{args.porta}  (Ctrl+C para sair)")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
