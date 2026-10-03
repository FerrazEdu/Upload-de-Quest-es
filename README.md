# Upload de Questões

Transforma listas de exercícios em PDF em questões no banco (Supabase), com **LaTeX,
negrito/itálico, tabelas e figuras em alta resolução**. Só transcreve e classifica: não gera
resolução.

```
PDF ──segmentar──▶ recortes + figuras + manifesto ──transcrever (IA)──▶ ia/QNN.json
      (segundos)                                     (paralelo)
    ──revisar──▶ transcricao.json + revisao.html ──enviar──▶ Supabase (Storage + importar_lista)
                 (validação automática + olho humano)
```

## Por que este desenho

- **A camada de texto do PDF não serve como fonte final.** O texto é selecionável, mas as
  fontes Type3 trocam símbolos (π vira "À", ≈ vira "H"), achatam expoentes (10⁸ vira "108")
  e partem palavras. Por isso a IA lê a **imagem** de cada questão; o texto do PDF entra
  como apoio e como conferência automática de números e palavras.
- **A geometria da página é confiável.** As barras "Questão NN", o fio entre colunas e o
  rodapé delimitam cada questão sem IA; as figuras saem em 300 dpi, com os rótulos
  desenhados por cima.
- **Uma chamada por questão, em paralelo**, em vez de um documento inteiro por vez: mais
  rápido, mais preciso e, se algo falhar, só aquela questão é refeita.
- **O que é regra fica no código, não na IA:** título no padrão, etapa, página, gabarito
  oficial, par disciplina/tópico (o banco recusa par fora da base).

## Instalação

```
pip install -r requirements.txt
```

## Importador no claude.ai (sem chave de API, sem servidor)

`python -m upq.artefato` monta `dist/importador-questoes.html`, publicado como artefato do
claude.ai (capacidades `db`, `assets`, `sample`, `downloads`, `user`). Tudo roda no navegador:

- **recorte** do PDF com pdf.js (`upq/web/recorte.js`, mesma geometria de `upq/segmentar.py`);
- **transcrição** pelo Claude do próprio claude.ai (capacidade `sample`, 4 questões por chamada,
  conta no plano de quem usa). Se bater limite, o card mostra **Continuar**;
- **validação** (porta de `upq/validar.py`), **banco** de questões, **listas virtuais**, edição,
  "Marcar como revisada" e **Baixar planilha (.xlsx)** / JSON.

Quando a visualização não envia imagens ao Claude, tabelas coladas como imagem são lidas por OCR
(Tesseract) no navegador, célula a célula. Os arquivos do OCR vão publicados junto com a página, em
`ocr/`: `scripts/preparar_ocr.sh` monta `dist/ocr/`. Fórmulas que o PDF traz como imagem ou desenho (sem texto: frações, raízes, alternativas inteiras)
são achadas no recorte (tinta sem texto) e entram no texto como `⟦FÓRMULA NOME⟧`, com o recorte guardado;
no modo só texto, o próprio navegador as lê em LaTeX (pix2tex/RapidLaTeXOCR em onnxruntime-web, lido
em várias escalas, por maioria). Os arquivos vão em `formula/`: `python scripts/preparar_formulas.py`
monta `dist/formula/`. A validação barra fórmula não lida, fórmula ausente da transcrição e aviso no
lugar do texto ("expressão não legível"). Fórmula colada como imagem grande (alternativa inteira em
imagem) também vai ao leitor, com o recorte da própria imagem: vira LaTeX só com leitura unânime em
duas escalas e coerente (sem `\frac{}{}`, `\left` sem `\right`); senão continua a figura que é.
Sistema com chave vira uma fórmula só, `\begin{cases} … \end{cases}`: chave desenhada com as equações em
texto é montada no recorte (a letra da alternativa fica fora); sistema inteiro sem texto (ex.: "Bruno {…")
é partido em rótulo, chave e linhas, e cada linha (longa: em pedaços) é lida pelo leitor; sistemas
empilhados que se tocam são separados (um por chave) e o rótulo usa a grafia do texto da questão ("André").

Cada questão do banco tem o botão **Reprocessar**: instrução opcional do revisor ("o que corrigir") e,
opcionalmente, o PDF da lista — com ele a questão é recortada de novo com os critérios atuais antes da
nova transcrição; a versão nova substitui a antiga.

Colunas: cada página é lida em uma ou duas colunas pela barra "Questão NN". O texto da barra decide
primeiro ("BANCA ANO" na ponta direita, depois do meio = barra na largura toda); sem isso, a cor da
barra. Se com o modelo escolhido algum texto ou imagem da página ficaria fora de todas as questões, o
recorte refaz a página com o outro modelo e fica com o que cobre tudo. A validação recusa barra partida
(questão sem banca e com "BANCA ANO" solto no texto).
Negrito: lido pela fonte e, nas fontes Type3
(sem nome), pela espessura do traço de cada palavra na página renderizada.

Banco do artefato: `importacoes/<hash16>`, `partes/<hash16>-<k>` (até 20 questões cada) e
`listas/<id>`; imagens e figuras ficam em `assets`. A aba precisa ficar aberta enquanto processa.

