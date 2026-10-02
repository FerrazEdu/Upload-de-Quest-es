# Prompt Mestre — Geração da Planilha de Importação (PDF → xlsx)

**Como usar:** abra um modelo de IA de ponta com suporte a PDF/visão, anexe o
PDF da lista ou do simulado e cole o prompt abaixo, inteiro e sem alterações.
Em simulados, anexe o PDF com o nome original do arquivo: é dele que saem o
número do simulado e o dia de prova usados no título. A coluna
"Explicação do Professor" fica vazia de propósito — a resolução é gerada pelo
app, com modelo e formato padronizados. Este prompt é de transcrição e de
classificação de dificuldade: o modelo lê as questões, mas não as resolve.
A base de tópicos da plataforma está no anexo, no fim do prompt; quando a
base for atualizada, substitua só o anexo.

---

Transforme o PDF anexado em uma planilha de importação de questões, seguindo
rigorosamente as regras abaixo. O resultado final deve ser um arquivo .xlsx com
uma única aba chamada Questões, uma linha por questão e exatamente estas 15
colunas, nesta ordem:

Nº | Título | Instituição | Ano | Disciplina | Tópico | Dificuldade | Enunciado |
Alternativa A | Alternativa B | Alternativa C | Alternativa D | Alternativa E |
Gabarito | Explicação do Professor

**ORGANIZAÇÃO E CLASSIFICAÇÃO**

- Inclua todas as questões de múltipla escolha do PDF, na ordem original,
  inclusive as autorais e os desafios.
- QUESTÃO ABERTA/DISSERTATIVA NÃO ENTRA NA PLANILHA. Não a inclua com gabarito
  vazio: remova-a e liste os números removidos na mensagem de entrega. O app
  recusa o arquivo inteiro se houver linha sem gabarito.
- Preserve a numeração original, com pelo menos dois dígitos: 01, 02, 03.
  Não reinicie a numeração por iniciativa própria.
- TÍTULO — o padrão depende do tipo de material:
  · Lista de exercícios: Lista de Exercícios - [Título da lista] - Questão
    [Nº] - [Banca] [Ano]
    Exemplo: Lista de Exercícios - Progressão Geométrica - Questão 05 - UFPR 2020
  · Simulado: Questão [Nº] - [N]º Simulado Autoral 2026 - [D]º DIA
    Exemplo: Questão 01 - 13º Simulado Autoral 2026 - 1º DIA
- LISTA DE EXERCÍCIOS:
  · [Título da lista] é o nome da lista como aparece na capa (ex.:
    Progressão Geométrica), sem repetir "Lista de Exercícios" e sem a etapa
    pedagógica (Fixação, Treinamento, Aprofundamento, Desafios).
  · [Banca] e [Ano] são exatamente os valores das colunas Instituição e Ano
    da mesma linha, separados por um espaço. Não use outra grafia no título.
  · Questão sem banca e sem ano (autoral, por exemplo): o título termina em
    Questão [Nº], sem o último " - ". Se só um dos dois existir, use apenas
    ele. Nunca invente banca ou ano para completar o título.
- SIMULADO: trate o PDF como simulado quando o nome do arquivo ou a capa
  contiver "Simulado". Nesse caso:
  · Extraia o número do simulado e o dia de prova do nome do arquivo do PDF.
    Se o nome do arquivo não estiver visível para você, use a capa. Se
    nenhum dos dois permitir determinar, não gere a planilha: informe o que
    faltou.
  · O ano do título é SEMPRE 2026. Regra fixa, não é inferência: vale mesmo
    que o nome do arquivo ou o PDF mostre outro ano ou nenhum ano.
  · Normalize a grafia: 13o, 13°, 13 → 13º · 1 DIA, 1_DIA, Dia 1, primeiro
    dia → 1º DIA. Use o indicador ordinal º, nunca o símbolo de grau °.
    DIA sempre em maiúsculas.
  · Número do simulado sem zero à esquerda (5º, nunca 05º). Número da
    questão com pelo menos dois dígitos, como no restante da planilha.
  · Número do simulado, dia de prova e ano são idênticos em todas as
    linhas; só o número da questão muda.
