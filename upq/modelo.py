"""Formato de dados das questões ao longo do fluxo.

A IA devolve `QuestaoIA` (só o que exige leitura e julgamento). O código completa
o resto (título, etapa, página, figuras) e grava `Questao` em transcricao.json,
que é o que a revisão mostra e o que vai para o Supabase.

Texto rico (enunciado e alternativas) é Markdown com LaTeX:
  - fórmulas: $...$ no meio do texto, $$...$$ destacadas;
  - **negrito**, *itálico*; parágrafos separados por linha em branco;
  - tabelas em Markdown (| a | b |);
  - figuras: ![descrição](figura:Q11_fig1), trocado pela URL pública no envio.
"""

from typing import Literal

from pydantic import BaseModel, Field

Letra = Literal["A", "B", "C", "D", "E"]


class Alternativa(BaseModel):
    letra: Letra
    texto: str


class QuestaoIA(BaseModel):
    numero: int
    instituicao: str | None = Field(description="Banca/vestibular como no cabeçalho, ex.: 'UFMG'; null se não houver")
    ano: int | None = Field(description="Ano do cabeçalho da questão; null se não houver")
    adaptada: bool = Field(description="true se o cabeçalho traz '(ADAPTADO)'")
    disciplina: str
    topico: str
    assuntos: list[str] = Field(description="1 ou 2 assuntos do tópico, grafia exata da base")
    dificuldade: int = Field(ge=1, le=5)
    enunciado: str
    alternativas: list[Alternativa]
    gabarito: Letra
    revisar: bool
    observacoes: str | None


class Figura(BaseModel):
    nome: str               # Q11_fig1
    arquivo: str            # figuras/Q11_fig1.png (relativo à pasta da lista)
    url: str | None = None  # preenchido no envio ao Supabase


class Questao(BaseModel):
    numero: int
    titulo: str
    instituicao: str | None
    ano: int | None
    disciplina: str
    topico: str
    assuntos: list[str] = []
    etapa: str | None
    dificuldade: int = Field(ge=1, le=5)
    enunciado: str
    alternativas: dict[str, str]
    gabarito: Letra
    figuras: list[Figura] = []
    pagina: int
    imagem: str             # recorte da questão, para a revisão
    revisar: bool = False
    observacoes: str | None = None


class Lista(BaseModel):
    arquivo: str
    hash_pdf: str
    tipo: Literal["lista", "simulado"]
    titulo: str              # nome da capa, ex.: "Movimento Circular Uniforme"
    nome: str                # como aparece na plataforma: "Lista de Movimento Circular Uniforme"
    descricao: str           # "Lista completa de Movimento Circular Uniforme"
    disciplina: str | None
    topico: str | None
    tags: list[str] = []     # assuntos cobertos pela lista
    questoes: list[Questao]


def schema_json(modelo: type[BaseModel]) -> dict:
    """JSON Schema no formato aceito por output_config (sem $defs soltos,
    additionalProperties false e todos os campos obrigatórios)."""
    schema = modelo.model_json_schema()
    defs = schema.pop("$defs", {})

    def resolver(no):
        if isinstance(no, dict):
            if "$ref" in no:
                return resolver(defs[no["$ref"].split("/")[-1]])
            no = {k: resolver(v) for k, v in no.items() if k not in ("title", "default")}
            if no.get("type") == "object" and "properties" in no:
                no["required"] = list(no["properties"])
                no["additionalProperties"] = False
            if no.get("type") == "integer":
                no.pop("minimum", None)
                no.pop("maximum", None)
            return no
        if isinstance(no, list):
            return [resolver(v) for v in no]
        return no

    return resolver(schema)


DIFICULDADES = {1: "Muito Fácil", 2: "Fácil", 3: "Média", 4: "Difícil", 5: "Muito Difícil"}


def titulo_padrao(tipo: str, titulo_lista: str, numero: int, instituicao: str | None,
                  ano: int | None, simulado_num: int | None = None, dia: int | None = None) -> str:
    """Título no padrão do Prompt Mestre."""
    n = f"{numero:02d}"
    if tipo == "simulado":
        return f"Questão {n} - {simulado_num}º Simulado Autoral 2026 - {dia}º DIA"
    origem = " ".join(str(x) for x in (instituicao, ano) if x)
    base = f"Lista de Exercícios - {titulo_lista} - Questão {n}"
    return f"{base} - {origem}" if origem else base
