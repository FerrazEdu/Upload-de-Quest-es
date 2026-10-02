-- Protótipo do banco de questões.
-- Texto rico (enunciado, alternativas, explicação) é Markdown com LaTeX entre $...$ / $$...$$.
-- Figuras ficam no bucket público "figuras" e entram no texto como ![descrição](URL).

create table public.topicos (
  disciplina text not null,
  topico     text not null,
  assuntos   text[] not null default '{}',
  primary key (disciplina, topico)
);

create table public.listas (
  id             uuid primary key default gen_random_uuid(),
  arquivo        text not null,
  hash_pdf       text not null unique,          -- reimportar o mesmo PDF atualiza a lista
  tipo           text not null default 'lista' check (tipo in ('lista', 'simulado')),
  titulo         text not null,
  disciplina     text,
  topico         text,
  total_questoes int not null default 0,
  status         text not null default 'rascunho' check (status in ('rascunho', 'publicada')),
  criado_em      timestamptz not null default now(),
  atualizado_em  timestamptz not null default now(),
  foreign key (disciplina, topico) references public.topicos (disciplina, topico)
);

create table public.questoes (
  id           uuid primary key default gen_random_uuid(),
  lista_id     uuid not null references public.listas (id) on delete cascade,
  numero       int  not null check (numero > 0),
  titulo       text not null,
  instituicao  text,
  ano          int  check (ano between 1900 and 2100),
  disciplina   text not null,
  topico       text not null,
  etapa        text check (etapa in ('Fixação', 'Treinamento', 'Aprofundamento', 'Desafios')),
  dificuldade  smallint not null check (dificuldade between 1 and 5),
  enunciado    text not null,
  alternativas jsonb not null,                  -- {"A": "...", "B": "...", ...}
  gabarito     char(1) not null check (gabarito in ('A', 'B', 'C', 'D', 'E')),
  explicacao   text,
  figuras      jsonb not null default '[]',     -- [{"nome": "...", "url": "...", "descricao": "..."}]
  pagina       int,
  revisar      boolean not null default false,
  observacoes  text,
  criado_em    timestamptz not null default now(),
  unique (lista_id, numero),
  foreign key (disciplina, topico) references public.topicos (disciplina, topico),
  check (jsonb_typeof(alternativas) = 'object' and alternativas ? gabarito)
);

create index questoes_topico_idx on public.questoes (disciplina, topico);

-- RLS: leitura pública só do que foi publicado; escrita só com a chave de serviço.
alter table public.topicos  enable row level security;
alter table public.listas   enable row level security;
alter table public.questoes enable row level security;

create policy "topicos: leitura" on public.topicos for select to anon, authenticated using (true);
create policy "listas: leitura publicadas" on public.listas for select to anon, authenticated
  using (status = 'publicada');
create policy "questoes: leitura publicadas" on public.questoes for select to anon, authenticated
  using (exists (select 1 from public.listas l where l.id = lista_id and l.status = 'publicada'));
