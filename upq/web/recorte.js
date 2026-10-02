/* Recorte de uma lista em PDF (modelo Plataforma Assaad) no navegador, com pdf.js.
 * Porta de upq/segmentar.py: usa só a geometria da página (barras "Questão NN",
 * meio da página entre as colunas, rodapé) e as imagens desenhadas nela.
 *
 *   const m = await UPQRecorte.segmentar(arquivo, progresso => ...)
 *   m.questoes[i] = {numero, pagina, coluna, regiao, etapa, textoPdf, imagem: Blob, figuras: [{nome, blob}]}
 */
const UPQRecorte = (() => {
  const ETAPAS = ['Fixação', 'Treinamento', 'Aprofundamento', 'Desafios'];
  const RE_QUESTAO = /^\s*Quest[aã]o\s*(\d[\d ]*)/;
  const MARGEM_TOPO = 30;          // abaixo da faixa de cabeçalho da página (pt)
  const FIGURA_MIN = 40;           // lado mínimo (pt) para uma imagem contar como figura
  const ESCALA = 3;                // render da página: 3 px por pt (≈ 216 dpi)
  const MAX_PX_QUESTAO = 1150000;  // o Claude reduz imagens a ~1,2 MP: o recorte já sai nesse tamanho

  async function hash(buffer) {
    const d = await crypto.subtle.digest('SHA-256', buffer);
    return [...new Uint8Array(d)].map(b => b.toString(16).padStart(2, '0')).join('');
  }

  // Linhas de texto da página, por coluna, em pt com origem no canto superior esquerdo.
  function linhasDaPagina(itens, viewport) {
    const meio = viewport.width / 2;
    const pedacos = [];
    for (const it of itens) {
      if (!it.str) continue;
      const [x, y] = viewport.convertToViewportPoint(it.transform[4], it.transform[5]);
      const h = it.height || Math.hypot(it.transform[2], it.transform[3]) || 8;
      pedacos.push({str: it.str, x0: x, x1: x + (it.width || 0), base: y, h, col: x < meio ? 0 : 1});
    }
    pedacos.sort((a, b) => a.col - b.col || a.base - b.base || a.x0 - b.x0);
    const linhas = [];
    for (const p of pedacos) {
      const l = linhas.length && linhas[linhas.length - 1];
      if (l && l.col === p.col && Math.abs(l.base - p.base) < 2.5) l.pedacos.push(p);
      else linhas.push({col: p.col, base: p.base, pedacos: [p]});
    }
    return linhas.map(l => {
      l.pedacos.sort((a, b) => a.x0 - b.x0);
      let texto = '', fim = null;
      for (const p of l.pedacos) {
        if (fim !== null && p.x0 - fim > 1.5 && !texto.endsWith(' ') && !p.str.startsWith(' ')) texto += ' ';
        texto += p.str; fim = p.x1;
      }
      const h = Math.max(...l.pedacos.map(p => p.h));
      return {texto, col: l.col, x0: Math.min(...l.pedacos.map(p => p.x0)), x1: Math.max(...l.pedacos.map(p => p.x1)),
              y0: l.base - h, y1: l.base + h * 0.25, base: l.base};
    });
  }

  // Retângulos (pt) das imagens desenhadas na página, seguindo a matriz de transformação.
  async function imagensDaPagina(page, viewport) {
    const {fnArray, argsArray} = await page.getOperatorList();
    const OPS = pdfjsLib.OPS;
    // Matrizes [a b c d e f] do PDF: mul(m1, m2) aplica m2 e depois m1.
    const mul = (m1, m2) => [m1[0] * m2[0] + m1[2] * m2[1], m1[1] * m2[0] + m1[3] * m2[1],
      m1[0] * m2[2] + m1[2] * m2[3], m1[1] * m2[2] + m1[3] * m2[3],
      m1[0] * m2[4] + m1[2] * m2[5] + m1[4], m1[1] * m2[4] + m1[3] * m2[5] + m1[5]];
    const aplicar = ([x, y], m) => [m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5]];
    let ctm = viewport.transform.slice();
    const pilha = [], rects = [];
    for (let i = 0; i < fnArray.length; i++) {
      const fn = fnArray[i], args = argsArray[i];
      if (fn === OPS.save) pilha.push(ctm.slice());
      else if (fn === OPS.restore) ctm = pilha.pop() || ctm;
      else if (fn === OPS.transform) ctm = mul(ctm, args);
      else if (fn === OPS.paintFormXObjectBegin) { pilha.push(ctm.slice()); if (args && args[0]) ctm = mul(ctm, args[0]); }
      else if (fn === OPS.paintFormXObjectEnd) ctm = pilha.pop() || ctm;
      else if (fn === OPS.paintImageXObject || fn === OPS.paintInlineImageXObject || fn === OPS.paintJpegXObject) {
        const pts = [[0, 0], [1, 0], [0, 1], [1, 1]].map(p => aplicar(p, ctm));
        const xs = pts.map(p => p[0]), ys = pts.map(p => p[1]);
        rects.push({x0: Math.min(...xs), y0: Math.min(...ys), x1: Math.max(...xs), y1: Math.max(...ys)});
      }
    }
    return rects;
  }

  // A imagem embutida às vezes é maior que a área visível e invade o texto vizinho:
  // corta nas linhas que cruzam a borda de cima ou de baixo (rótulos inteiros dentro ficam).
  function aparar(f, linhas) {
    const r = {...f};
    for (const t of linhas) {
      if (t.x1 < r.x0 || t.x0 > r.x1) continue;
      if (t.y0 < r.y1 && r.y1 < t.y1) r.y1 = t.y0 - 1;
      else if (t.y0 < r.y0 && r.y0 < t.y1) r.y0 = t.y1 + 1;
    }
    return r;
  }

  async function renderizar(page) {
    const vp = page.getViewport({scale: ESCALA});
    const canvas = document.createElement('canvas');
    canvas.width = Math.ceil(vp.width); canvas.height = Math.ceil(vp.height);
    const ctx = canvas.getContext('2d');
    ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, canvas.width, canvas.height);
    await page.render({canvasContext: ctx, viewport: vp}).promise;
    return canvas;
  }

  function recortar(canvas, r, {maxPx = Infinity, tipo = 'image/png', qualidade = 0.88} = {}) {
    const sx = Math.max(0, r.x0 * ESCALA), sy = Math.max(0, r.y0 * ESCALA);
    const sw = Math.min(canvas.width - sx, (r.x1 - r.x0) * ESCALA), sh = Math.min(canvas.height - sy, (r.y1 - r.y0) * ESCALA);
    const fator = Math.min(1, Math.sqrt(maxPx / (sw * sh)));
    const c = document.createElement('canvas');
    c.width = Math.max(1, Math.round(sw * fator)); c.height = Math.max(1, Math.round(sh * fator));
    const ctx = c.getContext('2d');
    ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, c.width, c.height);
    ctx.drawImage(canvas, sx, sy, sw, sh, 0, 0, c.width, c.height);
    return new Promise(res => c.toBlob(res, tipo, qualidade));
  }

  function etapasPeloSumario(paginas) {
    for (const p of paginas) {
      if (!p.linhas.some(l => /Sumário/.test(l.texto))) continue;
      const inicio = {};
      for (const etapa of ETAPAS) {
        const l = p.linhas.find(x => x.texto.trim() === etapa);
        if (!l) continue;
        const num = p.linhas.find(x => /^\s*\d{1,3}\s*$/.test(x.texto) && Math.abs(x.base - l.base) < 6);
        if (num) inicio[etapa] = parseInt(num.texto, 10);
      }
      if (Object.keys(inicio).length) return inicio;
    }
    return {};
  }

  function gabaritoEmTexto(linhas) {
    const pares = {};
    const texto = linhas.map(l => l.texto).join('\n');
    for (const m of texto.matchAll(/^\s*(\d{1,3})\s*[\n ]\s*([A-E])\s*$/gm)) pares[String(+m[1]).padStart(2, '0')] = m[2];
    return pares;
  }

  async function segmentar(arquivo, progresso = () => {}) {
    const buffer = arquivo instanceof ArrayBuffer ? arquivo : await arquivo.arrayBuffer();
    const hashPdf = await hash(buffer.slice(0));
    const doc = await pdfjsLib.getDocument({data: new Uint8Array(buffer), isEvalSupported: false}).promise;
    const paginas = [];
    let tituloLista = '';
    for (let pn = 1; pn <= doc.numPages; pn++) {
      progresso({etapa: 'lendo', pagina: pn, total: doc.numPages});
      const page = await doc.getPage(pn);
      const vp = page.getViewport({scale: 1});
      const {items} = await page.getTextContent();
      const linhas = linhasDaPagina(items, vp);
      if (!tituloLista) {
        const t = linhas.find(l => l.texto.startsWith('Lista de Exercícios'));
        if (t) tituloLista = t.texto.split('|').slice(1).join('|').trim();
      }
      const rodape = linhas.filter(l => l.y0 > vp.height * 0.85 && /Plataforma|Assaad/.test(l.texto));
      const fundo = rodape.length ? Math.min(...rodape.map(l => l.y0)) - 8 : vp.height - 30;
      const cabecalhos = linhas.filter(l => l.y0 > MARGEM_TOPO && RE_QUESTAO.test(l.texto))
        .map(l => ({col: l.col, y: l.y0, numero: parseInt(l.texto.match(RE_QUESTAO)[1].replace(/ /g, ''), 10)}));
      paginas.push({pn, page, vp, linhas, fundo, cabecalhos});
    }

    const questoes = [];
    const semQuestao = [];
    for (const p of paginas) {
      if (!p.cabecalhos.length) { semQuestao.push(p); continue; }
      progresso({etapa: 'recortando', pagina: p.pn, total: doc.numPages});
      const canvas = await renderizar(p.page);
      const imagens = (await imagensDaPagina(p.page, p.vp)).filter(r =>
        r.x1 - r.x0 >= FIGURA_MIN && r.y1 - r.y0 >= FIGURA_MIN && r.y0 > MARGEM_TOPO);
      const meio = p.vp.width / 2;
      for (const col of [0, 1]) {
        const naColuna = p.cabecalhos.filter(c => c.col === col).sort((a, b) => a.y - b.y);
        const [x0, x1] = col === 0 ? [0, meio] : [meio, p.vp.width];
        for (let i = 0; i < naColuna.length; i++) {
          const {y, numero} = naColuna[i];
          const yFim = i + 1 < naColuna.length ? naColuna[i + 1].y - 2 : p.fundo - 2;
          const regiao = {x0: x0 + 2, y0: y - 2, x1: x1 - 2, y1: yFim};
          const dentro = imagens.filter(f => {
            const cx = (f.x0 + f.x1) / 2, cy = (f.y0 + f.y1) / 2;
            return cx > regiao.x0 && cx < regiao.x1 && cy > regiao.y0 && cy < regiao.y1;
          }).sort((a, b) => a.y0 - b.y0 || a.x0 - b.x0);
          const nn = String(numero).padStart(2, '0');
          const figuras = [];
          for (let k = 0; k < dentro.length; k++) {
            const f = aparar(dentro[k], p.linhas);
            figuras.push({nome: `Q${nn}_fig${k + 1}`, regiao: f, blob: await recortar(canvas, f)});
          }
          const textoPdf = p.linhas.filter(l => l.col === col && (l.y0 + l.y1) / 2 > regiao.y0 && (l.y0 + l.y1) / 2 < regiao.y1)
            .sort((a, b) => a.base - b.base).map(l => l.texto).join('\n');
          questoes.push({numero, pagina: p.pn, coluna: col + 1, regiao, textoPdf, figuras,
            imagem: await recortar(canvas, regiao, {maxPx: MAX_PX_QUESTAO, tipo: 'image/jpeg', qualidade: 0.86})});
        }
      }
    }

    const inicio = etapasPeloSumario(paginas);
    for (const q of questoes) {
      const antes = Object.entries(inicio).filter(([, pg]) => pg <= q.pagina).map(([e]) => e);
      q.etapa = antes.length ? antes[antes.length - 1] : null;
    }
    questoes.sort((a, b) => a.numero - b.numero);
    const numeros = questoes.map(q => q.numero);
    const maior = Math.max(0, ...numeros);
    const faltando = [...Array(maior).keys()].map(i => i + 1).filter(n => !numeros.includes(n));
    const repetidos = [...new Set(numeros.filter((n, i) => numeros.indexOf(n) !== i))];

    const ultima = Math.max(0, ...questoes.map(q => q.pagina));
    const pGab = semQuestao.find(p => p.pn > ultima);
    let paginaGabarito = null, gabaritoPdf = {};
    if (pGab) {
      gabaritoPdf = gabaritoEmTexto(pGab.linhas);
      if (!Object.keys(gabaritoPdf).length) {
        const c = await renderizar(pGab.page);
        paginaGabarito = await recortar(c, {x0: 0, y0: 0, x1: pGab.vp.width, y1: pGab.vp.height}, {maxPx: MAX_PX_QUESTAO, tipo: 'image/jpeg'});
      }
    }
    const nome = arquivo.name || 'lista.pdf';
    return {
      arquivo: nome, hash: hashPdf, titulo: tituloLista || nome.replace(/\.pdf$/i, '').replace(/_/g, ' '),
      tipo: /simulado/i.test(nome + ' ' + tituloLista) ? 'simulado' : 'lista',
      etapas: inicio, questoes, faltando, repetidos, paginaGabarito, gabaritoPdf, paginas: doc.numPages,
    };
  }

  return {segmentar, ETAPAS};
})();
