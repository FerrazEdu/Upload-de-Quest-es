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
  const FIGURA_MIN = 30;           // lado mínimo (pt) para uma imagem contar como figura (alternativas em imagem são pequenas)
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
  // Ordem de leitura das figuras: por faixas horizontais (figuras lado a lado, como alternativas
  // A e B numa mesma linha, ficam da esquerda para a direita), depois de cima para baixo.
  function ordemDeLeitura(figs) {
    figs.sort((a, b) => a.y0 - b.y0);
    const faixas = [];
    for (const f of figs) {
      const u = faixas[faixas.length - 1];
      if (u && f.y0 < u.y1 - 0.5 * Math.min(f.y1 - f.y0, u.y1 - u.y0)) { u.f.push(f); u.y1 = Math.max(u.y1, f.y1); }
      else faixas.push({y1: f.y1, f: [f]});
    }
    figs.splice(0, figs.length, ...faixas.flatMap(u => u.f.sort((a, b) => a.x0 - b.x0)));
    return figs;
  }

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

  // Tabela de gabarito em texto: "12 C" na mesma linha, ou número e letra em pedaços alinhados.
  // Devolve {pares, caixas}: caixas[NN] = retângulo (pt) da linha da tabela, para o recorte.
  function gabaritoEmTexto(linhas) {
    const pares = {}, caixas = {};
    const nn = n => String(+n).padStart(2, '0');
    const uniao = (a, b) => ({x0: Math.min(a.x0, b.x0), y0: Math.min(a.y0, b.y0), x1: Math.max(a.x1, b.x1), y1: Math.max(a.y1, b.y1)});
    const numeros = [], letras = [];
    for (const l of linhas) {
      const t = l.texto.trim();
      let m;
      if ((m = t.match(/^(\d{1,3})\s+([A-E])$/))) { pares[nn(m[1])] = m[2]; caixas[nn(m[1])] = uniao(l, l); }
      else if (/^\d{1,3}$/.test(t)) numeros.push(l);
      else if (/^[A-E]$/.test(t)) letras.push(l);
    }
    for (const n of numeros) {
      const l = letras.filter(x => Math.abs(x.base - n.base) < 3 && x.x0 > n.x1).sort((a, b) => a.x0 - b.x0)[0];
      if (l && !pares[nn(n.texto)]) { pares[nn(n.texto)] = l.texto.trim(); caixas[nn(n.texto)] = uniao(n, l); }
    }
    return {pares, caixas};
  }

  // Quadro de gabarito desenhado como imagem: lê as letras A–E pela forma (sem IA).
  // Funciona com uma ou várias tabelas lado a lado ("Questão | Gabarito"), de qualquer tamanho.
  // A ordem das linhas é conferida pela quantidade de dígitos de cada número (1–9: um; 10+: dois).
  // Devolve {pares: {"01": "C", ...}, motivo} — pares vazio quando não dá para ler com segurança.
  function componentes(canvas, limiar) {
    const W = canvas.width, H = canvas.height;
    const px = canvas.getContext('2d').getImageData(0, 0, W, H).data;
    const tinta = new Uint8Array(W * H);
    for (let i = 0, j = 0; i < tinta.length; i++, j += 4) {
      const mx = Math.max(px[j], px[j + 1], px[j + 2]), mn = Math.min(px[j], px[j + 1], px[j + 2]);
      tinta[i] = mx < limiar && mx - mn < 90 ? 1 : 0;   // escuro e pouco saturado (não o vermelho/azul do layout)
    }
    const rot = new Int32Array(W * H), fila = new Int32Array(W * H), comps = [];
    for (let i = 0; i < tinta.length; i++) {
      if (!tinta[i] || rot[i]) continue;
      const c = {x0: W, y0: H, x1: 0, y1: 0, n: 0, id: comps.length + 1};
      let ini = 0, fim = 0; fila[fim++] = i; rot[i] = c.id;
      while (ini < fim) {
        const k = fila[ini++], x = k % W, y = (k - x) / W;
        c.n++; if (x < c.x0) c.x0 = x; if (x > c.x1) c.x1 = x; if (y < c.y0) c.y0 = y; if (y > c.y1) c.y1 = y;
        if (x > 0 && tinta[k - 1] && !rot[k - 1]) { rot[k - 1] = c.id; fila[fim++] = k - 1; }
        if (x < W - 1 && tinta[k + 1] && !rot[k + 1]) { rot[k + 1] = c.id; fila[fim++] = k + 1; }
        if (y > 0 && tinta[k - W] && !rot[k - W]) { rot[k - W] = c.id; fila[fim++] = k - W; }
        if (y < H - 1 && tinta[k + W] && !rot[k + W]) { rot[k + W] = c.id; fila[fim++] = k + W; }
      }
      comps.push(c);
    }
    return {comps, rot, W, px};
  }

  // retângulo (pt) que cobre o número e a letra de uma linha da tabela
  function caixaDe(num, letra) {
    const g = [...num.g, ...letra.g];
    return {x0: Math.min(...g.map(c => c.x0)) / ESCALA, y0: Math.min(...g.map(c => c.y0)) / ESCALA,
            x1: Math.max(...g.map(c => c.x1)) / ESCALA, y1: Math.max(...g.map(c => c.y1)) / ESCALA};
  }

  function gabaritoNaImagem(canvas, inicio = 1) {
    let melhor = {pares: {}, motivo: 'nenhum quadro de gabarito reconhecido'};
    for (const limiar of [120, 160, 90]) {
      const r = lerQuadro(canvas, limiar, inicio);
      if (Object.keys(r.pares).length) return r;
      if (r.pontos > (melhor.pontos || 0)) melhor = r;
    }
    return melhor;
  }

  function lerQuadro(canvas, limiar, inicio) {
    const {comps, rot, W, px} = componentes(canvas, limiar);
    const glifos = comps.filter(c => { const h = c.y1 - c.y0 + 1, w = c.x1 - c.x0 + 1;
      return h >= ESCALA * 3 && h <= ESCALA * 30 && w <= ESCALA * 30 && w >= 2 && c.n > 12; });
    // linhas: glifos com o centro vertical alinhado
    glifos.sort((a, b) => (a.y0 + a.y1) - (b.y0 + b.y1));
    const linhas = [];
    for (const g of glifos) {
      const yc = (g.y0 + g.y1) / 2, h = g.y1 - g.y0 + 1, l = linhas[linhas.length - 1];
      if (l && Math.abs(yc - l.yc) < 0.45 * Math.max(h, l.h)) { l.g.push(g); l.yc = (l.yc * (l.g.length - 1) + yc) / l.g.length; l.h = Math.max(l.h, h); }
      else linhas.push({yc, h, g: [g]});
    }
    // em cada linha, glifos próximos formam um "item" (o número 12 = dois glifos)
    const linhasQuadro = [];
    for (const l of linhas) {
      l.g.sort((a, b) => a.x0 - b.x0);
      const itens = [];
      for (const g of l.g) {
        const u = itens[itens.length - 1];
        if (u && g.x0 - u.x1 < 0.6 * l.h) { u.g.push(g); u.x1 = Math.max(u.x1, g.x1); } else itens.push({x0: g.x0, x1: g.x1, g: [g]});
      }
      // padrão de linha do quadro: [número, letra] repetido (número: 1–3 glifos; letra: 1 glifo)
      if (itens.length < 2 || itens.length % 2) continue;
      let ok = true;
      for (let i = 0; i < itens.length; i += 2) if (itens[i].g.length > 3 || itens[i + 1].g.length !== 1) ok = false;
      if (ok) linhasQuadro.push(itens);
    }
    if (!linhasQuadro.length) return {pares: {}, motivo: 'nenhuma linha "número | letra" encontrada', pontos: 0};
    // mesma quantidade de tabelas (pares por linha) na maioria das linhas; tabelas em colunas
    const colunas = [];
    for (const itens of linhasQuadro)
      for (let i = 0; i < itens.length; i += 2) {
        const xc = (itens[i].x0 + itens[i + 1].x1) / 2;
        let col = colunas.find(c => Math.abs(c.xc - xc) < ESCALA * 40);
        if (!col) colunas.push(col = {xc, celulas: []});
        col.celulas.push({digitos: itens[i].g.length, largura: itens[i].x1 - itens[i].x0, letra: itens[i + 1].g[0], y: itens[i].g[0].y0, caixa: caixaDe(itens[i], itens[i + 1])});
      }
    colunas.sort((a, b) => a.xc - b.xc);
    const tentativas = [
      colunas.flatMap(c => c.celulas.sort((a, b) => a.y - b.y)),                                   // tabela por tabela
      linhasQuadro.flatMap(itens => itens.filter((_, i) => i % 2 === 0).map((n, k) => ({digitos: n.g.length, largura: n.x1 - n.x0, letra: itens[2 * k + 1].g[0], caixa: caixaDe(n, itens[2 * k + 1])}))),  // linha a linha
    ];
    // números sem zero (1, 2… 10) ou com zero à esquerda (01, 02… 10): as duas formas valem
    // Conferência da ordem pelo número de dígitos: contando os glifos ou, quando dígitos pequenos
    // se grudam, pela largura do número (1–9 têm cerca de metade da largura de 10–99).
    const confere = cel => {
      if (cel.length < 5) return false;   // leitura parcial nunca vale
      const largura = String(inicio + cel.length - 1).length;
      if (cel.every((c, i) => c.digitos === String(inicio + i).length) || cel.every(c => c.digitos === Math.max(2, largura))) return true;
      const ref = cel.filter((c, i) => String(inicio + i).length === largura).map(c => c.largura).sort((a, b) => a - b);
      if (!ref.length) return false;
      const med = ref[Math.floor(ref.length / 2)];
      const padrao = cel.map(c => c.largura / med);
      const semZero = padrao.every((r, i) => String(inicio + i).length < largura ? r > 0.3 && r < 0.75 : r > 0.8 && r < 1.25);
      const comZero = padrao.every(r => r > 0.8 && r < 1.25) && inicio + cel.length - 1 >= 10;
      return semZero || comZero;
    };
    const celulas = tentativas.find(confere);
    if (!celulas) return {pares: {}, motivo: `quadro com ${tentativas[0].length} linhas, mas a numeração não fecha`, pontos: tentativas[0].length};
    const pares = {}, caixas = {};
    for (let i = 0; i < celulas.length; i++) {
      const letra = reconhecerLetra(celulas[i].letra, rot, W, px);
      if (!letra) return {pares: {}, caixas: {}, motivo: `não reconheci a letra da questão ${inicio + i}`, pontos: celulas.length};
      pares[String(inicio + i).padStart(2, '0')] = letra;
      caixas[String(inicio + i).padStart(2, '0')] = celulas[i].caixa;
    }
    return {pares, caixas, motivo: null, pontos: celulas.length};
  }

  // Segundo método, que não depende do tamanho da letra: compara o glifo (em tons de cinza,
  // esticado para uma grade 20×20) com A–E desenhados pelo navegador em várias fontes.
  const GRADE = 20;
  let modelos = null;
  function gradeDe(cinza, w, h) {   // cinza: Float32Array w×h com 0 (fundo) a 1 (tinta)
    const g = new Float32Array(GRADE * GRADE);
    for (let gy = 0; gy < GRADE; gy++) for (let gx = 0; gx < GRADE; gx++) {
      const xa = gx * w / GRADE, xb = (gx + 1) * w / GRADE, ya = gy * h / GRADE, yb = (gy + 1) * h / GRADE;
      let soma = 0, n = 0;
      for (let y = Math.floor(ya); y < Math.ceil(yb); y++) for (let x = Math.floor(xa); x < Math.ceil(xb); x++) { soma += cinza[y * w + x]; n++; }
      g[gy * GRADE + gx] = n ? soma / n : 0;
    }
    const m = g.reduce((a, b) => a + b) / g.length;
    let d = 0; for (let i = 0; i < g.length; i++) { g[i] -= m; d += g[i] * g[i]; }
    d = Math.sqrt(d) || 1; for (let i = 0; i < g.length; i++) g[i] /= d;
    return g;
  }
  function carregarModelos() {
    if (modelos) return modelos;
    modelos = [];
    const c = document.createElement('canvas'); c.width = c.height = 160;
    const ctx = c.getContext('2d', {willReadFrequently: true});
    const fontes = ['Arial', 'Helvetica', 'Inter', 'Montserrat', 'Roboto', 'Segoe UI', 'DejaVu Sans', 'Liberation Sans', 'Verdana', 'sans-serif'];
    for (const f of fontes) for (const peso of ['bold', '600', 'normal']) for (const letra of 'ABCDE') {
      ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, 160, 160); ctx.fillStyle = '#000';
      ctx.font = `${peso} 110px "${f}"`; ctx.textBaseline = 'middle'; ctx.textAlign = 'center'; ctx.fillText(letra, 80, 84);
      const d = ctx.getImageData(0, 0, 160, 160).data;
      let x0 = 160, y0 = 160, x1 = -1, y1 = -1;
      for (let y = 0; y < 160; y++) for (let x = 0; x < 160; x++) if (d[(y * 160 + x) * 4] < 128) { if (x < x0) x0 = x; if (x > x1) x1 = x; if (y < y0) y0 = y; if (y > y1) y1 = y; }
      if (x1 < 0) continue;
      const w = x1 - x0 + 1, h = y1 - y0 + 1, cinza = new Float32Array(w * h);
      for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) cinza[y * w + x] = 1 - d[((y0 + y) * 160 + x0 + x) * 4] / 255;
      modelos.push({letra, g: gradeDe(cinza, w, h)});
    }
    return modelos;
  }
  function letraPorModelo(c, W, px) {
    const w = c.x1 - c.x0 + 1, h = c.y1 - c.y0 + 1, cinza = new Float32Array(w * h);
    let fundo = 0, n = 0;   // cor do fundo: pixels claros em volta da caixa
    for (let x = c.x0; x <= c.x1; x++) for (const y of [c.y0 - 2, c.y1 + 2]) {
      const j = (y * W + x) * 4; if (j >= 0 && j < px.length) { fundo += Math.max(px[j], px[j + 1], px[j + 2]); n++; }
    }
    fundo = n ? fundo / n : 255;
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
      const j = ((c.y0 + y) * W + c.x0 + x) * 4;
      cinza[y * w + x] = Math.max(0, Math.min(1, (fundo - Math.max(px[j], px[j + 1], px[j + 2])) / Math.max(60, fundo - 30)));
    }
    const g = gradeDe(cinza, w, h);
    const melhor = {};
    for (const m of carregarModelos()) {
      let r = 0; for (let i = 0; i < g.length; i++) r += g[i] * m.g[i];
      if (!(m.letra in melhor) || r > melhor[m.letra]) melhor[m.letra] = r;
    }
    const ord = Object.entries(melhor).sort((a, b) => b[1] - a[1]);
    return {letra: ord[0][0], nota: ord[0][1], margem: ord[0][1] - ord[1][1]};
  }
  // Decisão: forma (buracos/hastes) e modelo concordando; se a forma não decidir, o modelo
  // decide sozinho só com folga clara sobre a 2ª letra.
  function reconhecerLetra(c, rot, W, px) {
    const forma = classificarLetra(c, rot, W);
    const modelo = letraPorModelo(c, W, px);
    if (forma && forma === modelo.letra) return forma;
    if (!forma && modelo.nota > 0.6 && modelo.margem > 0.08) return modelo.letra;
    if (forma && modelo.margem < 0.04) return forma;   // modelo indeciso: fica a forma
    return null;
  }

  function classificarLetra(c, rot, W) {
    const w = c.x1 - c.x0 + 1, h = c.y1 - c.y0 + 1;
    const g = (x, y) => rot[(c.y0 + y) * W + c.x0 + x] === c.id;
    // buracos: regiões de fundo da caixa que não tocam a borda
    const visto = new Uint8Array(w * h), pilha = [];
    let buracos = 0;
    for (let y0 = 0; y0 < h; y0++) for (let x0 = 0; x0 < w; x0++) {
      if (g(x0, y0) || visto[y0 * w + x0]) continue;
      let borda = false, area = 0; pilha.push(x0, y0); visto[y0 * w + x0] = 1;
      while (pilha.length) {
        const y = pilha.pop(), x = pilha.pop(); area++;
        if (x === 0 || y === 0 || x === w - 1 || y === h - 1) borda = true;
        for (const [a, b] of [[x - 1, y], [x + 1, y], [x, y - 1], [x, y + 1]])
          if (a >= 0 && b >= 0 && a < w && b < h && !g(a, b) && !visto[b * w + a]) { visto[b * w + a] = 1; pilha.push(a, b); }
      }
      if (!borda && area > 4) buracos++;
    }
    const largura = y => { let a = -1, b = -1; for (let x = 0; x < w; x++) if (g(x, y)) { if (a < 0) a = x; b = x; } return a < 0 ? 0 : (b - a + 1) / w; };
    const fracao = (ys, xa, xb) => { let n = 0, t = 0; for (const y of ys) for (let x = Math.floor(xa * w); x < Math.ceil(xb * w); x++) { t++; n += g(x, y); } return n / t; };
    const faixa = (a, b) => { const r = []; for (let y = Math.floor(a * h); y <= Math.min(h - 1, Math.floor(b * h)); y++) r.push(y); return r; };
    if (buracos === 2) return 'B';
    if (buracos === 1) {
      const topo = Math.max(...faixa(0, 0.08).map(largura)), base = Math.max(...faixa(0.92, 1).map(largura));
      return topo < 0.6 && base > 0.8 ? 'A' : topo > 0.7 ? 'D' : null;
    }
    if (buracos === 0) {
      const meioDireita = fracao(faixa(0.42, 0.58), 0.55, 0.75);   // braço do meio do E
      const haste = fracao(faixa(0.1, 0.9), 0, 0.12);              // haste vertical cheia do E
      if (meioDireita > 0.3 && haste > 0.9) return 'E';
      if (meioDireita < 0.05) return 'C';
    }
    return null;
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
          });
          ordemDeLeitura(dentro);
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
    // Tabela de gabarito: nas páginas sem questão depois da última questão (pode ocupar mais de
    // uma); em último caso, no fim da página da última questão.
    const candidatas = semQuestao.filter(p => p.pn > ultima);
    const pUltima = paginas.find(p => p.pn === ultima);
    if (pUltima) candidatas.push(pUltima);
    let paginaGabarito = null, gabaritoPdf = {}, gabaritoMotivo = 'nenhuma página de gabarito depois das questões';
    const motivos = [], gabaritoRecortes = {};
    for (const pg of candidatas) {
      const proximo = Object.keys(gabaritoPdf).length + 1;
      let {pares, caixas} = gabaritoEmTexto(pg.linhas);
      const c = await renderizar(pg.page);
      if (!Object.keys(pares).length) {
        const r = gabaritoNaImagem(c, proximo);
        ({pares, caixas = {}} = r);
        if (r.motivo) motivos.push(`página ${pg.pn}: ${r.motivo}`);
      }
      // recorte da linha da tabela de cada questão (número + letra), para conferência
      for (const [n, cx] of Object.entries(caixas)) {
        const h = cx.y1 - cx.y0, mx = Math.max(12, h * 1.2);
        gabaritoRecortes[n] = await recortar(c, {x0: cx.x0 - mx, y0: cx.y0 - h * 0.6, x1: cx.x1 + mx, y1: cx.y1 + h * 0.6});
      }
      if (Object.keys(pares).length || !paginaGabarito)
        paginaGabarito = paginaGabarito && !Object.keys(pares).length ? paginaGabarito
          : await recortar(c, {x0: 0, y0: 0, x1: pg.vp.width, y1: pg.vp.height}, {maxPx: MAX_PX_QUESTAO, tipo: 'image/jpeg'});
      Object.assign(gabaritoPdf, pares);
      if (Object.keys(gabaritoPdf).length >= maior) break;
    }
    const lidas = Object.keys(gabaritoPdf).length;
    const completo = maior > 0 && [...Array(maior).keys()].every(i => gabaritoPdf[String(i + 1).padStart(2, '0')]);
    if (completo) gabaritoMotivo = null;
    else {
      gabaritoMotivo = lidas ? `a tabela tem ${lidas} respostas, a lista tem ${maior} questões` : (motivos.join('; ') || gabaritoMotivo);
      gabaritoPdf = {};
      for (const n of Object.keys(gabaritoRecortes)) delete gabaritoRecortes[n];
    }
    const nome = arquivo.name || 'lista.pdf';
    return {
      arquivo: nome, hash: hashPdf, titulo: tituloLista || nome.replace(/\.pdf$/i, '').replace(/_/g, ' '),
      tipo: /simulado/i.test(nome + ' ' + tituloLista) ? 'simulado' : 'lista',
      etapas: inicio, questoes, faltando, repetidos, paginaGabarito, gabaritoPdf, gabaritoMotivo, gabaritoRecortes, paginas: doc.numPages,
    };
  }

  return {segmentar, gabaritoNaImagem, ETAPAS};
})();
