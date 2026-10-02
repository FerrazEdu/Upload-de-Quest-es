/* Leitura de fórmula em imagem → LaTeX no navegador (pix2tex / LaTeX-OCR, versão ONNX do RapidLaTeXOCR).
 * Usada quando o Claude desta visualização não recebe imagens: as fórmulas que o PDF traz como imagem
 * (sem texto) seriam perdidas. Arquivos publicados com a página, em formula/ (scripts/preparar_formulas.sh):
 *   ort.bundle.js        onnxruntime-web (só wasm, sem threads)
 *   ort.wasm.txt…        runtime wasm, em base64 e em pedaços (o artefato só serve tipos web comuns)
 *   resizer / encoder / decoder .txt…   modelos (pesos em float16 + Cast; decoder em int8), base64
 *   tokenizer.json       vocabulário
 *
 *   const leitor = await UPQFormulas.carregar(urlBase)
 *   const {latex, votos, de} = await leitor.ler(blob)
 *
 * Roda num Worker (a conta não trava a página; a memória do modelo fica fora dela). Se o navegador
 * não deixar criar o Worker, roda na página, cedendo a vez à tela entre os passos.
 */
function fabricaFormulas() {
  const MAX_W = 672, MAX_H = 192, MIN_W = 32, MIN_H = 32, BOS = 1, EOS = 2, MAX_TOKENS = 400;
  const MEDIA = 0.7931 * 255, DESVIO = 0.1738 * 255;
  let carregando = null;

  async function baixarBase64(url, partes) {
    const pedacos = [];
    for (let k = 1; k <= partes; k++) {
      const r = await fetch(`${url}.${k}.txt`);
      if (!r.ok) throw new Error(`não carregou ${url}.${k}.txt (${r.status})`);
      pedacos.push(await r.text());
    }
    const bin = atob(pedacos.join('').replace(/\s+/g, ''));
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    return bytes;
  }

  function carregar(base, progresso = () => {}) {
    if (carregando) return carregando;
    carregando = (async () => {
      const man = await (await fetch(base + 'manifesto.json')).json();
      progresso('runtime');
      // módulo ES do onnxruntime; se a página não aceitar import() do arquivo, tenta por blob
      let ort;
      try { ort = await import(base + 'ort.bundle.js'); }
      catch (e) {
        const codigo = await (await fetch(base + 'ort.bundle.js')).text();
        ort = await import(URL.createObjectURL(new Blob([codigo], {type: 'text/javascript'})));
      }
      ort.env.wasm.numThreads = 1;
      ort.env.wasm.proxy = false;
      ort.env.wasm.wasmBinary = (await baixarBase64(base + 'ort.wasm', man['ort.wasm'])).buffer;
      const sessao = async nome => {
        progresso(nome);
        const bytes = await baixarBase64(base + nome, man[nome]);
        return ort.InferenceSession.create(bytes, {executionProviders: ['wasm'], graphOptimizationLevel: 'all'});
      };
      const resizer = await sessao('resizer'), encoder = await sessao('encoder'), decoder = await sessao('decoder');
      const tok = await (await fetch(base + 'tokenizer.json')).json();
      const vocab = [];
      for (const [t, id] of Object.entries(tok.model.vocab)) vocab[id] = t;
      for (const t of tok.added_tokens || []) vocab[t.id] = t.content;
      return {ler: img => ler({ort, resizer, encoder, decoder, vocab}, img)};
    })();
    carregando.catch(() => { carregando = null; });
    return carregando;
  }

  // ---- pré-processamento (igual ao do pix2tex: cinza, recorte da tinta, múltiplos de 32, escala)
  const novaTela = (w, h) => {
    w = Math.max(1, w); h = Math.max(1, h);
    if (typeof document === 'undefined') return new OffscreenCanvas(w, h);
    const c = document.createElement('canvas'); c.width = w; c.height = h; return c;
  };
  const folga = () => typeof document === 'undefined' ? null : new Promise(r => setTimeout(r, 0));
  function cinzaDe(c) {
    const d = c.getContext('2d', {willReadFrequently: true}).getImageData(0, 0, c.width, c.height).data, g = new Float32Array(c.width * c.height);
    for (let i = 0, k = 0; k < g.length; i += 4, k++) g[k] = (d[i] * 299 + d[i + 1] * 587 + d[i + 2] * 114) / 1000;   // PIL "L"
    return g;
  }
  function deCinza(g, w, h) {
    const c = novaTela(w, h), ctx = c.getContext('2d'), im = ctx.createImageData(w, h);
    for (let k = 0; k < g.length; k++) { const v = Math.max(0, Math.min(255, Math.floor(g[k]))); im.data[4 * k] = im.data[4 * k + 1] = im.data[4 * k + 2] = v; im.data[4 * k + 3] = 255; }
    ctx.putImageData(im, 0, 0);
    return c;
  }
  // tinta escura sobre fundo claro, recortada à caixa da tinta e completada com branco até múltiplos de 32
  function pad(c) {
    const W = c.width, H = c.height;
    let g = cinzaDe(c), mn = 255, mx = 0;
    for (const v of g) { if (v < mn) mn = v; if (v > mx) mx = v; }
    const amp = mx - mn || 1;
    let soma = 0;
    for (let k = 0; k < g.length; k++) { g[k] = (g[k] - mn) / amp * 255; soma += g[k]; }
    const claro = soma / g.length > 128;
    if (!claro) for (let k = 0; k < g.length; k++) g[k] = 255 - g[k];
    let x0 = W, y0 = H, x1 = -1, y1 = -1;
    for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) if (g[y * W + x] < 128) { if (x < x0) x0 = x; if (x > x1) x1 = x; if (y < y0) y0 = y; if (y > y1) y1 = y; }
    if (x1 < 0) { x0 = 0; y0 = 0; x1 = W - 1; y1 = H - 1; }
    const w = x1 - x0 + 1, h = y1 - y0 + 1, PW = Math.ceil(w / 32) * 32, PH = Math.ceil(h / 32) * 32;
    const out = new Float32Array(PW * PH).fill(255);
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) out[y * PW + x] = Math.floor(g[(y0 + y) * W + x0 + x]);
    return deCinza(out, PW, PH);
  }
  function redimensionar(c, w, h) {
    const o = novaTela(w, h), ctx = o.getContext('2d');
    ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, w, h);
    ctx.imageSmoothingEnabled = true; ctx.imageSmoothingQuality = 'high';
    ctx.drawImage(c, 0, 0, c.width, c.height, 0, 0, w, h);
    return o;
  }
  function minmax(c) {
    const r = Math.max(c.width / MAX_W, c.height / MAX_H);
    if (r > 1) c = redimensionar(c, Math.max(1, Math.floor(c.width / r)), Math.max(1, Math.floor(c.height / r)));
    if (c.width < MIN_W || c.height < MIN_H) {
      const o = novaTela(Math.max(c.width, MIN_W), Math.max(c.height, MIN_H)), ctx = o.getContext('2d');
      ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, o.width, o.height); ctx.drawImage(c, 0, 0); c = o;
    }
    return c;
  }
  function tensor(ort, c) {
    const g = cinzaDe(c), t = new Float32Array(g.length);
    for (let k = 0; k < g.length; k++) t[k] = (Math.round(g[k]) - MEDIA) / DESVIO;
    return new ort.Tensor('float32', t, [1, 1, c.height, c.width]);
  }
  const argmax = (a, ini = 0, fim = a.length) => { let k = ini; for (let i = ini; i < fim; i++) if (a[i] > a[k]) k = i; return k - ini; };

  async function paraCanvas(img) {
    if (typeof HTMLCanvasElement !== 'undefined' && img instanceof HTMLCanvasElement) return img;
    const bmp = await createImageBitmap(img);
    const c = novaTela(bmp.width, bmp.height), ctx = c.getContext('2d');
    ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, c.width, c.height); ctx.drawImage(bmp, 0, 0);
    return c;
  }

  // Lê em três escalas e fica com a leitura em que a maioria concorda (fórmula pequena às vezes troca
  // um símbolo numa escala só); sem maioria, lê em mais duas. Desempate: leitura sem símbolo raro
  // (\aleph no lugar de 8…), depois a de maior confiança. `votos`/`de` dizem quanto concordaram.
  const ESCALAS = [1, 0.75, 1.5], EXTRAS = [0.6, 1.25];
  const RARO = /\\(aleph|beth|gimel|daleth|mho|wp|Re|Im|mathbf|mathfrak|propto|natural|flat|sharp|clubsuit|spadesuit|heartsuit|diamondsuit|bigstar|maltese|S|P)\b/;
  const chave = t => t.replace(/\\[,;:! ]|\s|[{}]/g, '').replace(/\\left|\\right/g, '');
  async function ler(m, img) {
    const base = await paraCanvas(img), leituras = [];
    const em = e => e === 1 ? base : redimensionar(base, Math.max(8, Math.round(base.width * e)), Math.max(8, Math.round(base.height * e)));
    const votar = () => {
      const grupos = new Map();
      for (const l of leituras) { const k = chave(l.latex); if (!grupos.has(k)) grupos.set(k, []); grupos.get(k).push(l); }
      return [...grupos.values()].sort((a, b) => b.length - a.length || RARO.test(a[0].latex) - RARO.test(b[0].latex)
        || Math.max(...b.map(x => x.media)) - Math.max(...a.map(x => x.media)))[0];
    };
    for (const e of ESCALAS) leituras.push(await lerUma(m, em(e)));
    let melhor = votar();
    if (melhor.length < 2) { for (const e of EXTRAS) leituras.push(await lerUma(m, em(e))); melhor = votar(); }
    const escolhida = [...melhor].sort((a, b) => b.media - a.media)[0];
    return {...escolhida, votos: melhor.length, de: leituras.length, leituras: leituras.map(l => l.latex)};
  }

  async function lerUma(m, img) {
    const {ort} = m;
    const entrada = minmax(pad(img));
    // o "resizer" escolhe a largura em que a fórmula fica na escala do treino
    let r = 1, w = entrada.width, h = entrada.height, final = null;
    for (let i = 0; i < 10; i++) {
      h = Math.floor(h * r);
      const p = pad(minmax(redimensionar(entrada, w, h)));
      final = tensor(ort, p);
      const out = (await m.resizer.run({[m.resizer.inputNames[0]]: final}))[m.resizer.outputNames[0]];
      w = (argmax(out.data) + 1) * 32;
      if (w === p.width) break;
      r = w / p.width;
    }
    const contexto = (await m.encoder.run({[m.encoder.inputNames[0]]: final}))[m.encoder.outputNames[0]];
    const ids = [BOS];
    let minimo = 1, somaLog = 0;
    for (let passo = 0; passo < MAX_TOKENS; passo++) {
      if (passo % 8 === 7) await folga();
      const x = new ort.Tensor('int64', BigInt64Array.from(ids.map(BigInt)), [1, ids.length]);
      const mascara = new ort.Tensor('bool', new Uint8Array(ids.length).fill(1), [1, ids.length]);
      const saida = (await m.decoder.run({x, mask: mascara, context: contexto}))[m.decoder.outputNames[0]];
      const V = saida.dims[2], base = (ids.length - 1) * V, d = saida.data;
      const k = argmax(d, base, base + V);
      let mx = -Infinity, soma = 0;
      for (let i = base; i < base + V; i++) if (d[i] > mx) mx = d[i];
      for (let i = base; i < base + V; i++) soma += Math.exp(d[i] - mx);
      const p = 1 / soma;   // probabilidade do token escolhido
      minimo = Math.min(minimo, p); somaLog += Math.log(p);
      ids.push(k);
      if (k === EOS) break;
    }
    const tokens = ids.slice(1).filter(i => i > 2).map(i => m.vocab[i] ?? '');
    const latex = enxugar(posProcessar(tokens.join('').replace(/Ġ/g, ' ').trim())).replace(/(\\[,;:!]|\\ )+$/, '').trim();
    return {latex, confianca: minimo, media: Math.exp(somaLog / Math.max(1, ids.length - 1))};
  }

  // mesmo pós-processamento do pix2tex: tira espaços que não separam comandos
  function posProcessar(s) {
    const reTexto = /(\\(operatorname|mathrm|text|mathbf)\s?\*? {.*?})/g;
    s = s.replace(reTexto, m0 => m0.replace(/ /g, ''));
    const letra = '[a-zA-Z]', naoLetra = '[\\W_^\\d]';
    for (;;) {
      let n = s.replace(new RegExp(`(?!\\\\ )(${naoLetra})\\s+?(${naoLetra})`, 'g'), '$1$2');
      n = n.replace(new RegExp(`(?!\\\\ )(${naoLetra})\\s+?(${letra})`, 'g'), '$1$2');
      n = n.replace(new RegExp(`(${letra})\\s+?(${naoLetra})`, 'g'), '$1$2');
      if (n === s) break;
      s = n;
    }
    return s;
  }

  // Chaves redundantes em volta de um comando inteiro ("k{\\frac{q}{a}}" → "k\\frac{q}{a}"); ficam as que
  // são argumento (depois de comando que recebe argumento, de "}", "^" ou "_").
  function enxugar(s) {
    for (let i = 0; i < s.length; i++) {
      if (s[i] !== '{' || s[i + 1] !== '\\') continue;
      const antes = s.slice(0, i);
      if (/[\^_}]$|\\(frac|dfrac|tfrac|sqrt|text|mathrm|mathbf|mathit|mathcal|boldsymbol|vec|hat|bar|dot|ddot|tilde|overline|underline|overrightarrow|operatorname|binom)\s*$/.test(antes)) continue;
      let prof = 0, j = i;
      for (; j < s.length; j++) { if (s[j] === '{') prof++; else if (s[j] === '}' && --prof === 0) break; }
      if (j >= s.length) break;
      const dentro = s.slice(i + 1, j), cmd = dentro.match(/^\\[a-zA-Z]+/);
      if (!cmd) continue;
      // o miolo tem de ser só o comando com seus argumentos {…}{…}
      let k = cmd[0].length, ok = true;
      while (k < dentro.length) {
        if (dentro[k] !== '{') { ok = false; break; }
        let pr = 0, t = k;
        for (; t < dentro.length; t++) { if (dentro[t] === '{') pr++; else if (dentro[t] === '}' && --pr === 0) break; }
        k = t + 1;
      }
      if (ok) { s = antes + dentro + s.slice(j + 1); i--; }
    }
    return s;
  }

  return {carregar, posProcessar, enxugar};
}

