# Especificação da Planilha de Questões (v1)

Este documento é o **contrato** entre três partes:

1. **A IA** que lê o PDF da lista e gera a planilha (ver `prompts/gerar_planilha.md`);
2. **O validador** (`ferramentas/validar_planilha.py`), que confere a planilha antes do envio;
3. **O aplicativo de importação**, que lê a planilha e cadastra no banco de questões.

Se as três partes seguirem exatamente estas regras, a formatação (negrito, itálico,
LaTeX, tabelas, imagens) chega intacta ao banco de questões.

---

## 1. Formato do arquivo

- Arquivo `.xlsx` (preferencial) ou `.csv` em **UTF-8**, separado por `;`.
- **Uma linha = uma questão.** A primeira linha contém os nomes das colunas abaixo, exatamente
  como escritos (minúsculas, sem acento, com `_`).
- Nome do arquivo: `<codigo_lista>.xlsx` — o mesmo código do PDF (ex.: `MAT-EM2-L07.xlsx`
  junto de `MAT-EM2-L07.pdf`).

## 2. Colunas

| Coluna | Obrigatória | Conteúdo | Exemplo |
|---|---|---|---|
| `codigo_lista` | sim | Código da lista (igual ao nome do PDF) | `MAT-EM2-L07` |
| `numero` | sim | Número da questão na lista (inteiro) | `12` |
| `pagina` | sim | Página do PDF onde a questão **começa** (1 = primeira) | `4` |
| `tipo` | sim | `objetiva`, `discursiva` ou `verdadeiro_falso` | `objetiva` |
| `disciplina` | sim | Nome da disciplina | `Matemática` |
| `topico` | sim | Tópico | `Funções` |
| `assunto` | sim | Assunto dentro do tópico | `Função quadrática` |
| `dificuldade` | sim | `facil`, `media` ou `dificil` | `media` |
| `ano` | não | Ano da questão (4 dígitos) | `2023` |
| `fonte` | não | Vestibular/banca/origem | `ENEM` |
| `enunciado` | sim | Texto da questão (ver §3) | |
| `alt_a` … `alt_e` | sim se objetiva | Texto de cada alternativa, **sem** a letra `a)` na frente | `$x = 2$` |
| `gabarito` | sim | Objetiva: uma letra `A`–`E`. Discursiva: resposta esperada. V/F: sequência como `VFFV` | `C` |
| `resolucao` | não | Resolução comentada (ver §3) | |
| `revisar` | não | `SIM` quando a IA não teve certeza de algo; explicar em `observacoes` | `SIM` |
| `observacoes` | não | Notas para o revisor humano (não vão para o banco) | `Gabarito ilegível no PDF` |

Alternativas não usadas (ex.: questão com 4 alternativas) ficam **vazias**.

## 3. Marcação de texto (enunciado, alternativas, gabarito discursivo, resolução)

Todo o texto rico usa **apenas** as marcações abaixo. Qualquer outra coisa é texto puro.

### 3.1 Formatação

| Efeito | Escreva | Observação |
|---|---|---|
| **Negrito** | `**texto**` | |
| *Itálico* | `*texto*` | |
| Sublinhado | `<u>texto</u>` | |
| Sobrescrito fora de fórmula | `<sup>2</sup>` | ex.: `1<sup>o</sup>` |
| Subscrito fora de fórmula | `<sub>2</sub>` | |
| Quebra de linha | `<br>` | **Nunca** use Enter dentro da célula |
| Novo parágrafo | `<br><br>` | |
| Lista de itens (I, II, III…) | `<br>I. texto<br>II. texto` | |

### 3.2 Matemática, Física e Química (LaTeX)

