# Upload de Questões — instruções para o Claude Code

Fluxo: PDF da lista → `python -m upq.segmentar` → transcrição (API ou manual) →
`python -m upq revisar` → revisão humana em `revisao.html` → `python -m upq enviar`.

## Modo manual (sem ANTHROPIC_API_KEY): o Claude Code é o motor de transcrição

Quando pedirem "transcreva a lista X", faça exatamente o que `upq/transcrever.py` faria:

1. Rode `python -m upq.segmentar <pdf> --saida saida/<nome>` se a pasta ainda não existir.
2. Leia `saida/<nome>/manifesto.json`.
3. Crie `saida/<nome>/ia/lista.json`:
   ```json
   {"gabarito": {"01": "C", "02": "C"},
    "classificacao": {"disciplina": "...", "topico": "...", "assunto": "...",
                      "descartados": [], "confiante": true, "justificativa": "..."}}
   ```
   - gabarito: use `gabarito_pdf` do manifesto; se vier vazio, leia a imagem `pagina_gabarito`.
   - classificação (só em `tipo: lista`): um par da base em `dados/base_topicos.txt`, grafia exata,
     igual para a lista inteira. Em simulado, `"classificacao": null`.
4. Para CADA questão do manifesto, crie `saida/<nome>/ia/QNN.json` no formato `QuestaoIA`
   (`upq/modelo.py`), seguindo À RISCA as regras de `upq/prompt.py` (`SISTEMA` e
   `mensagem_questao`). Entradas da questão: a imagem `imagem` (fonte da verdade), as
   figuras em `figuras` (use os `nome` em `![descrição](figura:NOME)`), o `texto_pdf`
   (apoio, com símbolos trocados) e a letra do gabarito oficial.
   - `alternativas` é uma lista `[{"letra": "A", "texto": "..."}]`.
   - `assuntos`: 1 ou 2 assuntos do tópico, com a grafia de `dados/base_topicos.txt`.
   - Não gere resolução: o trabalho é só transcrição e classificação.
5. Rode `python -m upq revisar saida/<nome>`, corrija os ERROS apontados e revise os avisos.

Não invente gabarito, banca ou ano. Não altere `dados/base_topicos.txt` sem pedido.

## Convenções do código

- Python 3.10+, mensagens e nomes em português, sem dependências além de `requirements.txt`.
- Banco: Supabase, migrações em `supabase/migrations/` (aplicadas na ordem do número).
  A função `importar_lista` nunca apaga questões; mudanças de esquema entram como nova migração.

## Importador no claude.ai

`upq/web/importador.html` + `upq/web/recorte.js` + `upq/artefato.py` formam o artefato
(`python -m upq.artefato` → `dist/importador-questoes.html`). Ao mudar `upq/prompt.py`,
`upq/validar.py` ou `upq/segmentar.py`, mantenha a versão JS equivalente e remonte o artefato.
