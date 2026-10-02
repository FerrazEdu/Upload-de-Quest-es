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

## App web (envio + listas cadastradas)

```
python -m upq.web            # http://localhost:8000
```

- **Enviar lista**: arraste um ou vários PDFs; cada um mostra as etapas
  (recorte → transcrição → validação → pronta para envio).
- **Listas**: a tabela das listas (nome, quantidade, descrição, disciplina, tópico, tags,
  situação). Clique numa lista para ver as questões; clique numa questão para ver os detalhes
  como na plataforma (título interno, instituição, disciplina, tópico, enunciado renderizado,
  assuntos, dificuldade, ano, alternativas com "Correta?") e o recorte original do PDF.
- **Enviar ao banco** manda a lista ao Supabase (precisa de `SUPABASE_URL` e `SUPABASE_SECRET_KEY`).

`python -m upq.web --demo demo.html` gera um HTML único, sem servidor, com as listas de `saida/`.

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
| `listas` | uma linha por PDF: nome, descrição, tags (`hash_pdf` único: reenviar atualiza) |
| `questoes` | enunciado, `alternativas` (JSON A–E), gabarito, assuntos, figuras, dificuldade, etapa |

- Texto rico é **Markdown + LaTeX** (`$...$`, `$$...$$`); figuras são `![descrição](URL pública)`.
- `importar_lista(p jsonb)` grava a lista inteira numa transação e nunca apaga questões.
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
