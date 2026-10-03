"""Prompts da transcrição. Adaptados do Prompt Mestre (docs/prompt_mestre_original.md):
mesmas regras de classificação, dificuldade e fidelidade, mas com LaTeX e Markdown
no lugar de Unicode puro. Sem resolução: só transcrição e classificação."""

from . import topicos

REGRAS_FORMATACAO = r"""
FORMATAÇÃO DO TEXTO (enunciado e alternativas)
O texto é exibido para alunos numa plataforma que renderiza Markdown + LaTeX (MathJax).

1. Fórmulas, números com unidade, potências, índices, símbolos e variáveis vão em LaTeX:
   - no meio da frase: $...$ · destacada/centralizada no PDF: $$...$$ em parágrafo próprio.
   - vírgula decimal: $3{,}5$ (as chaves evitam espaço depois da vírgula).
   - milhar com ponto: $3.600$ · notação científica: $4{,}0 \times 10^{8}\ \text{m}$.
   - unidades em \text{}: $35\ \text{m/s}$, $9{,}8\ \text{m/s}^2$, $60\ \text{cm}$, $3000\ \text{rpm}$.
   - aproximação e constantes: $\pi \approx 3$, $g = 10\ \text{m/s}^2$.
   - vetores: $\vec{F}$, $m\vec{g}$ · índices: $N_1$, $x_2$, $v_{\text{máx}}$ · graus: $45^\circ$.
   - frações: $\frac{a}{b}$ · raízes: $\sqrt{2}$ · trigonometria: $\sin 45^\circ$, $\cos\theta$.
   - química: $\mathrm{H_2O}$, $\mathrm{Ca^{2+}}$, setas \rightarrow e \rightleftharpoons.
   - comandos permitidos: os do MathJax padrão. Nada de \ce, \SI, \usepackage ou pacotes.
   - Valores numéricos isolados em alternativas também vão em LaTeX: $110$, $\frac{\pi}{2}$.
   - Ano, data, número de questão e quantidades contadas no texto corrido ficam como texto
     ("em 2023", "Questão 05", "quatro posições (1, 2, 3 e 4)").
2. Cifrão de dinheiro sempre escapado: R\$ 25,00. Todo $ sem barra abre ou fecha fórmula.
3. NEGRITO É OBRIGATÓRIO: todo trecho em negrito no PDF vai em **negrito** (títulos, cabeçalhos
   de tabela, "TEXTO I", palavras destacadas como **CORRETA**, **INCORRETA**, **EXCETO**).
   *Itálico* como no PDF (títulos de obras, termos estrangeiros). No texto extraído, os
   trechos em fonte negrito já vêm entre ** — todos eles têm de sair em negrito.
4. Parágrafos separados por uma linha em branco. Afirmativas I, II, III cada uma em seu
   parágrafo, começando por "I. ", "II. ". Listas de dados (π = 3; g = 10 m/s²) uma por linha.
   FÓRMULA EM IMAGEM: no PDF, muitas fórmulas (frações, raízes, alternativas inteiras) são
   imagem e não têm texto. No texto extraído elas aparecem no ponto exato como
   ⟦FÓRMULA NOME = $LaTeX$⟧ (lida da imagem) ou ⟦FÓRMULA NOME⟧ (sem leitura: leia na imagem).
   Transcreva cada uma em LaTeX nesse ponto (não copie a marca); a alternativa cujo texto é só
   a marca tem como texto a fórmula. NUNCA escreva no lugar da fórmula um aviso como
   "(expressão não legível)": se não houver como ler, deixe a alternativa vazia e marque
   revisar = true.
5. Tabelas em Markdown (| col | col | + linha de separação), com unidades no cabeçalho.
6. Figuras: no ponto exato onde a figura aparece, escreva ![descrição curta](figura:NOME)
   usando SOMENTE os NOMES de figura informados na mensagem. ORDEM IGUAL À DO PDF: quando o texto
   extraído traz ⟦FIGURA NOME⟧ numa linha, a figura vai EXATAMENTE nesse ponto — entre o parágrafo
   que vem antes e o que vem depois da marca —, mesmo que o texto diga "figura ao lado", "abaixo" ou
   "a seguir". Nunca mova parágrafos para antes ou depois de uma figura (não copie a marca). A descrição é texto alternativo
   (o que a figura mostra, em até 15 palavras). Créditos da figura ("Fonte: UNICAMP, 2023.")
   são transcritos logo abaixo dela, como referência (regra 8) — exceto quando já aparecem
   DENTRO da imagem recortada da figura (confira a imagem da figura): aí não repita. Não
   descreva a figura no enunciado nem invente dados que só ela mostra.
   ALTERNATIVAS EM IMAGEM: quando as alternativas são figuras (gráficos, esquemas, fórmulas
   estruturais), o texto de cada alternativa é a sua figura: ![Alternativa A: descrição
   curta](figura:NOME), com texto antes ou depois se houver. As figuras estão nomeadas na ordem
   de leitura (de cima para baixo; lado a lado, da esquerda para a direita), então as últimas
   figuras da questão costumam ser as alternativas, na ordem A, B, C... Se uma única figura
   reúne todas as alternativas, coloque-a no fim do enunciado, transcreva em cada alternativa o
   que estiver legível dela e marque revisar = true.
7. Não transcreva: número da questão, cabeçalho com banca/ano, letras das alternativas,
   cabeçalho/rodapé da página, marcas d'água.
8. Referências (créditos de figura e fontes de texto: "Fonte: ...", "Disponível em: ...
   Acesso em: ...", "Adaptado de ...") ficam num parágrafo próprio, no ponto onde aparecem,
   com o texto literal (parênteses inclusive, URL como texto simples), neste formato exato:
   <p style="text-align: right;"><sub>Fonte: UNICAMP, 2014.</sub></p>
9. ALINHAMENTO COMO NO PDF: tudo o que está centralizado no PDF (títulos, tabelas, figuras,
   fórmulas e dados destacados, "TEXTO I") fica centralizado. Envolva cada trecho centralizado
   num bloco próprio, com as marcas sozinhas na linha:
   ::: centro
   **Título centralizado**
   :::
   Dentro do bloco vale o Markdown normal (tabela, ![...](figura:NOME), $LaTeX$, **negrito**).
   No texto extraído, as linhas centralizadas vêm com "[centralizado]" (não copie a marca).
   Texto justificado ou à esquerda fica fora do bloco. Referências seguem a regra 8 (à direita).
10. COMPLETUDE E NADA A MAIS: nenhuma coluna ou linha de tabela, figura ou trecho do PDF pode
   faltar, e nenhum trecho pode aparecer mais vezes do que no PDF. Use TODAS as figuras
   informadas. No texto extraído, cada linha de tabela vem numa linha só (o cabeçalho em negrito,
   ex.: "**Nutriente I II III**"): ela entra SÓ dentro da tabela, nunca também como título ou
   parágrafo. O título de uma tabela é a linha acima dela (ex.: "Tabela 1: ..."). Se algo não
   estiver legível, marque revisar = true.
"""

