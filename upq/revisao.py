"""Gera revisao.html: original do PDF à esquerda, questão renderizada (Markdown +
LaTeX + figuras) à direita, com erros e avisos da validação. Abra no navegador.

Uso:
    python -m upq.revisao saida/MCU
"""

import json
import sys
from pathlib import Path

from .validar import resumo, validar

PAGINA = r"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Revisão — __TITULO__</title>
<script src="https://cdn.jsdelivr.net/npm/marked@12/marked.min.js"></script>
<script>
MathJax = {tex: {inlineMath: [['$', '$']], displayMath: [['$$', '$$']], processEscapes: true},
           options: {ignoreHtmlClass: 'sem-tex'}};
</script>
<script src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-chtml.js" async></script>
<style>
:root{--fundo:#f5f4f0;--cartao:#fff;--borda:#ddd8cc;--texto:#1f1d1a;--suave:#6b665c;
--certa:#e3f3e3;--erro:#fde8e6;--erro-b:#c8382c;--aviso:#fff4dd;--aviso-b:#d39a1c;--acento:#b3261e}
@media (prefers-color-scheme:dark){:root{--fundo:#1b1a18;--cartao:#252320;--borda:#3a3732;
--texto:#ece8e0;--suave:#a39d92;--certa:#1f3a22;--erro:#3d1f1c;--aviso:#3a3020}}
*{box-sizing:border-box}
body{margin:0;font:15px/1.55 system-ui,sans-serif;background:var(--fundo);color:var(--texto)}
header.topo{position:sticky;top:0;z-index:2;background:var(--cartao);border-bottom:1px solid var(--borda);
padding:12px 16px;display:flex;flex-wrap:wrap;gap:12px;align-items:center;justify-content:space-between}
header.topo h1{font-size:17px;margin:0}
.filtros button{border:1px solid var(--borda);background:var(--fundo);color:var(--texto);border-radius:6px;
padding:5px 10px;cursor:pointer;font:inherit;font-size:13px}
.filtros button.ativo{background:var(--acento);border-color:var(--acento);color:#fff}
main{max-width:1400px;margin:0 auto;padding:16px}
.q{background:var(--cartao);border:1px solid var(--borda);border-radius:10px;margin:0 0 18px;overflow:hidden}
.q>.cab{display:flex;flex-wrap:wrap;gap:6px 14px;align-items:baseline;padding:10px 16px;border-bottom:1px solid var(--borda)}
.q>.cab b{font-size:16px}.meta{color:var(--suave);font-size:13px}
.selo{font-size:12px;padding:1px 8px;border-radius:99px;border:1px solid var(--borda)}
.selo.erro{background:var(--erro);border-color:var(--erro-b)}.selo.aviso{background:var(--aviso);border-color:var(--aviso-b)}
.corpo{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.25fr)}
@media (max-width:900px){.corpo{grid-template-columns:1fr}}
.orig{padding:12px;border-right:1px solid var(--borda);background:var(--fundo)}
.orig img{width:100%;height:auto;border-radius:4px;background:#fff}
.render{padding:12px 18px;min-width:0}
.render img{max-width:100%;height:auto;display:block;margin:8px auto;border-radius:4px}
.render table{border-collapse:collapse;margin:8px 0}.render td,.render th{border:1px solid var(--borda);padding:4px 8px}
ol.alts{list-style:none;padding:0;margin:10px 0}
ol.alts li{display:flex;gap:8px;padding:4px 8px;border-radius:6px}ol.alts li p{margin:0}
ol.alts li.certa{background:var(--certa)}
ol.alts .l{font-weight:700;min-width:1.4em}
.msgs{margin:0;padding:8px 16px 8px 34px;font-size:13px}
.msgs.erro{background:var(--erro)}.msgs.aviso{background:var(--aviso)}
details{margin-top:10px;border-top:1px dashed var(--borda);padding-top:8px}
summary{cursor:pointer;font-weight:600}
mjx-container{overflow-x:auto;overflow-y:hidden;max-width:100%}
</style></head><body>
<header class="topo">
  <h1>__TITULO__ <span class="meta">· __RESUMO__</span></h1>
  <div class="filtros">
    <button data-f="todas" class="ativo">Todas</button>
    <button data-f="erro">Com erro</button>
    <button data-f="aviso">Com aviso</button>
  </div>
</header>
<main id="lista"></main>
<script id="dados" type="application/json">__DADOS__</script>
<script>
const D = JSON.parse(document.getElementById('dados').textContent);

// Protege o LaTeX do Markdown (sublinhados e asteriscos dentro das fórmulas).
function md(texto, figuras) {
  const guardadas = [];
  let t = texto.replace(/\\\$/g, '\u0001')
    .replace(/\$\$[\s\S]+?\$\$|\$[^$\n]+?\$/g, m => { guardadas.push(m); return `\u0002${guardadas.length - 1}\u0002`; })
    .replace(/\(figura:([A-Za-z0-9_]+)\)/g, (m, n) => `(${figuras[n] || n})`);
  let html = marked.parse(t);
  return html.replace(/\u0002(\d+)\u0002/g, (m, i) => guardadas[+i].replace(/</g, '&lt;'))
             .replace(/\u0001/g, '\\$');
}
const esc = s => String(s ?? '').replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));

const main = document.getElementById('lista');
for (const q of D.questoes) {
  const v = D.validacao[q.numero] || {erros: [], avisos: []};
  const figs = Object.fromEntries(q.figuras.map(f => [f.nome, f.url || f.arquivo]));
  const alts = Object.entries(q.alternativas).map(([l, t]) =>
    `<li class="${l === q.gabarito ? 'certa' : ''}"><span class="l">${l})</span><div>${md(t, figs)}</div></li>`).join('');
  const s = document.createElement('section');
  s.className = 'q';
  s.dataset.erro = v.erros.length > 0;
  s.dataset.aviso = v.avisos.length > 0;
  s.innerHTML = `
    <div class="cab"><b>Questão ${String(q.numero).padStart(2, '0')}</b>
      <span class="meta">${esc(q.instituicao || 'sem banca')} ${esc(q.ano || '')} · ${esc(q.etapa || '')} · dificuldade ${q.dificuldade} · p.${q.pagina}</span>
      ${v.erros.length ? `<span class="selo erro">${v.erros.length} erro(s)</span>` : ''}
      ${v.avisos.length ? `<span class="selo aviso">${v.avisos.length} aviso(s)</span>` : ''}
      <span class="meta" style="flex-basis:100%">${esc(q.titulo)}</span></div>
    ${v.erros.length ? `<ul class="msgs erro sem-tex">${v.erros.map(e => `<li>${esc(e)}</li>`).join('')}</ul>` : ''}
    ${v.avisos.length ? `<ul class="msgs aviso sem-tex">${v.avisos.map(e => `<li>${esc(e)}</li>`).join('')}</ul>` : ''}
    <div class="corpo">
      <div class="orig"><img loading="lazy" src="${q.imagem}" alt="Original da questão ${q.numero}"></div>
      <div class="render">${md(q.enunciado, figs)}<ol class="alts">${alts}</ol>
        <details><summary>Explicação do professor</summary>${md(q.explicacao, figs)}</details></div>
    </div>`;
  main.appendChild(s);
}
document.querySelectorAll('.filtros button').forEach(b => b.onclick = () => {
  document.querySelectorAll('.filtros button').forEach(x => x.classList.toggle('ativo', x === b));
  document.querySelectorAll('.q').forEach(q => q.hidden = b.dataset.f !== 'todas' && q.dataset[b.dataset.f] !== 'true');
});
</script>
</body></html>
"""


def gerar(pasta: Path) -> Path:
    lista, resultado = validar(pasta)
    erros, avisos = resumo(resultado)
    dados = {"questoes": [q.model_dump() for q in lista.questoes], "validacao": resultado}
    texto_resumo = (f"{len(lista.questoes)} questões · {lista.disciplina or ''} / {lista.topico or ''}"
                    f" · {erros} erro(s) · {avisos} aviso(s)")
    html = (PAGINA.replace("__TITULO__", lista.titulo)
            .replace("__RESUMO__", texto_resumo)
            .replace("__DADOS__", json.dumps(dados, ensure_ascii=False).replace("</", "<\\/")))
    destino = pasta / "revisao.html"
    destino.write_text(html, encoding="utf-8")
    return destino


if __name__ == "__main__":
    print(gerar(Path(sys.argv[1])))
