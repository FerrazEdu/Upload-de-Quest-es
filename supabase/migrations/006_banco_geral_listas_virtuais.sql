-- Banco geral de questões + listas virtuais.
--
--   importacoes     um PDF importado (hash único: reimportar atualiza as mesmas questões)
--   questoes        banco geral; cada questão vem de uma importação e pode ser publicada sozinha
--   listas          listas virtuais (nome, descrição, tags...), montadas por filtro/seleção
--   lista_questoes  quais questões estão em cada lista e em que ordem
--
-- Cada importação cria também a "lista padrão" do PDF, que aponta para as suas questões.

create table public.importacoes (
  id             uuid primary key default gen_random_uuid(),
  arquivo        text not null,
  hash_pdf       text not null unique,
  tipo           text not null default 'lista' check (tipo in ('lista', 'simulado')),
  titulo         text not null,
  total_questoes int  not null default 0,
  criado_em      timestamptz not null default now(),
  atualizado_em  timestamptz not null default now()
);

-- A lista existente vira a importação de mesmo id (e continua como lista padrão dela).
insert into public.importacoes (id, arquivo, hash_pdf, tipo, titulo, total_questoes, criado_em, atualizado_em)
select id, arquivo, hash_pdf, tipo, titulo, total_questoes, criado_em, atualizado_em from public.listas;

alter table public.questoes add column importacao_id uuid references public.importacoes (id);
update public.questoes set importacao_id = lista_id;
alter table public.questoes alter column importacao_id set not null;
alter table public.questoes add column publicada boolean not null default false;

create table public.lista_questoes (
  lista_id   uuid not null references public.listas (id) on delete cascade,
  questao_id uuid not null references public.questoes (id) on delete cascade,
  posicao    int  not null,
  primary key (lista_id, questao_id)
);
create index lista_questoes_questao_idx on public.lista_questoes (questao_id);
insert into public.lista_questoes (lista_id, questao_id, posicao)
select lista_id, id, numero from public.questoes;

-- Questão deixa de pertencer a uma lista.
drop policy "questoes: leitura publicadas" on public.questoes;
alter table public.questoes drop column lista_id;
alter table public.questoes add constraint questoes_importacao_numero_key unique (importacao_id, numero);

-- Lista deixa de ser um PDF: guarda só a importação de origem (quando houver).
alter table public.listas add column importacao_id uuid references public.importacoes (id) on delete set null;
update public.listas set importacao_id = id;
alter table public.listas
  drop column arquivo, drop column hash_pdf, drop column tipo, drop column total_questoes, drop column titulo;
alter table public.listas alter column nome set not null;
alter table public.listas alter column descricao set default '';
create index listas_importacao_idx on public.listas (importacao_id);

create view public.listas_resumo with (security_invoker = true) as
select l.*, (select count(*) from public.lista_questoes lq where lq.lista_id = l.id) as total_questoes
from public.listas l;

-- RLS: o aluno lê questões publicadas e listas publicadas.
alter table public.importacoes    enable row level security;
alter table public.lista_questoes enable row level security;
create policy "questoes: leitura publicadas" on public.questoes for select to anon, authenticated
  using (publicada or exists (select 1 from public.lista_questoes lq join public.listas l on l.id = lq.lista_id
                              where lq.questao_id = questoes.id and l.status = 'publicada'));
create policy "lista_questoes: leitura publicadas" on public.lista_questoes for select to anon, authenticated
  using (exists (select 1 from public.listas l where l.id = lista_id and l.status = 'publicada'));

-- Importa um PDF: questões no banco geral + lista padrão da importação. Nunca apaga questões.
create or replace function public.importar_lista(p jsonb)
returns uuid
language plpgsql
set search_path = ''
as $$
declare
  v_imp uuid;
  v_lista uuid;
  v_sobram int[];