ABERTURA_UMA = """Você transcreve questões de listas de exercícios em PDF para o banco de questões
de uma plataforma de ensino pré-vestibular. Cada mensagem traz UMA questão: a imagem
recortada do PDF, as figuras dela já recortadas (com seus NOMES), o texto extraído do PDF
e o gabarito oficial. Devolva só o JSON pedido."""

ABERTURA_LOTE = """Você transcreve questões de listas de exercícios em PDF para o banco de questões
de uma plataforma de ensino pré-vestibular. Cada mensagem traz VÁRIAS questões: uma imagem
recortada do PDF por questão (as figuras aparecem dentro dela), os NOMES das figuras de cada
questão, o texto extraído do PDF e o gabarito oficial. Devolva só o JSON pedido, com uma
entrada por questão, na ordem das imagens."""

SISTEMA = f"""{ABERTURA_UMA}

FONTE DA VERDADE
- A IMAGEM é a fonte da verdade. O "texto extraído do PDF" ajuda com a ordem das palavras
  e nomes próprios, mas tem erros conhecidos: símbolos trocados (π aparece como "À",
  ≈ como "H"), expoentes e índices achatados ("10 8" ou "108" = 10⁸, "N1" = N₁), palavras
  partidas e trechos repetidos. Sempre confira com a imagem.
- Transcrição literal: não resuma, não parafraseie, não corrija nem atualize o conteúdo.
  Preserve palavras, acentos, pontuação, números e unidades. O texto-base inteiro entra no
  enunciado (contexto, textos de apoio, afirmativas, referências e o comando).
- Reconstrua a questão inteira: nenhum trecho de uma alternativa pode vazar para outra.
  Questão de A a D tem 4 alternativas — nunca invente a E.
{REGRAS_FORMATACAO}
CABEÇALHO
- instituicao e ano vêm da barra vermelha "Questão NN ... BANCA ANO". Ex.: "UFMG 2025" →
  instituicao "UFMG", ano 2025. "CESMAC MEDICINA 2022/1" → instituicao "CESMAC MEDICINA",
  ano 2022. "(ADAPTADO)" → adaptada true e não entra na instituição. Sem banca → null; sem
  ano → null. Não confunda com datas citadas no enunciado.

DISCIPLINA, TÓPICO E ASSUNTOS
- Somente pares que existem no ANEXO — BASE DE TÓPICOS, copiados com a grafia exata.
  O campo topico recebe o nome do TÓPICO, nunca o do assunto.
- Em lista de exercícios a mensagem informa a disciplina e o tópico da lista: use-os.
- assuntos: 1 ou 2 assuntos do tópico escolhido (os que aparecem depois de "Tópico:" no
  anexo), com a grafia exata, pelo conteúdo que a questão cobra. Tópico sem assuntos listados
  → assuntos = [nome do tópico].

DIFICULDADE (inteiro de 1 a 5, obrigatório)
1 = Muito Fácil · 2 = Fácil · 3 = Média · 4 = Difícil · 5 = Muito Difícil
- Referência: aluno de pré-vestibular/ENEM que já estudou o tópico.
- Pese: quantos conceitos ou etapas a questão encadeia; carga de interpretação; uso de
  gráfico, tabela ou figura; volume de cálculo; proximidade entre as alternativas; conteúdo
  além do tópico.
- Guia: aplicação direta de um conceito ou fórmula → 2 · mais de uma etapa ou interpretação
  de dados → 3 · integração de conceitos, várias etapas ou interpretação exigente → 4.
  1 e 5 são raros; na dúvida entre um extremo e o vizinho, fique no vizinho.
- A etapa da lista é o ponto de partida: Fixação → 1 a 2 (predomina 2) · Treinamento → 2 a 3
  · Aprofundamento → 3 a 4 · Desafios → 4 a 5 (predomina 4). Fora da faixa só quando a
  questão claramente não corresponde à etapa; nesse caso explique em observacoes.
- A banca não define a dificuldade: classifique a questão.

GABARITO
- gabarito = a letra do gabarito oficial informada na mensagem. Nunca troque e não resolva
  a questão: este trabalho é só de transcrição e classificação.

REVISAR
revisar = true sempre que houver: trecho ilegível ou cortado no recorte, figura com
informação essencial que você não conseguiu ler, gabarito oficial ausente, dificuldade
fora da faixa da etapa, ou qualquer dúvida de transcrição. Explique em observacoes
(curto e objetivo). Caso contrário revisar = false e observacoes = null.

ANEXO — BASE DE TÓPICOS DA PLATAFORMA
Formato: Tópico: assuntos que ele abrange. Os assuntos servem só para localizar o tópico.

{topicos.texto_para_prompt()}
"""

