# Upload de Questões

Ferramentas para transformar listas de exercícios em PDF em questões cadastradas no banco de
questões, **preservando formatação, LaTeX e imagens**.

## Fluxo

```
PDF da lista ──(IA + prompts/gerar_planilha.md)──▶ planilha ──(validar_planilha.py)──▶ importação
```

1. Envie o PDF para a IA com o prompt de `prompts/gerar_planilha.md`.
2. Salve a resposta como `<codigo_lista>.csv` (ou cole no Excel e salve `.xlsx`).
3. Valide e revise visualmente:
   ```
   pip install openpyxl
   python ferramentas/validar_planilha.py MAT-EM2-L07.csv --preview
   ```
   Abra o `MAT-EM2-L07.preview.html` gerado no navegador.
4. Corrija os erros apontados e importe.

## Arquivos

- `docs/ESPECIFICACAO_PLANILHA.md` — o contrato da planilha: colunas e regras de marcação
  (negrito, LaTeX, tabelas, marcadores de imagem `[[IMG:p4:2|...]]`).
- `prompts/gerar_planilha.md` — prompt para a IA gerar a planilha a partir do PDF.
- `ferramentas/validar_planilha.py` — validador + preview HTML com MathJax.
- `exemplos/MAT-EM2-L07.csv` — exemplo com 2 questões corretas e 2 com erros propositais.