const UPQFormulas = (() => {
  const local = fabricaFormulas();
  let carregando = null;
  // Worker com uma cópia deste mesmo código (fabricaFormulas), falando por mensagens.
  function noWorker(base) {
    const fonte = `${fabricaFormulas.toString()}
const F = fabricaFormulas(); let leitor = null;
self.onmessage = async e => {
  const {id, tipo, base, blob} = e.data;
  try {
    if (tipo === 'carregar') { leitor = await F.carregar(base); self.postMessage({id, ok: true}); }
    else self.postMessage({id, ok: true, r: await leitor.ler(blob)});
  } catch (err) { self.postMessage({id, ok: false, erro: String(err && err.message || err)}); }
};`;
    const w = new Worker(URL.createObjectURL(new Blob([fonte], {type: 'text/javascript'})));
    let seq = 0;
    const pendentes = new Map();
    w.onmessage = e => { const p = pendentes.get(e.data.id); if (!p) return; pendentes.delete(e.data.id); e.data.ok ? p.ok(e.data.r) : p.falha(new Error(e.data.erro)); };
    w.onerror = e => { for (const p of pendentes.values()) p.falha(new Error(e.message || 'o Worker do leitor de fórmulas parou')); pendentes.clear(); };
    const pedir = msg => new Promise((ok, falha) => { const id = ++seq; pendentes.set(id, {ok, falha}); w.postMessage({...msg, id}); });
    return pedir({tipo: 'carregar', base}).then(() => ({ler: blob => pedir({tipo: 'ler', blob}), modo: 'worker'}),
      e => { w.terminate(); throw e; });
  }
  function carregar(base) {
    if (carregando) return carregando;
    carregando = (async () => {
      try { if (typeof Worker !== 'undefined' && typeof OffscreenCanvas !== 'undefined') return await noWorker(base); }
      catch (e) { console.warn('leitor de fórmulas sem Worker:', e); }
      const l = await local.carregar(base);
      return {ler: l.ler, modo: 'página'};
    })();
    carregando.catch(() => { carregando = null; });
    return carregando;
  }
  return {carregar, posProcessar: local.posProcessar, enxugar: local.enxugar};
})();