- Separe instituição e ano conforme o cabeçalho de cada questão. Não confunda o
  ano da questão com datas citadas no enunciado ou nas referências.

**DISCIPLINA E TÓPICO (SOMENTE DA BASE DA PLATAFORMA)**

- Disciplina e Tópico só podem receber valores que existam no ANEXO — BASE
  DE TÓPICOS DA PLATAFORMA, no fim deste prompt. Nunca crie, adapte,
  traduza, abrevie nem corrija um nome: copie exatamente como está na base,
  com a mesma grafia, acentuação e maiúsculas, mesmo que pareça ter erro.
- O par Disciplina + Tópico precisa existir junto na base. O mesmo nome de
  tópico pode aparecer em mais de uma disciplina (ex.: Política, em
  Filosofia e em Sociologia; Interpretação de Texto, em Linguagens e
  Códigos, Espanhol e Inglês): use o da disciplina correta.
- Os assuntos da base servem só para localizar o tópico. A coluna Tópico
  recebe o nome do tópico, nunca o do assunto. Exemplo: a lista "Cadeia e
  Teia Alimentar" corresponde ao assunto Cadeia alimentar, que pertence ao
  tópico Ecologia → Disciplina: Biologia · Tópico: Ecologia.
- Em lista, Disciplina e Tópico vêm do assunto da lista e são iguais em
  todas as linhas. O Título continua usando o nome da capa (ex.: Lista de
  Exercícios - Cadeia e Teia Alimentar - ...), mesmo quando o tópico da
  base tem outro nome.
- "Fixação", "Treinamento", "Aprofundamento" e "Desafios" são etapas
  pedagógicas, nunca tópicos.
- Em simulado, classifique cada questão individualmente, pelo conteúdo que
  ela cobra: Disciplina e Tópico podem mudar de uma linha para outra.
- Use a disciplina Intensivo Revisional somente quando o PDF for material do
  Intensivo Revisional (capa ou nome do arquivo). Nos demais casos, use a
  disciplina do conteúdo.
- Se mais de um tópico couber, escolha o que tem o assunto mais específico
  para o conteúdo e informe na entrega o tópico descartado.
- Se nenhum tópico da base couber com segurança, não force o mais próximo
  nem invente um: não gere a planilha e informe o assunto (da lista ou das
  questões) e os tópicos candidatos, para decisão humana.

**DIFICULDADE (OBRIGATÓRIA EM TODAS AS LINHAS)**

- Preencha com um número inteiro de 1 a 5, na escala do app:
  1 = Muito Fácil · 2 = Fácil · 3 = Média · 4 = Difícil · 5 = Muito Difícil
- NUNCA deixe a célula vazia. Leia cada questão inteira (enunciado, textos de
  apoio, tabelas, figuras e alternativas) antes de classificar. Não resolva
  a questão e não registre resolução: avalie apenas o que ela exige do aluno.
- Referência: aluno de pré-vestibular/ENEM que já estudou o tópico da lista.
- Na leitura, pese: quantos conceitos ou etapas a questão encadeia; a carga
  de interpretação (texto-base longo ou denso, comando indireto); o uso de
  dados de gráfico, tabela ou figura; o volume e a complexidade de cálculo;
  a proximidade entre as alternativas; e a exigência de conteúdo além do
  tópico da lista.
- Guia de níveis: reconhecimento ou aplicação direta de um conceito ou
  fórmula → 2 · aplicação com mais de uma etapa ou interpretação de dados
  → 3 · integração de conceitos, várias etapas ou interpretação exigente → 4.
- 1 e 5 são raros. Use 1 só para reconhecimento imediato, sem nenhuma etapa;
  use 5 só quando a questão reúne vários dos fatores acima no grau mais alto.
  Na dúvida entre um extremo e o nível vizinho, fique no vizinho.
