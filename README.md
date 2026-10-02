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

## Segmentação do PDF (sem IA, segundos por lista)

```
pip install pymupdf
python ferramentas/segmentar_pdf.py Movimento_Circular_Uniforme.pdf --saida saida/MCU
```

Gera um recorte PNG de cada questão, cada figura em alta resolução, as páginas sem questões
(capa, sumário, gabarito) e um `manifesto.json` com número, página, coluna, etapa (Fixação,
Treinamento…) e figuras de cada questão. Usa só a geometria da página, porque a camada de
texto dessas listas (fontes Type3) vem corrompida: π vira "À", expoentes somem, colunas se
misturam.

## Arquivos

- `docs/ESPECIFICACAO_PLANILHA.md` — o contrato da planilha: colunas e regras de marcação
  (negrito, LaTeX, tabelas, marcadores de imagem `[[IMG:p4:2|...]]`).
- `prompts/gerar_planilha.md` — prompt para a IA gerar a planilha a partir do PDF.
- `ferramentas/segmentar_pdf.py` — recorta questões e figuras do PDF.
- `ferramentas/validar_planilha.py` — validador + preview HTML com MathJax.
- `exemplos/MAT-EM2-L07.csv` — exemplo com 2 questões corretas e 2 com erros propositais.
