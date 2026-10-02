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
  // umaColuna: página com questões na largura toda (sem divisão em duas colunas)
  // negrito(fontName): se a fonte do pedaço é negrito (nome da fonte embutida no PDF).
  // Cada linha sai com `texto` (puro) e `marcado` (trechos em negrito entre **).
  // Negrito pela espessura do traço, PALAVRA A PALAVRA: nas fontes Type3 destas listas a mesma fonte
  // desenha letras normais e em negrito ("Assinale a alternativa CORRETA:" é um pedaço só), então não
  // há nome nem fonte que diga o peso. Na página renderizada, cada pedaço é separado em palavras pelos
  // vãos de tinta; o traço médio de cada palavra (relativo ao tamanho da letra) bem acima do da
  // página = negrito.
  function tracoDe(px, W, X0, X1, Y0, Y1) {
    const runs = [];
    for (let y = Y0; y < Y1; y++) {
      let run = 0;
      for (let x = X0; x < X1; x++) {
        const j = (y * W + x) * 4, escuro = 0.299 * px[j] + 0.587 * px[j + 1] + 0.114 * px[j + 2] < 120;
        if (escuro) run++; else if (run) { runs.push(run); run = 0; }
      }
      if (run) runs.push(run);
    }
    if (runs.length < 4) return null;
    runs.sort((a, b) => a - b);
    const teto = 2.5 * runs[Math.floor(runs.length / 2)], uteis = runs.filter(r => r <= teto);   // sem barras de "e", "t"
    return uteis.reduce((a, b) => a + b, 0) / uteis.length;
  }
  // Pixels da página renderizada, lidos UMA vez por canvas: cada getImageData da página inteira são
  // ~18 MB; ler de novo em cada etapa (negrito, barra, tabela, fórmula) enchia a memória e travava a aba.
  function pixelsDe(canvas) {
    if (!canvas.__px) canvas.__px = canvas.getContext('2d', {willReadFrequently: true}).getImageData(0, 0, canvas.width, canvas.height).data;
    return canvas.__px;
  }
  // cópia de uma região (para quem trabalha em coordenadas locais), tirada do buffer já lido
  function regiaoDe(canvas, X, Y, W, H) {
    const px = pixelsDe(canvas), CW = canvas.width, out = new Uint8ClampedArray(W * H * 4);
    for (let y = 0; y < H; y++) out.set(px.subarray(((Y + y) * CW + X) * 4, ((Y + y) * CW + X + W) * 4), y * W * 4);
    return out;
  }
  const folga = () => new Promise(r => setTimeout(r, 0));
  function liberar(canvas) { if (canvas) { canvas.__px = null; canvas.width = canvas.height = 0; } }
  function negritoPorPalavra(canvas, ...listasDeLinhas) {
    const W = canvas.width, H = canvas.height, px = pixelsDe(canvas);
    const medidas = [];   // {token, razao}
    const vistos = new Set();
    for (const linhas of listasDeLinhas) for (const l of linhas) for (const t of l.trechos || []) {
      if (vistos.has(t) || !(t.h > 3) || !t.t.trim()) continue;
      vistos.add(t);
      const X0 = Math.max(0, Math.floor(t.x0 * ESCALA)), X1 = Math.min(W, Math.ceil(t.x1 * ESCALA));
      const Y0 = Math.max(0, Math.round((t.base - 0.62 * t.h) * ESCALA)), Y1 = Math.min(H, Math.round((t.base - 0.1 * t.h) * ESCALA));
      if (X1 - X0 < 4 || Y1 - Y0 < 3) continue;
      // colunas com tinta → segmentos (palavras) separados por vãos de pelo menos 1/4 da altura da letra
      const tem = [];
      for (let x = X0; x < X1; x++) { let k = false; for (let y = Y0; y < Y1 && !k; y++) { const j = (y * W + x) * 4; k = 0.299 * px[j] + 0.587 * px[j + 1] + 0.114 * px[j + 2] < 120; } tem.push(k); }
      const vaoMin = Math.max(2, 0.22 * t.h * ESCALA), segs = [];
      let ini = -1, ultimo = -1e9;
      tem.forEach((k, i) => { if (!k) return; if (ini < 0) ini = i; else if (i - ultimo > vaoMin) { segs.push([ini, ultimo]); ini = i; } ultimo = i; });
      if (ini >= 0) segs.push([ini, ultimo]);
      const tokens = t.t.split(/(\s+)/), palavras = tokens.filter(x => x.trim());
      if (segs.length !== palavras.length) continue;   // não deu para casar palavra e segmento: fica sem marca
      t.palavras = tokens.map(tok => ({t: tok, negrito: false}));
      let k = 0;
      for (const tok of t.palavras) {
        if (!tok.t.trim()) continue;
        const [a0, a1] = segs[k++];
        const traco = tracoDe(px, W, X0 + a0, X0 + a1 + 1, Y0, Y1);
        // só palavras de 3+ letras/dígitos: letra de alternativa (em círculo pintado) e palavras curtas dão medida falsa
        if (traco && (tok.t.match(/[A-Za-zÀ-ú0-9]/g) || []).length >= 3) medidas.push({tok, razao: traco / (t.h * ESCALA), n: tok.t.length});
      }
    }
    if (medidas.length < 8) return;
    // referência = traço típico das palavras da página (ponderado por letras; a maioria é texto corrido)
    const pesos = medidas.flatMap(m => Array(Math.min(12, m.n)).fill(m.razao)).sort((a, b) => a - b);
    const corpo = pesos[Math.floor(pesos.length * 0.4)];
    for (const m of medidas) if (m.razao >= 1.22 * corpo) m.tok.negrito = true;
  }
  const marcadoDe = l => {
    if (!l.trechos) return l.marcado;
    const partes = l.trechos.flatMap(t => t.palavras ? t.palavras.map(p => ({t: p.t, negrito: t.negrito || p.negrito})) : [{t: t.t, negrito: t.negrito}]);
    // espaço entre duas palavras em negrito fica dentro do negrito ("**alternativa CORRETA**")
    partes.forEach((p, i) => { if (!p.t.trim()) p.negrito = !!(partes[i - 1]?.negrito && partes[i + 1]?.negrito); });
    return marcarNegrito(partes);
  };

  // Junta trechos vizinhos de mesmo peso e põe ** em volta dos negritos (espaços ficam fora).
  function marcarNegrito(trechos) {
    const runs = [];
    for (const t of trechos) {
      const u = runs[runs.length - 1];
      if (u && u.negrito === t.negrito) u.t += t.t; else runs.push({...t});
    }
    return runs.map(r => {
      if (!r.negrito || !/[0-9A-Za-zÀ-ú]/.test(r.t)) return r.t;
      const m = r.t.match(/^(\s*)([\s\S]*?)(\s*)$/);
      return `${m[1]}**${m[2]}**${m[3]}`;
    }).join('');
  }

  function linhasDaPagina(itens, viewport, umaColuna = false, negrito = () => false) {
    const meio = umaColuna ? Infinity : viewport.width / 2;
    const pedacos = [];
    for (const it of itens) {
      if (!it.str) continue;
      const [x, y] = viewport.convertToViewportPoint(it.transform[4], it.transform[5]);
      const h = it.height || Math.hypot(it.transform[2], it.transform[3]) || 8;
      pedacos.push({str: it.str, x0: x, x1: x + (it.width || 0), base: y, h, col: x < meio ? 0 : 1, negrito: negrito(it.fontName), fonte: it.fontName});
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
      const trechos = [];   // [{t, negrito}] com os espaços entre pedaços
      for (const p of l.pedacos) {
        // sobreposição > 1 pt: a largura do pedaço anterior incluía o espaço final (o pdf.js o tira do texto)
        const espaco = fim !== null && (p.x0 - fim > 1.5 || fim - p.x0 > 1) && !texto.endsWith(' ') && !p.str.startsWith(' ') ? ' ' : '';
        texto += espaco + p.str; fim = p.x1;
        trechos.push({t: espaco + p.str, negrito: p.negrito, fonte: p.fonte, x0: p.x0, x1: p.x1, base: p.base, h: p.h});
      }
      const h = Math.max(...l.pedacos.map(p => p.h));
      return {texto, marcado: marcarNegrito(trechos), trechos, col: l.col, x0: Math.min(...l.pedacos.map(p => p.x0)), x1: Math.max(...l.pedacos.map(p => p.x1)),
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
  // Tabela colada como imagem (print): procura a grade — linhas horizontais longas com a mesma
  // largura e linhas verticais fechando a caixa. Devolve a caixa da grade (pt) ou null.
  function gradeDaTabela(canvas, f) {
    const X = Math.max(0, Math.round(f.x0 * ESCALA)), Y = Math.max(0, Math.round(f.y0 * ESCALA));
    const W = Math.min(canvas.width - X, Math.round((f.x1 - f.x0) * ESCALA)), H = Math.min(canvas.height - Y, Math.round((f.y1 - f.y0) * ESCALA));
    if (W < 60 || H < 40) return null;
    const px = regiaoDe(canvas, X, Y, W, H);
    const at = (x, y) => (y * W + x) * 4;
    const fundo = [[2, 2], [W - 3, 2], [2, H - 3], [W - 3, H - 3]].map(([x, y]) => [px[at(x, y)], px[at(x, y) + 1], px[at(x, y) + 2]])
      .sort((a, b) => (b[0] + b[1] + b[2]) - (a[0] + a[1] + a[2]))[1];
    const tinta = new Uint8Array(W * H);
    for (let i = 0; i < W * H; i++) tinta[i] = Math.abs(px[i * 4] - fundo[0]) + Math.abs(px[i * 4 + 1] - fundo[1]) + Math.abs(px[i * 4 + 2] - fundo[2]) > 120 ? 1 : 0;
    const linhasDe = (n, m, get, minRun) => {   // n linhas de varredura de comprimento m
      const cand = [];
      for (let a = 0; a < n; a++) {
        let run = 0, melhor = 0, ini = 0, mIni = 0;
        for (let b = 0; b < m; b++) { if (get(a, b)) { if (!run) ini = b; run++; if (run > melhor) { melhor = run; mIni = ini; } } else run = 0; }
        if (melhor >= minRun) cand.push({a, b0: mIni, b1: mIni + melhor});
      }
      const grupos = [];
      for (const c of cand) {
        const u = grupos[grupos.length - 1];
        if (u && c.a - u.a1 <= 2) { u.a1 = c.a; u.b0 = Math.min(u.b0, c.b0); u.b1 = Math.max(u.b1, c.b1); } else grupos.push({a0: c.a, a1: c.a, b0: c.b0, b1: c.b1});
      }
      return grupos;
    };
    const fina = g => g.a1 - g.a0 + 1 <= 2 * ESCALA;   // fio de grade: até 2 pt (faixa grossa = cabeçalho pintado)
    const hs = linhasDe(H, W, (y, x) => tinta[y * W + x], Math.round(0.4 * W));
    if (hs.length < 3 || hs.filter(fina).length < 2) return null;   // fios finos + faixas pintadas (cabeçalho)
    // horizontais da grade: mesma extensão que a mais larga
    const larga = hs.filter(fina).reduce((a, b) => (b.b1 - b.b0 > a.b1 - a.b0 ? b : a));
    const grade = hs.filter(h => Math.abs(h.b0 - larga.b0) < 0.04 * W && Math.abs(h.b1 - larga.b1) < 0.04 * W);
    if (grade.length < 3 || grade.filter(fina).length < 2) return null;
    const topo = grade[0].a0, base = grade[grade.length - 1].a1, esq = larga.b0, dir = larga.b1;
    // miolo das células claro: entre dois fios seguidos, pouca tinta (foto escura não passa)
    const finas = grade.filter(fina);
    for (let i = 0; i + 1 < finas.length; i++) {
      const ya = finas[i].a1 + 2, yb = finas[i + 1].a0 - 2;
      if (yb - ya < 4) continue;
      let n = 0, t = 0;
      for (let y = ya; y < yb; y += 2) for (let x = esq; x < dir; x += 2) { t++; n += tinta[y * W + x]; }
      if (t && n / t > 0.35 && !grade.some(g => !fina(g) && g.a0 <= ya + 2 && g.a1 >= yb - 2)) return null;
    }
    const vs = linhasDe(W, H, (x, y) => tinta[y * W + x], Math.round(0.8 * (base - topo))).filter(v => v.a0 >= esq - 4 && v.a1 <= dir + 4 && fina(v));
    if (vs.length < 2 || vs[0].a0 - esq > 0.05 * W || dir - vs[vs.length - 1].a1 > 0.05 * W) return null;
    const m = 2 * ESCALA;
    // Células: separadores = fios finos + bordas das faixas pintadas (o cabeçalho pintado, que o
    // texto branco parte em pedaços, vira UMA linha da tabela).
    const faixas = [];
    for (const g of grade) {
      const u = faixas[faixas.length - 1];
      if (u && !fina(g) && !u.fina && g.a0 - u.a1 < 12 * ESCALA) { u.a1 = g.a1; continue; }
      faixas.push({a0: g.a0, a1: g.a1, fina: fina(g)});
    }
    const cortes = [];
    for (const f of faixas) { if (f.fina) cortes.push([f.a0, f.a1]); else { cortes.push([f.a0, f.a0]); cortes.push([f.a1, f.a1]); } }
    const ys = [];
    for (let i = 0; i + 1 < cortes.length; i++) { const a = cortes[i][1] + 1, b = cortes[i + 1][0] - 1; if (b - a >= 4 * ESCALA) ys.push([a, b]); }
    const xs = [];
    for (let i = 0; i + 1 < vs.length; i++) { const a = vs[i].a1 + 1, b = vs[i + 1].a0 - 1; if (b - a >= 4 * ESCALA) xs.push([a, b]); }
    const ox = esq - m, oy = topo - m;   // células relativas à caixa devolvida, na escala do render
    return {x0: (X + esq - m) / ESCALA, y0: (Y + topo - m) / ESCALA, x1: (X + dir + m) / ESCALA, y1: (Y + base + m) / ESCALA,
            celulas: {ys: ys.map(([a, b]) => [a - oy, b - oy]), xs: xs.map(([a, b]) => [a - ox, b - ox])}};
  }

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

  // Tinta sem texto numa parte: fórmula que o PDF traz como imagem pequena (ou desenho), sem camada de
  // texto — sem isto ela some da transcrição (alternativas "em branco") e do recorte. Duas fontes:
  // as imagens pequenas da página (que não são o círculo da letra) e, para desenhos vetoriais, a tinta
  // que sobra no mapa da página (células de 1 pt) tirando o texto e as figuras. Manchas vizinhas se
  // juntam (fração, expoente, "·", parênteses). Ficam de fora traços (linhas, réguas, barras), pingos
  // e o que contém texto (círculo da letra, caixas, tabelas). Devolve as caixas (pt), cada uma com o
  // recorte só da sua tinta (PNG).
  async function tintaSemTexto(canvas, regiao, linhas, figuras, cabecalho, pequenas = []) {
    const E = ESCALA, X0 = Math.max(0, Math.floor(regiao.x0)), X1 = Math.min(Math.floor(canvas.width / E), Math.ceil(regiao.x1));
    const Y0 = Math.max(0, Math.floor(cabecalho ? Math.max(regiao.y0, cabecalho.y1 + 2) : regiao.y0)), Y1 = Math.min(Math.floor(canvas.height / E), Math.ceil(regiao.y1));
    const W = X1 - X0, H = Y1 - Y0;
    if (W < 4 || H < 4) return [];
    const px = pixelsDe(canvas), CW = canvas.width, OX = X0 * E, OY = Y0 * E;   // índices no buffer da página
    const trechos = linhas.flatMap(l => l.trechos?.length ? l.trechos : [{x0: l.x0, x1: l.x1, base: l.base, h: l.y1 - l.y0}]);
    const caixaDe = t => ({x0: t.x0 - 0.8, x1: t.x1 + 0.8, y0: t.base - 1.02 * t.h - 0.5, y1: t.base + 0.32 * t.h});
    const contemTexto = c => trechos.some(t => { const b = caixaDe(t); return b.x0 + 0.8 >= c.x0 - 1 && b.x1 - 0.8 <= c.x1 + 1 && t.base - 0.6 * t.h >= c.y0 - 1 && t.base <= c.y1 + 1; });
    // imagens pequenas dentro da parte que não envolvem texto (o círculo da letra envolve a letra)
    const naParte = pequenas.filter(r => { const cx = (r.x0 + r.x1) / 2, cy = (r.y0 + r.y1) / 2; return cx > X0 && cx < X1 && cy > Y0 && cy < Y1; });
    const imgs = naParte.filter(r => r.x1 - r.x0 >= 4 && r.y1 - r.y0 >= 4 && !contemTexto(r));
    const apagar = [...trechos.map(caixaDe), ...figuras.map(f => ({x0: f.x0 - 2, x1: f.x1 + 2, y0: f.y0 - 2, y1: f.y1 + 2})),
      ...naParte.filter(r => !imgs.includes(r)).map(r => ({x0: r.x0 - 1, x1: r.x1 + 1, y0: r.y0 - 1, y1: r.y1 + 1}))];
    const rotulos = trechos.filter(t => t.t && t.t.trim().length <= 2).map(t => ({x0: t.x0 - 4, x1: t.x1 + 4, y0: t.base - t.h - 4, y1: t.base + 0.4 * t.h + 4}));
    // linha de texto de cada mancha (a da letra da alternativa): manchas de linhas diferentes não se juntam
    const linhaDe = c => { const y0 = Y0 + c.y0, y1 = Y0 + c.y1 + 1;
      const k = linhas.findIndex(l => Math.min(l.y1, y1) - Math.max(l.y0, y0) >= 0.5 * (l.y1 - l.y0)); return k; };
    const escuro = new Uint8Array(W * H), cel = new Uint8Array(W * H), fora = new Uint8Array(W * H);
    // texto, figuras e imagens pequenas pintados de uma vez no mapa de células (em vez de testar
    // cada caixa em cada célula)
    const pintar = (b, folgaPt = 0) => {
      const x0 = Math.max(0, Math.ceil(b.x0 - folgaPt - X0 - 0.5)), x1 = Math.min(W - 1, Math.floor(b.x1 + folgaPt - X0 - 0.5));
      const y0 = Math.max(0, Math.ceil(b.y0 - folgaPt - Y0 - 0.5)), y1 = Math.min(H - 1, Math.floor(b.y1 + folgaPt - Y0 - 0.5));
      for (let y = y0; y <= y1; y++) fora.fill(1, y * W + x0, y * W + x1 + 1);
    };
    apagar.forEach(b => pintar(b)); imgs.forEach(r => pintar(r, 1));
    for (let cy = 0; cy < H; cy++) for (let cx = 0; cx < W; cx++) {
      let t = false;
      for (let y = cy * E; y < cy * E + E && !t; y++) for (let x = cx * E; x < cx * E + E; x++) {
        const j = ((OY + y) * CW + OX + x) * 4;
        if (0.299 * px[j] + 0.587 * px[j + 1] + 0.114 * px[j + 2] < 150) { t = true; break; }
      }
      if (!t) continue;
      escuro[cy * W + cx] = 1;
      if (!fora[cy * W + cx]) cel[cy * W + cx] = 1;
    }
    // componentes (8-vizinhança) da tinta que sobrou + uma mancha por imagem pequena
    const rotulo = new Uint8Array(W * H);
    let grupos = [];
    for (let i = 0; i < W * H; i++) {
      if (!cel[i] || rotulo[i]) continue;
      const c = {x0: W, y0: H, x1: -1, y1: -1, celulas: [], imagem: false}, pilha = [i];
      rotulo[i] = 1;
      while (pilha.length) {
        const k = pilha.pop(), x = k % W, y = (k - x) / W;
        c.celulas.push(k); c.x0 = Math.min(c.x0, x); c.x1 = Math.max(c.x1, x); c.y0 = Math.min(c.y0, y); c.y1 = Math.max(c.y1, y);
        for (let dy = -1; dy <= 1; dy++) for (let dx = -1; dx <= 1; dx++) {
          const nx = x + dx, ny = y + dy, n = ny * W + nx;
          if (nx >= 0 && ny >= 0 && nx < W && ny < H && cel[n] && !rotulo[n]) { rotulo[n] = 1; pilha.push(n); }
        }
      }
      // traço comprido e fino (régua, sublinhado, borda, barra): não é fórmula sozinho
      const w = c.x1 - c.x0 + 1, h = c.y1 - c.y0 + 1;
      if ((h <= 2 && w > 40) || (w <= 2 && h > 40) || (w > 20 * h && w > 60)) continue;
      // o que envolve texto (anel do círculo da letra, caixa, tabela) sai antes de juntar com vizinhos,
      // e também os restos do círculo em volta da letra da alternativa
      const cx0 = X0 + c.x0, cy0 = Y0 + c.y0, cx1 = X0 + c.x1 + 1, cy1 = Y0 + c.y1 + 1;
      if (contemTexto({x0: cx0, y0: cy0, x1: cx1, y1: cy1})) continue;
      if (rotulos.some(b => cx0 >= b.x0 && cx1 <= b.x1 && cy0 >= b.y0 && cy1 <= b.y1)) continue;
      grupos.push(c);
    }
    for (const r of imgs) {
      const c = {x0: Math.max(0, Math.floor(r.x0 - X0)), y0: Math.max(0, Math.floor(r.y0 - Y0)), x1: Math.min(W - 1, Math.ceil(r.x1 - X0)), y1: Math.min(H - 1, Math.ceil(r.y1 - Y0)), celulas: [], imagem: true};
      for (let y = c.y0; y <= c.y1; y++) for (let x = c.x0; x <= c.x1; x++) if (escuro[y * W + x]) c.celulas.push(y * W + x);
      if (c.celulas.length) grupos.push(c);
    }
    // junta manchas próximas: na mesma faixa (vão ≤ 6 pt) ou empilhadas (vão ≤ 5 pt: numerador, traço,
    // denominador), nunca de linhas de texto diferentes (alternativas vizinhas)
    const perto = (a, b) => {
      const la = a.linha ?? linhaDe(a), lb = b.linha ?? linhaDe(b);
      if (la >= 0 && lb >= 0 && la !== lb) return false;
      const vx = Math.max(a.x0, b.x0) - Math.min(a.x1, b.x1), vy = Math.max(a.y0, b.y0) - Math.min(a.y1, b.y1);
      const sob = -vy / Math.max(1, Math.min(a.y1 - a.y0, b.y1 - b.y0) + 1);
      return (vy <= 0 && vx <= 6) || (sob >= 0.4 && vx <= 12) || (vx <= 0 && vy <= 5) || (vx <= 1.5 && vy <= 1.5);
    };
    // passadas de união com janela em x (só vizinhos até 12 pt à direita), até não juntar mais nada
    for (let mudou = true; mudou;) {
      mudou = false;
      grupos.sort((a, b) => a.x0 - b.x0);
      grupos.forEach(g => { g.linha = linhaDe(g); });
      const vivo = grupos.map(() => true);
      for (let a = 0; a < grupos.length; a++) {
        if (!vivo[a]) continue;
        for (let b = a + 1; b < grupos.length && grupos[b].x0 <= grupos[a].x1 + 12; b++) {
          if (!vivo[b] || !perto(grupos[a], grupos[b])) continue;
          const A = grupos[a], B = grupos[b];
          grupos[a] = {x0: Math.min(A.x0, B.x0), y0: Math.min(A.y0, B.y0), x1: Math.max(A.x1, B.x1), y1: Math.max(A.y1, B.y1),
            celulas: A.celulas.concat(B.celulas), imagem: A.imagem || B.imagem};
          grupos[a].linha = linhaDe(grupos[a]);
          vivo[b] = false; mudou = true;
        }
      }
      grupos = grupos.filter((g, k) => vivo[k]);
    }
    const saida = [];
    for (const g of grupos) {
      const w = g.x1 - g.x0 + 1, h = g.y1 - g.y0 + 1;
      if (w < 3 || h < 3 || w * h < 30 || g.celulas.length < 12) continue;
      if (w > 20 * h || h > 20 * w) continue;
      const caixa = {x0: X0 + g.x0, y0: Y0 + g.y0, x1: X0 + g.x1 + 1, y1: Y0 + g.y1 + 1};
      if (!g.imagem && contemTexto(caixa)) continue;
      if (h > 60 && w > 30) continue;   // desenho grande sem texto: não é fórmula
      // recorte só com a tinta do grupo (vizinhos apagados), com margem branca
      const M = 4, c = document.createElement('canvas');
      c.width = (w + 2 * M) * E; c.height = (h + 2 * M) * E;
      const ctx = c.getContext('2d'), im = ctx.createImageData(c.width, c.height);
      im.data.fill(255);
      const meu = new Uint8Array(W * H);
      for (const k of g.celulas) { const x = k % W, y = (k - x) / W; for (let dy = -1; dy <= 1; dy++) for (let dx = -1; dx <= 1; dx++) { const nx = x + dx, ny = y + dy; if (nx >= 0 && ny >= 0 && nx < W && ny < H) meu[ny * W + nx] = 1; } }
      for (let y = 0; y < h + 2 * M; y++) for (let x = 0; x < w + 2 * M; x++) {
        const cx = g.x0 - M + x, cy = g.y0 - M + y;
        if (cx < 0 || cy < 0 || cx >= W || cy >= H || !meu[cy * W + cx]) continue;
        for (let yy = 0; yy < E; yy++) for (let xx = 0; xx < E; xx++) {
          const o = (((y * E + yy) * c.width) + x * E + xx) * 4, j = ((OY + cy * E + yy) * CW + OX + cx * E + xx) * 4;
          im.data[o] = px[j]; im.data[o + 1] = px[j + 1]; im.data[o + 2] = px[j + 2];
        }
      }
      ctx.putImageData(im, 0, 0);
      saida.push({...caixa, blob: await new Promise(res => c.toBlob(res, 'image/png'))});
    }
    return saida.sort((a, b) => a.y0 - b.y0 || a.x0 - b.x0);
  }

  async function renderizar(page) {
    const vp = page.getViewport({scale: ESCALA});
    const canvas = document.createElement('canvas');
    canvas.width = Math.ceil(vp.width); canvas.height = Math.ceil(vp.height);
    const ctx = canvas.getContext('2d', {willReadFrequently: true});
    ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, canvas.width, canvas.height);
    await page.render({canvasContext: ctx, viewport: vp}).promise;
    return canvas;
  }

  // Recorte (canvas) de uma região, na escala do render; juntarRecortes empilha as partes de uma
  // questão dividida (colunas ou páginas) numa imagem só, do tamanho que o Claude lê.
  function recortarCanvas(canvas, r) {
    const sx = Math.max(0, r.x0 * ESCALA), sy = Math.max(0, r.y0 * ESCALA);
    const sw = Math.max(1, Math.min(canvas.width - sx, (r.x1 - r.x0) * ESCALA)), sh = Math.max(1, Math.min(canvas.height - sy, (r.y1 - r.y0) * ESCALA));
    const c = document.createElement('canvas'); c.width = Math.round(sw); c.height = Math.round(sh);
    c.getContext('2d').drawImage(canvas, sx, sy, sw, sh, 0, 0, c.width, c.height);
    return c;
  }
  // Recorte de cada parte guardado comprimido (JPEG) até juntar: 30 questões em canvas abertos
  // somavam centenas de MB.
  function parteComprimida(canvas) {
    const fator = Math.min(1, Math.sqrt(MAX_PX_QUESTAO / (canvas.width * canvas.height)));
    let c = canvas;
    if (fator < 1) { c = document.createElement('canvas'); c.width = Math.round(canvas.width * fator); c.height = Math.round(canvas.height * fator);
      c.getContext('2d').drawImage(canvas, 0, 0, c.width, c.height); }
    return new Promise(res => c.toBlob(b => { const w = canvas.width, h = canvas.height; if (c !== canvas) c.width = c.height = 0; canvas.width = canvas.height = 0; res({blob: b, width: w, height: h}); }, 'image/jpeg', 0.94));
  }
  async function juntarRecortes(partes, opcoes = {}) {
    const recortes = [];
    for (const p of partes) {   // {blob, width, height}: o tamanho original da parte (a escala vem daí)
      const bmp = await createImageBitmap(p.blob);
      recortes.push({bmp, width: p.width, height: p.height});
    }
    try { return await juntarCanvas(recortes, opcoes); } finally { recortes.forEach(r => r.bmp.close()); }
  }
  function juntarCanvas(recortes, {maxPx = MAX_PX_QUESTAO, qualidade = 0.86} = {}) {
    const vao = recortes.length > 1 ? 6 * ESCALA : 0;
    const W = Math.max(...recortes.map(c => c.width)), H = recortes.reduce((s, c) => s + c.height, 0) + vao * (recortes.length - 1);
    const fator = Math.min(1, Math.sqrt(maxPx / (W * H)));
    const c = document.createElement('canvas'); c.width = Math.max(1, Math.round(W * fator)); c.height = Math.max(1, Math.round(H * fator));
    const ctx = c.getContext('2d'); ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, c.width, c.height);
    let y = 0;
    for (const r of recortes) {
      ctx.drawImage(r.bmp, 0, 0, r.bmp.width, r.bmp.height, 0, Math.round(y * fator), Math.round(r.width * fator), Math.round(r.height * fator));
      y += r.height + vao;
      if (vao && y < H) { ctx.fillStyle = '#d0d0d0'; ctx.fillRect(0, Math.round((y - vao / 2) * fator), c.width, Math.max(1, Math.round(fator * 2))); ctx.fillStyle = '#fff'; }
    }
    return new Promise(res => c.toBlob(b => { c.width = c.height = 0; res(b); }, 'image/jpeg', qualidade));
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
      const l = letras.filter(x => Math.abs(x.base - n.base) < 3 && x.x0 > n.x1 - 2).sort((a, b) => a.x0 - b.x0)[0];
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
    const px = pixelsDe(canvas);
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
    const tarefa = pdfjsLib.getDocument({data: new Uint8Array(buffer), isEvalSupported: false});
    const doc = await tarefa.promise;
    const paginas = [];
    let tituloLista = '';
    for (let pn = 1; pn <= doc.numPages; pn++) {
      progresso({etapa: 'lendo', pagina: pn, total: doc.numPages});
      const page = await doc.getPage(pn);
      const vp = page.getViewport({scale: 1});
      const {items} = await page.getTextContent();
      await page.getOperatorList();   // carrega as fontes: o nome diz se é negrito
      const negrito = id => {
        try {
          if (!page.commonObjs.has(id)) return false;
          const f = page.commonObjs.get(id);
          return !!(f && (f.bold || f.black || /bold|black|heavy|semibold|demibold|extrabold|,b$/i.test(f.name || '')));
        } catch { return false; }
      };
      // Os dois modelos de página: duas colunas ou uma coluna (questões na largura toda). Quem
      // decide é a largura da barra "Questão NN" (medida no recorte); o texto que atravessa o
      // meio da página é só o plano B, quando a barra não é encontrada.
      const meioPag = vp.width / 2;
      const cruzam = items.filter(it => {
        if (!it.str || it.str.trim().length < 8) return false;
        const [x] = vp.convertToViewportPoint(it.transform[4], it.transform[5]);
        return x < meioPag - 15 && x + (it.width || 0) > meioPag + 15;
      }).length;
      const modelo = umaColuna => {
        const linhas = linhasDaPagina(items, vp, umaColuna, negrito);
        const cabecalhos = linhas.filter(l => l.y0 > MARGEM_TOPO && RE_QUESTAO.test(l.texto))
          .map(l => ({col: l.col, y: l.y0, x0: l.x0, base: l.base, numero: parseInt(l.texto.match(RE_QUESTAO)[1].replace(/ /g, ''), 10)}));
        return {umaColuna, linhas, cabecalhos};
      };
      const duas = modelo(false), uma = modelo(true);
      const linhas = duas.linhas;
      if (!tituloLista) {
        const t = uma.linhas.find(l => l.texto.startsWith('Lista de Exercícios'));
        if (t) tituloLista = t.texto.split('|').slice(1).join('|').trim();
      }
      const rodape = uma.linhas.filter(l => l.y0 > vp.height * 0.85 && /Plataforma|Assaad/.test(l.texto));
      const fundo = rodape.length ? Math.min(...rodape.map(l => l.y0)) - 8 : vp.height - 30;
      paginas.push({pn, page, vp, fundo, cruzam, duas, uma, linhas, cabecalhos: duas.cabecalhos.length ? duas.cabecalhos : uma.cabecalhos});
    }

    // Até onde vai a barra colorida da "Questão NN": além do meio da página = questão na largura toda.
    function fimDaBarra(canvas, cab) {
      const y = Math.round(((cab.y + cab.base) / 2) * ESCALA);
      if (y < 0 || y >= canvas.height) return null;
      const linha = pixelsDe(canvas).subarray(y * canvas.width * 4, (y + 1) * canvas.width * 4);
      const cor = x => [linha[x * 4], linha[x * 4 + 1], linha[x * 4 + 2]];
      const x0 = Math.max(0, Math.round((cab.x0 - 3) * ESCALA));
      const c0 = cor(x0);
      if (Math.min(...c0) > 215 || Math.max(...c0) - Math.min(...c0) < 25 && Math.min(...c0) > 150) return null;   // fundo claro: sem barra
      const perto = c => Math.abs(c[0] - c0[0]) + Math.abs(c[1] - c0[1]) + Math.abs(c[2] - c0[2]) < 90;
      let ultimo = x0;
      for (let x = x0; x < canvas.width && x - ultimo < 18 * ESCALA; x++) if (perto(cor(x))) ultimo = x;   // pula as letras brancas
      return ultimo / ESCALA;
    }

    // Uma página vira partes em ordem de leitura: "nova" (começa numa barra Questão NN) ou
    // "continuação" (topo de coluna antes da 1ª barra, ou coluna sem barra): o resto da questão
    // anterior, que pode vir da outra coluna ou da página anterior.
    const temConteudo = (p, m, col, r, imagens) =>
      m.linhas.some(l => (m.umaColuna || l.col === col) && l.texto.trim().length >= 2 && !ETAPAS.includes(l.texto.trim())
        && (l.y0 + l.y1) / 2 > r.y0 && (l.y0 + l.y1) / 2 < r.y1)
      || imagens.some(f => (f.x0 + f.x1) / 2 > r.x0 && (f.x0 + f.x1) / 2 < r.x1 && (f.y0 + f.y1) / 2 > r.y0 && (f.y0 + f.y1) / 2 < r.y1);
    function partesDaPagina(p, m, imagens) {
      const partes = [], meio = p.vp.width / 2;
      for (const col of m.umaColuna ? [0] : [0, 1]) {
        const [x0, x1] = m.umaColuna ? [0, p.vp.width] : col === 0 ? [0, meio] : [meio, p.vp.width];
        const cabs = m.cabecalhos.filter(c => m.umaColuna || c.col === col).sort((a, b) => a.y - b.y);
        const topo = {x0: x0 + 2, y0: MARGEM_TOPO, x1: x1 - 2, y1: (cabs.length ? cabs[0].y : p.fundo) - 2};
        if (topo.y1 - topo.y0 > 6 && temConteudo(p, m, col, topo, imagens)) partes.push({tipo: 'continuacao', col, regiao: topo});
        cabs.forEach((c, i) => partes.push({tipo: 'nova', col, numero: c.numero,
          regiao: {x0: x0 + 2, y0: c.y - 2, x1: x1 - 2, y1: (i + 1 < cabs.length ? cabs[i + 1].y : p.fundo) - 2}}));
      }
      return partes;
    }

    // Texto (com **negrito** e [centralizado]), fórmulas sem texto e figuras de uma parte.
    async function dadosDaParte(p, m, parte, canvas, imagens, comCabecalho, pequenas = []) {
      const {regiao, col} = parte;
      const daParte = m.linhas.filter(l => (m.umaColuna || l.col === col) && (l.y0 + l.y1) / 2 > regiao.y0 && (l.y0 + l.y1) / 2 < regiao.y1)
        .sort((a, b) => a.base - b.base);
      const corpo = comCabecalho ? daParte.slice(1) : daParte;
      const esq = corpo.length ? Math.min(...corpo.map(l => l.x0)) : regiao.x0, dir = corpo.length ? Math.max(...corpo.map(l => l.x1)) : regiao.x1;
      const largura = Math.max(1, dir - esq), centro = (esq + dir) / 2;
      const centralizado = (x0, x1, n) => n >= 3 && x1 - x0 < 0.8 * largura && x0 - esq > 0.06 * largura
        && (Math.abs((x0 + x1) / 2 - centro) < 0.04 * largura || Math.abs((x0 + x1) / 2 - (regiao.x0 + regiao.x1) / 2) < 0.04 * largura);
      const dentro = imagens.filter(f => { const cx = (f.x0 + f.x1) / 2, cy = (f.y0 + f.y1) / 2;
        return cx > regiao.x0 && cx < regiao.x1 && cy > regiao.y0 && cy < regiao.y1; });
      ordemDeLeitura(dentro);
      // print de tabela: recorta só a grade (sem o texto que veio junto no print) e marca como tabela
      const tabelas = new Set();
      const aparadas = dentro.map(f => aparar(f, m.linhas)).map((f, k) => { const g = gradeDaTabela(canvas, f); if (g) { tabelas.add(k); return g; } return f; });
      // Fórmula sem texto (imagem pequena ou desenho): entra no texto como ⟦FÓRMULA #k⟧, no ponto em que
      // aparece (na linha da letra da alternativa, ou numa linha própria), e o recorte vai junto.
      const formulas = await tintaSemTexto(canvas, regiao, comCabecalho ? daParte.slice(1) : daParte, aparadas, comCabecalho ? daParte[0] : null, pequenas);
      const entradas = daParte.map((l, i) => ({y: (l.y0 + l.y1) / 2, l, i, formulas: []}));
      formulas.forEach((f, k) => {
        f.k = k;
        const alvo = entradas.filter(e => e.l && !(comCabecalho && e.i === 0)).map(e => ({e, sob: Math.min(e.l.y1, f.y1) - Math.max(e.l.y0, f.y0)}))
          .filter(x => x.sob >= 0.5 * (x.e.l.y1 - x.e.l.y0) || (x.sob > 0 && x.e.y > f.y0 && x.e.y < f.y1)).sort((a, b) => b.sob - a.sob)[0];
        if (alvo) alvo.e.formulas.push(f);
        else entradas.push({y: (f.y0 + f.y1) / 2, l: null, formulas: [f]});
      });
      entradas.sort((a, b) => a.y - b.y);
      const marca = f => `⟦FÓRMULA #${f.k}⟧`;
      const texto = entradas.map(e => {
        const {l} = e;
        if (!l) {
          const f = e.formulas[0];
          return (centralizado(f.x0, f.x1, 3) ? '[centralizado] ' : '') + marca(f);
        }
        if (comCabecalho && e.i === 0) return l.texto;
        const prefixo = centralizado(l.x0, l.x1, l.texto.trim().length) ? '[centralizado] ' : '';
        if (!e.formulas.length) return prefixo + marcadoDe(l);
        // fórmulas na linha: na posição x entre os trechos de texto
        const itens = [...(l.trechos || []).map(t => ({x: (t.x0 + t.x1) / 2, t})), ...e.formulas.map(f => ({x: f.x0, f}))].sort((a, b) => a.x - b.x);
        const pedacos = [];
        let grupo = [];
        for (const it of itens) {
          if (it.t) { grupo.push(it.t); continue; }
          if (grupo.length) pedacos.push(marcadoDe({trechos: grupo}).trim());
          grupo = []; pedacos.push(marca(it.f));
        }
        if (grupo.length) pedacos.push(marcadoDe({trechos: grupo}).trim());
        if (!l.trechos) pedacos.unshift(marcadoDe(l));
        return prefixo + pedacos.filter(Boolean).join(' ');
      });
      // Centralização por faixa: figuras lado a lado contam como um grupo (o par é que está no centro).
      const noCentro = (a, b) => b - a >= 0.85 * largura || (
        Math.abs((a + b) / 2 - centro) < 0.05 * largura || Math.abs((a + b) / 2 - (regiao.x0 + regiao.x1) / 2) < 0.05 * largura);
      const faixas = [];
      aparadas.forEach((f, k) => {
        const u = faixas.length && faixas[faixas.length - 1];
        if (u && f.y0 < u.y1 - 0.5 * Math.min(f.y1 - f.y0, u.y1 - u.y0)) { u.k.push(k); u.x0 = Math.min(u.x0, f.x0); u.x1 = Math.max(u.x1, f.x1); u.y1 = Math.max(u.y1, f.y1); }
        else faixas.push({k: [k], x0: f.x0, x1: f.x1, y0: f.y0, y1: f.y1});
      });
      const centradas = new Set(faixas.filter(u => noCentro(u.x0, u.x1)).flatMap(u => u.k));
      const figuras = [];
      for (let k = 0; k < aparadas.length; k++)
        figuras.push({regiao: {...aparadas[k], pagina: p.pn}, centralizada: centradas.has(k), tabela: tabelas.has(k),
          linha: entradas.filter(e => e.y < aparadas[k].y0).length, blob: await recortar(canvas, aparadas[k])});
      // imagem da parte só até onde há conteúdo (sem o branco até o fim da coluna); fórmulas contam
      const ys0 = [...daParte.map(l => l.y0), ...aparadas.map(f => f.y0), ...formulas.map(f => f.y0)];
      const ys1 = [...daParte.map(l => l.y1), ...aparadas.map(f => f.y1), ...formulas.map(f => f.y1)];
      const util = ys1.length ? {...regiao, y0: comCabecalho ? regiao.y0 : Math.max(regiao.y0, Math.min(...ys0) - 6), y1: Math.min(regiao.y1, Math.max(...ys1) + 8)} : regiao;
      return {texto, figuras, formulas: formulas.map(f => ({regiao: {x0: f.x0, y0: f.y0, x1: f.x1, y1: f.y1, pagina: p.pn}, blob: f.blob})),
              recorte: await parteComprimida(recortarCanvas(canvas, util))};
    }

    const questoes = [];
    const semQuestao = [];
    const ultimaComQuestao = Math.max(0, ...paginas.filter(p => p.duas.cabecalhos.length || p.uma.cabecalhos.length).map(p => p.pn));
    let aberta = null, umaColunaAnterior = false;
    for (const p of paginas) {
      const temCab = p.duas.cabecalhos.length || p.uma.cabecalhos.length;
      // página sem barra: é continuação da questão aberta se tiver texto de conteúdo e não for o gabarito
      const conteudo = p.uma.linhas.filter(l => l.y0 > MARGEM_TOPO && l.y0 < p.fundo && l.texto.trim().length >= 2 && !ETAPAS.includes(l.texto.trim()));
      const continua = aberta && conteudo.length >= 3 && !conteudo.some(l => /gabarito/i.test(l.texto)) && !gabaritoEmTexto(p.uma.linhas).pares['01'];
      if (!temCab && !continua) { semQuestao.push(p); if (p.pn > ultimaComQuestao) aberta = null; continue; }
      progresso({etapa: 'recortando', pagina: p.pn, total: doc.numPages});
      const canvas = await renderizar(p.page);
      negritoPorPalavra(canvas, p.uma.linhas, p.duas.linhas);
      const todas = await imagensDaPagina(p.page, p.vp);
      const imagens = todas.filter(r => r.x1 - r.x0 >= FIGURA_MIN && r.y1 - r.y0 >= FIGURA_MIN && r.y0 > MARGEM_TOPO);
      const pequenas = todas.filter(r => !(r.x1 - r.x0 >= FIGURA_MIN && r.y1 - r.y0 >= FIGURA_MIN) && r.y0 > MARGEM_TOPO);
      // modelo da página pela barra; sem barra, pelo texto que atravessa o meio; página só de
      // continuação segue o modelo da anterior
      const fins = p.uma.cabecalhos.map(c => fimDaBarra(canvas, c)).filter(x => x !== null);
      const umaColuna = fins.length ? fins.filter(x => x > p.vp.width / 2 + 30).length * 2 > fins.length
        : temCab ? p.cruzam >= 3 : umaColunaAnterior;
      umaColunaAnterior = umaColuna;
      const m = umaColuna ? p.uma : p.duas;
      Object.assign(p, {linhas: m.linhas, cabecalhos: m.cabecalhos, umaColuna});
      const partes = partesDaPagina(p, m, imagens);
      for (const parte of partes) {
        if (parte.tipo === 'nova') {
          aberta = {numero: parte.numero, pagina: p.pn, coluna: parte.col + 1, regiao: parte.regiao, partes: [], foraDoRecorte: []};
          questoes.push(aberta);
        } else if (!aberta) continue;   // texto antes da 1ª questão da lista (capa, instruções)
        const d = await dadosDaParte(p, m, parte, canvas, imagens, parte.tipo === 'nova', pequenas);
        aberta.partes.push({pagina: p.pn, col: parte.col, regiao: parte.regiao, ...d});
        parte.dono = aberta;
      }
      // Trava: nenhum texto ou imagem da página pode ficar fora de todas as partes.
      const dentroDe = r => partes.find(pt => r.x0 >= pt.regiao.x0 - 6 && r.x1 <= pt.regiao.x1 + Math.max(8, 0.08 * (pt.regiao.x1 - pt.regiao.x0)) && (r.y0 + r.y1) / 2 >= pt.regiao.y0 && (r.y0 + r.y1) / 2 <= pt.regiao.y1 + 2);
      const dono = r => (partes.filter(pt => pt.dono && (r.y0 + r.y1) / 2 >= pt.regiao.y0 - 2).sort((a, b) => b.regiao.y0 - a.regiao.y0)[0] || partes.find(pt => pt.dono))?.dono;
      for (const l of m.linhas) {
        // a barra "Questão NN" é da própria questão (às vezes passa uns pontos do meio da página)
        if (l.texto.trim().length < 2 || ETAPAS.includes(l.texto.trim()) || RE_QUESTAO.test(l.texto) || l.y0 < MARGEM_TOPO || l.y0 >= p.fundo - 2 || dentroDe(l)) continue;
        dono(l)?.foraDoRecorte.push(l.texto.trim().slice(0, 80));
      }
      for (const f of imagens) if (!dentroDe(f) && f.y0 >= MARGEM_TOPO && f.y0 < p.fundo) dono(f)?.foraDoRecorte.push('[imagem]');
      liberar(canvas); p.page.cleanup();
      await folga();   // devolve a vez à tela entre uma página e outra
    }
    // Junta as partes de cada questão: texto em ordem, figuras numeradas, imagem empilhada.
    for (const q of questoes) {
      const nn = String(q.numero).padStart(2, '0');
      let base = 0;
      q.figuras = q.partes.flatMap(pt => { const fs = pt.figuras.map(f => ({...f, linha: base + f.linha})); base += pt.texto.length; return fs; })
        .map((f, k) => ({nome: `Q${nn}_fig${k + 1}`, ...f}));
      // fórmulas: #k de cada parte → nome da questão (Q35_f1, Q35_f2…), na ordem do texto
      q.formulas = [];
      q.textoPdf = q.partes.map(pt => pt.texto.join('\n').replace(/⟦FÓRMULA #(\d+)⟧/g, (m0, k) => {
        const nome = `Q${nn}_f${q.formulas.length + 1}`;
        q.formulas.push({nome, ...pt.formulas[+k]});
        return `⟦FÓRMULA ${nome}⟧`;
      })).join('\n');
      q.regioes = q.partes.map(pt => ({pagina: pt.pagina, ...pt.regiao}));
      q.imagem = await juntarRecortes(q.partes.map(pt => pt.recorte));
      delete q.partes;
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
      const menor = Math.min(...numeros), proximo = menor + Object.keys(gabaritoPdf).length;   // a lista pode não começar na 1
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
      liberar(c); pg.page.cleanup();
      if (numeros.every(n => gabaritoPdf[String(n).padStart(2, '0')])) break;
    }
    const lidas = Object.keys(gabaritoPdf).length;
    const completo = numeros.length > 0 && numeros.every(n => gabaritoPdf[String(n).padStart(2, '0')]);
    if (completo) gabaritoMotivo = null;
    else {
      gabaritoMotivo = lidas ? `a tabela tem ${lidas} respostas, a lista tem ${numeros.length} questões` : (motivos.join('; ') || gabaritoMotivo);
      gabaritoPdf = {};
      for (const n of Object.keys(gabaritoRecortes)) delete gabaritoRecortes[n];
    }
    const nome = arquivo.name || 'lista.pdf';
    // fecha o documento no pdf.js (senão cada lista fica na memória do Worker)
    try { await tarefa.destroy(); } catch {}
    return {
      arquivo: nome, hash: hashPdf, titulo: tituloLista || nome.replace(/\.pdf$/i, '').replace(/_/g, ' '),
      tipo: /simulado/i.test(nome + ' ' + tituloLista) ? 'simulado' : 'lista',
      etapas: inicio, questoes, faltando, repetidos, paginaGabarito, gabaritoPdf, gabaritoMotivo, gabaritoRecortes, paginas: doc.numPages,
    };
  }

  return {segmentar, gabaritoNaImagem, gabaritoEmTexto, linhasDaPagina, gradeDaTabela, ETAPAS, ESCALA,
};
})();