- Em listas, o bloco é o ponto de partida, e a leitura da questão decide o
  nível dentro da faixa esperada:
  Fixação → 1 a 2 (predomina 2) · Treinamento → 2 a 3 ·
  Aprofundamento → 3 a 4 · Desafios → 4 a 5 (predomina 4).
  Sair da faixa só é permitido quando a questão claramente não corresponde
  ao bloco, e deve ser informado na entrega.
- A banca não define a dificuldade por si só: classifique a questão, não o
  vestibular.
- EM SIMULADO, a dificuldade já vem indicada no PDF, junto a cada questão.
  Transcreva essa indicação em vez de classificar pela leitura:
  · Converta para a escala do app: Muito Fácil → 1 · Fácil → 2 · Média → 3 ·
    Difícil → 4 · Muito Difícil → 5. Se o PDF já trouxer o número de 1 a 5,
    use-o direto.
  · A indicação do PDF prevalece sobre a sua leitura, mesmo que você
    discorde dela. Não a ajuste nem a recalibre.
  · A indicação é metadado: não a transcreva no Enunciado nem em nenhuma
    outra coluna além de Dificuldade.
  · Só se uma questão específica vier sem indicação, classifique-a pela
    leitura, com os critérios acima, e liste o número dela na entrega.
  · Se a indicação usar uma escala ou um símbolo que você não consiga
    converter com segurança para 1–5, não adivinhe: não gere a planilha e
    descreva na entrega como a indicação aparece no PDF.

**TRANSCRIÇÃO DO CONTEÚDO**

- O enunciado deve conter a contextualização completa, os textos de apoio, as
  afirmativas, as referências e o comando da questão. Texto-base compartilhado
  por várias questões é repetido integralmente em cada uma.
- Separe cada alternativa na coluna correspondente, sem o marcador A/B/C/D/E.
  Questão de A a D deixa a coluna E vazia — não invente quinta alternativa.
- Reconstrua as continuações entre colunas e páginas do PDF. Nenhum trecho de
  uma alternativa pode vazar para a célula de outra.
- NOTAÇÃO CIENTÍFICA E MATEMÁTICA SEMPRE EM CARACTERES UNICODE:
  m³ (nunca m3) · cm² (nunca cm2) · 10²³ (nunca 10 23 ou 10^23) ·
  H₂O (nunca H2O) · x₁, x₂ · √2 · π · ≤ ≥ ≠ · × · − (sinal de menos real).
  Se algum símbolo não puder ser representado, avise na entrega.
- PROIBIDO LaTeX e qualquer marcação: nada de $...$, \frac, \times, HTML,
  markdown ou negrito/itálico simulado. Texto simples com unicode, com quebras
  de linha reais dentro das células (nunca o literal \n).
- Transcreva tabelas com cabeçalhos, valores e unidades em texto organizado,
  preservando a associação entre os dados.
- As imagens permanecem no PDF (o app as extrai sozinho). Preserve as
  referências e transcreva legendas legíveis. Quando uma figura indispensável
  não puder ser representada em texto, registre: Consultar figura no PDF,
  página X. Não invente descrições para mapas, charges, gráficos ou desenhos.
- Exclua cabeçalhos recorrentes, rodapés, números de página e marcas-d'água.
- Preserve palavras, acentos, pontuação, números, unidades e símbolos. Não
  resuma, não parafraseie, não atualize nem corrija o conteúdo da fonte — o
  reconhecimento de questão já cadastrada compara o texto literal.

**GABARITO E EXPLICAÇÕES**

- Transcreva o gabarito do PDF: uma única letra maiúscula (A a E).
- Associe gabarito e questão pelo número E pelo tópico, especialmente com
  numerações repetidas. Não resolva a questão para deduzir gabarito ausente.