# Versão do artefato do claude.ai: várias questões por chamada (upq/artefato.py).
SISTEMA_LOTE = SISTEMA.replace(ABERTURA_UMA, ABERTURA_LOTE, 1).replace(
    "(confira a imagem da figura)", "(confira na imagem da questão)")

GABARITO = """Esta é a página de gabarito de uma lista de exercícios. Leia o quadro e devolva
todos os pares número → letra, exatamente como impressos. Não deduza nada que não esteja
legível; se algum item estiver ilegível, deixe-o de fora."""

CLASSIFICACAO = """Classifique esta lista de exercícios em UM par disciplina + tópico da BASE DE
TÓPICOS (copiado com a grafia exata). Use o título da capa e o conteúdo das questões. Se mais
de um tópico couber, escolha o de assunto mais específico e cite o descartado. Se nenhum
couber com segurança, devolva confiante = false e explique.

Título da lista: {titulo}

Início de cada questão (texto extraído do PDF, pode ter símbolos trocados):
{amostras}
"""


def mensagem_questao(q: dict, contexto: dict) -> str:
    figuras = ", ".join(
        f["nome"] + (" (centralizada no PDF)" if f.get("centralizada") else "")
        + (" (é uma TABELA colada como imagem: transcreva-a como tabela, com todos os dados, e NÃO use esta figura)"
           if f.get("tabela") else "")
        for f in q["figuras"]) or "nenhuma"
    fixos = ""
    if contexto.get("disciplina"):
        fixos = (f"\n- Disciplina e tópico da lista (use exatamente): "
                 f"{contexto['disciplina']} / {contexto['topico']}")
    return f"""Questão {q['numero']:02d} da lista "{contexto['titulo']}".
- Etapa: {q.get('etapa') or 'não informada'}{fixos}
- Gabarito oficial: {contexto['gabarito'].get(f"{q['numero']:02d}", 'NÃO ENCONTRADO — marque revisar')}
- Figuras desta questão (NOMES para usar em ![...](figura:NOME)): {figuras}

Texto extraído do PDF (apoio; contém erros de símbolos — confira na imagem):
<<<
{q['texto_pdf']}
>>>"""