## App web

```
python -m upq.web            # http://localhost:8000
```

- **Enviar lista**: arraste um ou vários PDFs; cada um mostra as etapas
  (recorte → transcrição → validação → no banco). As questões vão para o **banco geral** e o
  PDF gera a sua lista ("Lista de <título>").
- **Banco de questões**: todas as questões, com filtros por texto, disciplina, tópico, assunto,
  instituição, ano e dificuldade. Marque questões e crie uma lista nova ou adicione a uma existente.
- **Listas**: listas virtuais (apontam para questões do banco). Ao abrir uma, o gerenciamento
  mostra "Questões selecionadas" (reordenar, ver, tirar) e "Buscar questões" (filtros e adicionar).
  **Enviar ao banco** manda ao Supabase as importações usadas e a lista
  (precisa de `SUPABASE_URL` e `SUPABASE_SECRET_KEY`).

As listas ficam em `saida/_listas.json`. `python -m upq.web --demo demo.html` gera um HTML
único, sem servidor, com o banco e as listas de `saida/`.

## Uso pela linha de comando

```
# 1. Segmentar + transcrever + validar + gerar revisão (uma lista ou uma pasta inteira)
export ANTHROPIC_API_KEY=...            # sem chave: veja "Sem chave de API" abaixo
python -m upq processar exemplos/Movimento_Circular_Uniforme.pdf
python -m upq processar pasta_com_900_pdfs/

# 2. Revisar: abrir saida/<lista>/revisao.html no navegador
#    (original à esquerda, renderizado à direita, erros e avisos no topo de cada questão)
python -m upq revisar saida/<lista>      # refaz validação e revisão depois de correções

# 3. Enviar ao Supabase
export SUPABASE_URL=https://wrexjikxwjqwxcsmuzis.supabase.co
export SUPABASE_SECRET_KEY=sb_secret_...  # Dashboard → Project Settings → API Keys
python -m upq enviar saida/<lista>        # --forcar para enviar com avisos já revisados

# Opcional: .xlsx de 15 colunas (formato do Prompt Mestre)
python -m upq exportar saida/<lista>
```

Depois de enviar, a lista fica como `rascunho`. Para publicar (aparecer no
`visualizador.html` e para os alunos):

```sql
update public.listas set status = 'publicada' where titulo = 'Movimento Circular Uniforme';
```

### Sem chave de API

O Claude Code faz o papel do motor de transcrição, seguindo as mesmas regras
(ver `CLAUDE.md`): peça "transcreva a lista saida/<lista>" e depois rode
`python -m upq revisar saida/<lista>`. Serve para testar e para listas avulsas; para
o volume de 800–900 listas use a API.

## Banco (Supabase)

Migrações em `supabase/migrations/`, já aplicadas no projeto `wrexjikxwjqwxcsmuzis`:

| Tabela | Conteúdo |
|---|---|
| `topicos` | base oficial de tópicos (166 pares disciplina/tópico, de `dados/base_topicos.txt`) |
| `importacoes` | um PDF importado (`hash_pdf` único: reenviar atualiza as mesmas questões) |
| `questoes` | banco geral: enunciado, `alternativas` (JSON A–E), gabarito, assuntos, figuras, dificuldade, etapa, `publicada` |
| `listas` | listas virtuais: nome, descrição, disciplina, tópico, tags, status |
| `lista_questoes` | quais questões estão em cada lista, e em que ordem |

- Texto rico é **Markdown + LaTeX** (`$...$`, `$$...$$`); figuras são `![descrição](URL pública)`.
- `importar_lista(p jsonb)` grava as questões de um PDF no banco geral e a lista padrão dele,
  numa transação, sem nunca apagar questões. `salvar_lista(p jsonb)` cria ou atualiza uma lista
  virtual a partir de `{hash_pdf, numero}` das questões.
- RLS: leitura pública só de listas `publicada`; escrita só com a chave secreta.
- Figuras no bucket público `figuras`.

## Arquivos

| Caminho | O quê |
|---|---|
| `upq/segmentar.py` | recorta questões e figuras, lê etapas do sumário e o gabarito |
| `upq/prompt.py` | regras de transcrição, formatação, classificação e dificuldade (adaptadas do Prompt Mestre) |
| `upq/transcrever.py` | motor da API do Claude (paralelo, cache do prompt, saída em JSON Schema) |
| `upq/montar.py` | junta tudo em `transcricao.json` com título, etapa e gabarito oficial |
| `upq/validar.py` | estrutura, base de tópicos, LaTeX, figuras e conferência com o texto do PDF |
| `upq/revisao.py` | gera `revisao.html` |
| `upq/enviar.py` / `upq/exportar.py` | Supabase / .xlsx |
| `upq/web.py` + `upq/web/app.html` | app web local (envio de PDFs e listas cadastradas) |
| `visualizador.html` | o banco publicado, como o aluno vê |
| `docs/prompt_mestre_original.md` | prompt usado antes, para referência |