- Deixe a coluna Explicação do Professor vazia em todas as linhas — a
  resolução é gerada pelo app.
- Não invente instituição, ano ou qualquer informação ausente da fonte.

**CONFERÊNCIA OBRIGATÓRIA ANTES DE ENTREGAR**

- Total de questões do PDF = total de linhas (menos as abertas removidas).
- Sequência, ausência de duplicações e correspondência dos títulos.
- Dificuldade preenchida em 100% das linhas, só com inteiros de 1 a 5.
  Em lista: se muitas questões caíram em 1 ou 5, revise a calibragem, e a
  média de cada bloco não pode ser menor que a do bloco anterior. Em
  simulado: cada valor confere com a indicação do PDF.
- Em lista: todos os títulos no padrão Lista de Exercícios - [Título da
  lista] - Questão [Nº] - [Banca] [Ano], com banca e ano idênticos às
  colunas Instituição e Ano da mesma linha.
- Em simulado: todos os títulos no padrão Questão [Nº] - [N]º Simulado
  Autoral 2026 - [D]º DIA, com o mesmo número de simulado, o mesmo dia de
  prova e o ano 2026 em todas as linhas.
- Todo par Disciplina + Tópico existe no anexo, com grafia idêntica. Nenhum
  Tópico é nome de assunto, etapa pedagógica ou título da capa adaptado.
- Todos os gabaritos conferidos contra os quadros do PDF.
- NENHUMA alternativa A–D com menos de 2 caracteres ou terminando no meio de
  palavra — célula assim indica corte de transcrição: reconstrua da fonte.
- Nenhuma célula com m3/cm2/10 23/H2O onde deveria haver m³/cm²/10²³/H₂O.
- Nenhum $, \frac ou comando LaTeX em nenhuma célula.
- Revise visualmente tabelas, fórmulas e trechos ambíguos. Não trate texto
  extraído automaticamente como necessariamente correto.

**ENTREGA**

Somente o .xlsx final, sem abas auxiliares nem colunas extras. Na mensagem de
entrega: total de questões, números das abertas removidas, pendências de
gabarito ou símbolo, e dependências de figura. Informe também a Disciplina e o
Tópico atribuídos (em lista, com o assunto da base que justificou a
escolha), os casos em que mais de um tópico cabia e a distribuição
de dificuldade (quantas questões em cada nível de 1 a 5; em lista, por bloco)
e os números das questões classificadas fora da faixa do bloco. Em lista,
informe também os números das questões cujo título ficou sem banca ou sem ano.
Em simulado, informe também o número do simulado e o dia de prova
identificados e de onde vieram (nome do arquivo ou capa), além das questões
que vieram sem indicação de dificuldade no PDF e foram classificadas pela
leitura. Não declare fidelidade integral se houver trecho não verificado.

---

**ANEXO — BASE DE TÓPICOS DA PLATAFORMA**

Formato: Tópico: assuntos que ele abrange. Quando o tópico não lista
assuntos, o único assunto tem o mesmo nome do tópico. Os assuntos servem só
para localizar o tópico; a coluna Tópico recebe apenas o nome do tópico.

DISCIPLINA: História
- Idade Antiga: Egito; Grécia; Primeiras civilizações; Roma
- Idade Média: Cruzadas; Feudalismo; Império Bizantino
- Idade Moderna: Estados Nacionais; Expansão marítima; História da América; Mercantilismo; Reforma e contrarreforma; Renascimento; Revolução industrial
- Idade Contemporânea: Entreguerras; Guerra Fria; Imperialismo; Nazifascismo; Primaveira Árabe; Primeira Guerra Mundial; Revolução Francesa; Segunda Guerra Mundial
- Brasil Colônia: Catequização; Ciclos econõmicos; Escravidão; Independência; Revoltas brasileiras
- Brasil Império: Abolição da escravidão; Guerra do Paraguai; Período Regencial; Primeiro Reinado; Revoltas brasileiras; Segundo Reinado
- Brasil República: Constituição Federal; Direitos Sociais; Ditadura militar; Era Vargas; Governo JK; Proclamação da República; Redemocratização; República Oligárquica; República Velha; Revoltas brasileiras