begin
  insert into public.importacoes (arquivo, hash_pdf, tipo, titulo, total_questoes)
  values (p->>'arquivo', p->>'hash_pdf', coalesce(p->>'tipo', 'lista'), p->>'titulo',
          jsonb_array_length(p->'questoes'))
  on conflict (hash_pdf) do update
    set arquivo = excluded.arquivo, tipo = excluded.tipo, titulo = excluded.titulo,
        total_questoes = excluded.total_questoes, atualizado_em = now()
  returning id into v_imp;

  select array_agg(numero order by numero) into v_sobram
  from public.questoes
  where importacao_id = v_imp
    and numero not in (select (q->>'numero')::int from jsonb_array_elements(p->'questoes') q);
  if v_sobram is not null then
    raise exception 'Reimportação deixaria de fora as questões % já cadastradas; remova-as antes.', v_sobram;
  end if;

  insert into public.questoes (importacao_id, numero, titulo, instituicao, ano, disciplina, topico,
                               assuntos, etapa, dificuldade, enunciado, alternativas, gabarito,
                               figuras, pagina, revisar, observacoes)
  select v_imp, (q->>'numero')::int, q->>'titulo', nullif(q->>'instituicao', ''),
         nullif(q->>'ano', '')::int, q->>'disciplina', q->>'topico',
         coalesce(array(select jsonb_array_elements_text(q->'assuntos')), '{}'),
         q->>'etapa', (q->>'dificuldade')::smallint, q->>'enunciado', q->'alternativas',
         q->>'gabarito', coalesce(q->'figuras', '[]'), (q->>'pagina')::int,
         coalesce((q->>'revisar')::boolean, false), q->>'observacoes'
  from jsonb_array_elements(p->'questoes') q
  on conflict (importacao_id, numero) do update
    set titulo = excluded.titulo, instituicao = excluded.instituicao, ano = excluded.ano,
        disciplina = excluded.disciplina, topico = excluded.topico, assuntos = excluded.assuntos,
        etapa = excluded.etapa, dificuldade = excluded.dificuldade, enunciado = excluded.enunciado,
        alternativas = excluded.alternativas, gabarito = excluded.gabarito,
        figuras = excluded.figuras, pagina = excluded.pagina,
        revisar = excluded.revisar, observacoes = excluded.observacoes;

  select id into v_lista from public.listas where importacao_id = v_imp order by criado_em limit 1;
  if v_lista is null then
    insert into public.listas (nome, descricao, disciplina, topico, tags, importacao_id)
    values (coalesce(p->>'nome', 'Lista de ' || (p->>'titulo')),
            coalesce(p->>'descricao', 'Lista completa de ' || (p->>'titulo')),
            p->>'disciplina', p->>'topico',
            coalesce(array(select jsonb_array_elements_text(p->'tags')), '{}'), v_imp)
    returning id into v_lista;
  else
    update public.listas
      set disciplina = p->>'disciplina', topico = p->>'topico',
          tags = coalesce(array(select jsonb_array_elements_text(p->'tags')), '{}'), atualizado_em = now()
    where id = v_lista;
  end if;

  insert into public.lista_questoes (lista_id, questao_id, posicao)
  select v_lista, q.id, q.numero from public.questoes q where q.importacao_id = v_imp
  on conflict (lista_id, questao_id) do update set posicao = excluded.posicao;

  return v_lista;
end;
$$;

-- Cria ou atualiza uma lista virtual. As questões vêm como {hash_pdf, numero}, que
-- identificam a questão no banco sem depender de ids locais.
create or replace function public.salvar_lista(p jsonb)
returns uuid
language plpgsql
set search_path = ''
as $$
declare
  v_lista uuid := coalesce((p->>'id')::uuid, gen_random_uuid());
  v_ids uuid[];
  v_faltam int;
begin
  select array_agg(q.id order by e.ord) into v_ids
  from jsonb_array_elements(p->'questoes') with ordinality e(item, ord)
  join public.importacoes i on i.hash_pdf = e.item->>'hash_pdf'
  join public.questoes q on q.importacao_id = i.id and q.numero = (e.item->>'numero')::int;
  v_faltam := jsonb_array_length(p->'questoes') - coalesce(array_length(v_ids, 1), 0);
  if v_faltam > 0 then
    raise exception '% questão(ões) da lista ainda não estão no banco; envie as importações antes.', v_faltam;
  end if;

  insert into public.listas (id, nome, descricao, disciplina, topico, tags, status)
  values (v_lista, p->>'nome', coalesce(p->>'descricao', ''), nullif(p->>'disciplina', ''),
          nullif(p->>'topico', ''), coalesce(array(select jsonb_array_elements_text(p->'tags')), '{}'),
          coalesce(p->>'status', 'rascunho'))
  on conflict (id) do update
    set nome = excluded.nome, descricao = excluded.descricao, disciplina = excluded.disciplina,
        topico = excluded.topico, tags = excluded.tags, status = excluded.status, atualizado_em = now();

  delete from public.lista_questoes where lista_id = v_lista and questao_id <> all (coalesce(v_ids, '{}'));
  insert into public.lista_questoes (lista_id, questao_id, posicao)
  select v_lista, id, ord from unnest(v_ids) with ordinality u(id, ord)
  on conflict (lista_id, questao_id) do update set posicao = excluded.posicao;

  return v_lista;
end;
$$;

revoke execute on function public.importar_lista(jsonb) from public, anon, authenticated;
revoke execute on function public.salvar_lista(jsonb) from public, anon, authenticated;
grant execute on function public.importar_lista(jsonb) to service_role;
grant execute on function public.salvar_lista(jsonb) to service_role;
