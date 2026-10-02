"""Monta dist/formula/: leitor de fórmula em imagem → LaTeX (pix2tex / RapidLaTeXOCR) para o artefato.

Publicado junto com a página do importador. O artefato só serve tipos web comuns, então os binários
(runtime wasm e modelos) vão em base64, em pedaços .txt de até 12 MB.

Os modelos ONNX do RapidLaTeXOCR somam ~180 MB; para caber, as constantes são dobradas (otimização
básica do onnxruntime), os pesos grandes ficam em float16 com um Cast para float32 (a conta continua
em float32) e o decoder é quantizado em int8 — a leitura das fórmulas de teste não muda.

Uso (precisa de onnx, onnxruntime e npm só aqui, não no app):
    pip install onnx onnxruntime && python scripts/preparar_formulas.py
"""

import base64
import json
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

import numpy as np
import onnx
import onnxruntime as ort
from onnx import TensorProto, helper, numpy_helper
from onnxruntime.quantization import QuantType, quantize_dynamic

RAIZ = Path(__file__).resolve().parent.parent
DESTINO = RAIZ / "dist" / "formula"
MODELOS = "https://github.com/RapidAI/RapidLaTeXOCR/releases/download/v0.0.0"
ORT_WEB = "onnxruntime-web@1.30.0"
PEDACO = 12 * 1024 * 1024


def baixar(nome: str, pasta: Path) -> Path:
    destino = pasta / nome
    if not destino.exists():
        print("baixando", nome)
        urllib.request.urlretrieve(f"{MODELOS}/{nome}", destino)
    return destino


def dobrar(origem: Path, destino: Path) -> None:
    so = ort.SessionOptions()
    so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_BASIC
    so.optimized_model_filepath = str(destino)
    ort.InferenceSession(str(origem), so, providers=["CPUExecutionProvider"])


def pesos_float16(origem: Path, destino: Path) -> None:
    m = onnx.load(origem)
    g = m.graph
    novos, casts = [], []
    for t in list(g.initializer):
        if t.data_type == TensorProto.FLOAT and int(np.prod(t.dims or [1])) >= 1024:
            h = numpy_helper.from_array(numpy_helper.to_array(t).astype(np.float16), t.name + "__f16")
            novos.append(h)
            casts.append(helper.make_node("Cast", [h.name], [t.name], to=TensorProto.FLOAT, name=t.name + "__cast"))
            g.initializer.remove(t)
    g.initializer.extend(novos)
    for n in reversed(casts):
        g.node.insert(0, n)
    onnx.save(m, destino)


def em_pedacos(dados: bytes, nome: str) -> int:
    b64 = base64.b64encode(dados).decode()
    partes = [b64[i:i + PEDACO] for i in range(0, len(b64), PEDACO)]
    for k, p in enumerate(partes, 1):
        (DESTINO / f"{nome}.{k}.txt").write_text(p)
    return len(partes)


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        DESTINO.mkdir(parents=True, exist_ok=True)
        for velho in DESTINO.glob("*"):
            velho.unlink()
        manifesto = {}
        for nome in ("image_resizer", "encoder"):
            dobrar(baixar(f"{nome}.onnx", tmp), tmp / f"{nome}.opt.onnx")
            pesos_float16(tmp / f"{nome}.opt.onnx", tmp / f"{nome}.f16.onnx")
            chave = "resizer" if nome == "image_resizer" else nome
            manifesto[chave] = em_pedacos((tmp / f"{nome}.f16.onnx").read_bytes(), chave)
        quantize_dynamic(str(baixar("decoder.onnx", tmp)), str(tmp / "decoder.q8.onnx"), weight_type=QuantType.QUInt8)
        manifesto["decoder"] = em_pedacos((tmp / "decoder.q8.onnx").read_bytes(), "decoder")
        shutil.copy(baixar("tokenizer.json", tmp), DESTINO / "tokenizer.json")
        subprocess.run(["npm", "init", "-y"], cwd=tmp, check=True, capture_output=True)
        subprocess.run(["npm", "install", "--silent", ORT_WEB], cwd=tmp, check=True)
        dist = tmp / "node_modules" / "onnxruntime-web" / "dist"
        shutil.copy(dist / "ort.wasm.bundle.min.mjs", DESTINO / "ort.bundle.js")
        manifesto["ort.wasm"] = em_pedacos((dist / "ort-wasm-simd-threaded.wasm").read_bytes(), "ort.wasm")
        (DESTINO / "manifesto.json").write_text(json.dumps(manifesto))
    total = sum(p.stat().st_size for p in DESTINO.iterdir())
    print(f"{DESTINO}: {len(list(DESTINO.iterdir()))} arquivos, {total / 1e6:.1f} MB · {manifesto}")


if __name__ == "__main__":
    sys.exit(main())