DISCIPLINA: Geografia
- Geografia Econômica: Blocos econômicos; Comércio; Conceitos geográficos; Desigualdade socioeconômica; DIT; Doutrinas econômicas; Fontes de energia; Globalização; Modais; Modelos de produção; Neoliberalismo; Setores da economia; Sistemas econômicos
- Geografia Urbana e Demografia: Densidade demográfica; Fenômenos urbanos e problemas sociais; Indicadores demográficos; Migrações; Pirâmides etárias; Teorias demográficas; Transição demográfica
- Geografia Agrária: Conflitos no campo; Estrutura fundiária; Modelos de produção agrícola; Reforma agrária; Revolução verde
- Geopolítica: Blocos econômicos; Colonialismo e neocolonialismo; Conflitos geopolíticos; Imperialismo; Ordens mundiais; Sustentabilidade
- Geografia Física: Cartografia; Ciclo das rochas; Eras geológicas; Geologia; Relevos; Tectonismo
- Hidrografia
- Climatologia: Climas do Brasil; El Nino e La Nina; Fatores do clima; Fenômenos climáticos
- Impactos ambientais: Degradação dos solos; Desmatamento; Escassez hídrica; Mudanças climáticas; Poluição

DISCIPLINA: Filosofia
- Fundamentos da Filosofia: A Passagem do Mito ao Logos; Mito e Religião; O Que é Filosofia
- Filosofia Clássica: Aristóteles; Platão; Pré-Socráticos; Sócrates
- Filosofia Moderna: Contratualismo; Idealismo; Iluminismo; Kant; Racionalismo e empirismo
- Filosofia Contemporânea: Educação; Escola de Frankfurt; Guerra Fria; Michel Foucault; Nietzche; Sartre
- Filosofia Religiosa: Santo Agostinho; São Tomás de Aquino
- Filosofia da Ciência
- Ética e Moral
- Política

DISCIPLINA: Sociologia
- Fundamentos da Sociologia: O Que é Sociologia; Sociologia e suas Áreas
- Sociólogos Clássicos: Auguste Comte; Émile Durkheim; Marx e Engels; Max Weber
- Cultura e Identidade
- Instituições Sociais
- Sociologia do Trabalho
- Política
- Movimentos Sociais: Abolição, racismo e antirracismo; Movimento feminista; Movimento LGBT; Movimento operário
- Sociologia Brasileira
- Tecnologia
- Religião
- Indústria Cultural, Consumo, Comunicação e Influência
- Consciência Coletiva

DISCIPLINA: Biologia
- Fundamentos da Biologia: Introdução à Célula; Níveis de Organização Biológica; Noções de Metabolismo e Energia; O que é Vida
- Método Científico
- Bioquímica: Enzimas; Macromoléculas; Vitaminas
- Citologia e Moléculas da Vida: Células; Divisão celular; Membrana Plasmática; Organelas; Transportes de membrana
- Metabolismo Energético I: Fermentação; Respiração celular
- Metabolismo Energético II: Fotossíntese; Quimiossíntese
- Biologia Molecular: Bases nitrogenadas; DNA e RNA; Proteínas
- Evolução e Classificação dos Seres Vivos: Cladogramas; Especiação; Origem da vida; Teorias evolutivas
- Ecologia: Biomas e diversidade; Cadeia alimentar; Ciclos biogeoquímicos; Dinâmica de populações; Ecossistemas; Fluxos de energia e de matéria; Gráficos de relações ecológicas; Impactos antrópicos; Preservação e conservação ambiental; Problemas ambientais; Relações ecológicas; Sucessão ecológica
- Impactos e Problemas Ambientais
- Genética: 1° Lei de Mendel; 2° Lei de Mendel; Biotecnologia; Doenças genéticas; Engenharia genética; Fator Rh e Sistema ABO; Fundamentos da genética; Heredogramas; Interações gênicas
- Histologia: Tecido Muscular
- Fisiologia Humana: Sistema cardiorrespiratório; Sistema digestório; Sistema endócrino; Sistema excretor; Sistema hematopoietico; Sistema imunológico; Sistema nervoso; Sistema reprodutor
- Botânica: Fisiologia vegetal; Fitormônios; Grupos vegetais; Histologia vegetal; Reprodução
- Zoologia: Artrópodes e Equinodermos; Cordados; Primeiros filos
- Doenças: Bacterioses; Protozooses e verminoses; Vírus e viroses
- Microbiologia
- Reprodução e Embriologia