| Caso | Escreva |
|---|---|
| Fórmula no meio do texto | `$...$` → `a função $f(x) = x^2 - 3x$ é` |
| Fórmula destacada (centralizada) | `$$...$$` → `$$\int_0^1 x\,dx$$` |
| Decimal com vírgula | `$3{,}5$` (as chaves evitam espaço extra após a vírgula) |
| Unidades | `$9{,}8\ \text{m/s}^2$` |
| Fórmulas químicas | `$\mathrm{H_2SO_4}$`, `$\mathrm{Fe^{3+}}$` |
| Reação | `$\mathrm{2H_2 + O_2 \rightarrow 2H_2O}$` |
| Texto dentro da fórmula | `\text{...}` |
| Cifrão de dinheiro | `R\$ 25,00` — **sempre** escape o `$` de dinheiro com `\` |

Regras:
- Todo `$` abre ou fecha fórmula, exceto `\$`. Logo, a quantidade de `$` não escapados em cada
  célula deve ser **par**.
- Use somente comandos LaTeX padrão do MathJax (`\frac`, `\sqrt`, `\cdot`, `\times`, `\leq`,
  `\geq`, `\neq`, `\alpha`…`\omega`, `\vec`, `\overline`, `\sin`, `\log`, `\begin{cases}`,
  `\begin{matrix}` etc.). Não use pacotes (`\ce`, `\SI`, `\usepackage`).
- Números soltos no texto (“em 2023”, “3 alunos”) **não** precisam de `$`.

### 3.3 Tabelas

Tabelas vão em HTML simples, numa linha só:

```
<table><tr><th>x</th><th>f(x)</th></tr><tr><td>1</td><td>$3$</td></tr></table>
```

Permitidos apenas: `table`, `tr`, `th`, `td`. LaTeX pode ser usado dentro das células.

### 3.4 Imagens

Imagens **não** vão na planilha. No lugar onde a imagem aparece, escreva um marcador:

```
[[IMG:p<pagina>:<n>|<descrição curta>]]
```

- `p<pagina>` — página do PDF onde a imagem está.
- `<n>` — ordem da imagem **naquela página**, contando de cima para baixo e da esquerda para a
  direita, começando em 1. (Conta todas as figuras da página, não só as desta questão.)
- `<descrição curta>` — o que a imagem mostra; serve de texto alternativo e ajuda o revisor.

Exemplo: `Observe o gráfico.<br>[[IMG:p4:2|gráfico da parábola com vértice em (1, -4)]]<br>O valor mínimo é`

O aplicativo de importação recorta a imagem do PDF usando página + ordem. Imagens podem
aparecer no enunciado, nas alternativas ou na resolução.

**Não** transforme em imagem algo que é texto, fórmula ou tabela — transcreva.

## 4. O que NÃO fazer

- Não escrever a letra da alternativa dentro dela (`a) 12` → errado; `12` → certo).
- Não repetir o número da questão no enunciado (`12. Calcule…` → errado).
- Não incluir cabeçalho/rodapé da página, logotipos, número de página, marca d’água.
- Não usar Enter/quebra real dentro da célula — use `<br>`.
- Não usar Unicode matemático no lugar de LaTeX (`x²`, `√2`, `≤`) — use `$x^2$`, `$\sqrt{2}$`, `$\leq$`.
- Não inventar gabarito ou resolução. Se o PDF não mostra o gabarito, deixe vazio e marque `revisar = SIM`.

## 5. Exemplo completo de uma linha

| coluna | valor |
|---|---|
| codigo_lista | `MAT-EM2-L07` |
| numero | `3` |
| pagina | `1` |
| tipo | `objetiva` |
| disciplina | `Matemática` |
| topico | `Funções` |
| assunto | `Função quadrática` |
| dificuldade | `media` |
| ano | `2022` |
| fonte | `UFPR` |
| enunciado | `Uma loja vende cada camiseta por R\$ 40,00. O lucro, em reais, é dado por $L(x) = -x^2 + 60x - 500$, em que $x$ é a quantidade vendida.<br><br>**Qual** a quantidade que maximiza o lucro?` |
| alt_a | `$20$` |
| alt_b | `$25$` |
| alt_c | `$30$` |
| alt_d | `$35$` |
| alt_e | `$40$` |
| gabarito | `C` |
| resolucao | `O máximo ocorre no vértice: $$x_v = -\frac{b}{2a} = -\frac{60}{2\cdot(-1)} = 30$$` |
