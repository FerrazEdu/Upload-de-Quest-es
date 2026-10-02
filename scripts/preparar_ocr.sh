#!/usr/bin/env bash
# Baixa o Tesseract (OCR) e monta dist/ocr/, publicado junto com o artefato do importador.
# O artefato não serve .gz: os dados do português vão como script (por-dados.js, base64).
set -euo pipefail
cd "$(dirname "$0")/.."
tmp=$(mktemp -d)
(cd "$tmp" && npm init -y >/dev/null && npm install --silent tesseract.js@7.0.0 tesseract.js-core @tesseract.js-data/por)
mkdir -p dist/ocr
n="$tmp/node_modules"
cp "$n/tesseract.js/dist/tesseract.min.js" "$n/tesseract.js/dist/worker.min.js" dist/ocr/
cp "$n/tesseract.js-core/tesseract-core-lstm.wasm.js" "$n/tesseract.js-core/tesseract-core-simd-lstm.wasm.js" \
   "$n/tesseract.js-core/tesseract-core-relaxedsimd-lstm.wasm.js" dist/ocr/
python3 - "$n/@tesseract.js-data/por/4.0.0_best_int/por.traineddata.gz" <<'PY'
import base64, sys, pathlib
dados = pathlib.Path(sys.argv[1]).read_bytes()
pathlib.Path("dist/ocr/por-dados.js").write_text('self.UPQ_POR_TRAINEDDATA_GZ_B64 = "' + base64.b64encode(dados).decode() + '";\n')
PY
rm -rf "$tmp"
ls -la dist/ocr