DISCIPLINA: Física
- Energia e suas Transformações: Fontes de energia; Impactos Ambientais e Contexto Energético
- Ferramental Matemático: Conversão de unidades; Potência de 10 e notação científica; Proporção entre grandezas físicas; Triângulo retângulo na Física
- Grandezas Físicas
- Termologia I: Calorimetria; Dilatação; Termometria
- Cinemática I: Fundamentos da cinemática; Movimento uniforme; Movimento uniformemente variado; Queda livre e lançamento vertical
- Ondulatória I: Espectro eletromagnético; Fenômenos ondulatórios; Propriedades das ondas
- Dinâmica I: Força de atrito; Força elástica e lei de Hooke; Forças particulares; Leis de Newton; Polias fixas e móveis
- Vetores
- Eletrostática: Campo e potencial elétrico; Eletrização; Força elétrica
- Eletrodinâmica I: 1º Lei de Ohm; 2º Lei de Ohm; Amperímetro e voltímetro; Circuitos elétricos; Potência elétrica; Tensão e corrente
- Potência e Eficiência
- Cinemática II: Acoplamento no MCU; Cinemática vetorial; Lançamento horizontal; Lançamento oblíquo; Movimento circular
- Termologia II: Gases; Termodinâmica
- Dinâmica II: Dinâmica do MCU; Plano inclinado
- Dinâmica III: Colisões; Energia cinética e mecânica; Energia potencial elástica; Energia potencial gravitacional; Força elástica; Impulso e quantidade de movimento; Movimento Harmônico Simples
- Estática: Equilíbrio de corpos
- Hidrostática: Densidade; Empuxo; Pressão
- Eletrodinâmica II: Associação de pilhas e baterias; Geradores, receptores e capacitores; Ponte de Wheatstone
- Magnetismo e Eletromagnetismo
- Óptica: Espelhos; Fenômenos ópticos; Lentes
- Ondulatória II: Acústica
- Gravitação
- Física Moderna: Física nuclear; Mecânica quântica; Radiação de corpo negro; Relatividade

DISCIPLINA: Química
- Propriedades da Matéria
- Processos de Separação de Misturas
- Atomística: Alotropia; Efeitos luminosos; Leis ponderais; Modelo atômico atual; Modelos atômicos; Propriedades atômicas
- Estequiometria: Cálculos estequiométricos; Variáveis no cálculo estequiométrico
- Tabela Periódica e suas Propriedades: Elementos químicos; Famílias e períodos; Propriedades periódicas
- Química Orgânica: Compostos orgânicos; Funções orgânicas; Isomeria; Reações orgânicas
- Ligações Químicas, Propriedades dos Compostos e Polaridade: Forças intermoleculares; Ligações químicas; Polaridade
- Geometria Molecular: Arranjos geométricos espaciais; Teoria da Repulsão dos Pares de Elétrons
- Radioatividade: Decaimento radioativo; Partículas; Reações nucleares
- Propriedades Coligativas: Crioscopia; Osmoscopia; Tonoscopia
- Eletroquímica: Eletrólise; Oxirredução; Pilhas; Reações
- Química Ambiental
- Química Inorgânica: Ácidos; Bases; Funções inorgânicas; Ionização e dissociação iônica; NOX; Óxidos; Reações inorgânicas; Sais
- Termoquímica: Equações termoquímicas; Lei de Hess
- Soluções: Concentração; Diluição e mistura de soluções; Dispersões
- Equilíbrio Químico
- Cinética Química
- Reações Químicas
- Gases e suas Transformações
- Polímeros

DISCIPLINA: Linguagens e Códigos
- Funções da Linguagem
- Figuras de Linguagem
- Tipologias Textuais
- Gêneros Textuais
- Campanhas Publicitárias, Anúncios e Influência
- Crítica Social, Cultural e Artística
- Variações Linguísticas: Normas linguísticas; Patrimônio linguístico
- Poemas e Poesias
- Expressividade e Lirismo
- Progressão Textual e Temática
- Mecanismos de Coesão e Coerência
- Intertextualidade
- Charges e HQs
- Literatura: Arcadismo; Barroco; Classicismo; Contemporânea; Leituras obrigatórias; Modernismo; Naturalismo; Parnasianismo; Quinhentismo; Realismo; Romantismo; Simbolismo; Trovadorismo
- Artes: Cubismo; Dadaísmo; Expressionismo; Futurismo; Surrealismo
- Movimentos Artísticos
- Recursos Argumentativos
- Estratégias Argumentativas
- Gramática: Colocação Pronominal; Concordância; Fonética e Fonologia; Morfologia; Ortografia e Acentuação; Pontuação; Regência; Semântica e Lexicologia; Sintaxe
- Tecnologias
- Interpretação de Texto
- Educação Física
- Linguagem Corporal

DISCIPLINA: Espanhol
- Interpretação de Texto
- Charges e HQ's
- Campanhas Publicitárias
- Vocabulário e Semântica

DISCIPLINA: Inglês
- Vocabulário e Semântica
- Interpretação de Texto
- Charges e HQs
- Campanhas Publicitárias

DISCIPLINA: Matemática
- Fundamentos da Matemática: Divisão; Frações; Multiplicação; Potenciação; Radiciação; Soma; Subtração
- Razão, Proporção e Regra de Três: Divisão diretamente proporcional; Divisão inversamente proporcional; Regra de 3 composta; Regra de 3 simples
- Razão e Proporção Avançada: Regra de 3 simples
- Porcentagem: Aumento percentual; Redução percentual; Taxa percentual
- Unidades de Medida e Conversões
- Notação Cientifica
- Escalas: Escalas lineares; Escalas superficiais; Escalas volumétricas
- Vazão
- Matemática Financeira: Aumentos; Descontos; Juros compostos; Juros Simples; Taxa percentual
- Gráficos e Tabelas: Gráficos; Tabelas
- Estatística: Desvio padrão e variância; Medidas de tendência central
- Conjuntos
- Álgebra: Números complexos; Polinômios
- Inequações
- Sistemas e Equações: Escalonamento; Primeiro grau; Segundo grau
- Função do Primeiro Grau
- Progressão Aritmética: Soma dos termos; Termo geral
- Sequências Lógicas
- Progressão Geométrica
- Função do Segundo Grau
- Geometria Plana: Ângulos; Área e perímetro; Circunferências e arcos; Polígonos e semelhança; Razões trigonométricas
- Trigonometria
- Geometria Espacial: Poliedros; Projeção ortogonal
- Geometria Analítica: Circunferência; Plano cartesiano; Reta
- Análise Combinatória: Arranjo; Combinação; Permutação; PFC
- Probabilidade
- Função Exponencial e Logarítmica
- Função Trigonométrica
- Logaritmo
- Matrizes
- Lógica
- MMC e MDC
- Conjuntos Numéricos
- Função Racional

DISCIPLINA: Redação
- Cadernos de Aprimoramento Textual

DISCIPLINA: Intensivo Revisional
- Matemática
- Biologia
- Química
- Física
