-- Aproxima o protótipo do formato da plataforma:
--   lista: nome ("Lista de X"), descrição ("Lista completa de X") e tags (assuntos cobertos);
--   questão: assuntos. A resolução deixou de ser gerada: explicacao fica sempre nula.
alter table public.listas
  add column nome text,
  add column descricao text,
  add column tags text[] not null default '{}';
alter table public.questoes
  add column assuntos text[] not null default '{}';

update public.listas set nome = 'Lista de ' || titulo, descricao = 'Lista completa de ' || titulo
where nome is null;
update public.questoes set explicacao = null where explicacao is not null;

create or replace function public.importar_lista(p jsonb)
returns uuid
language plpgsql
set search_path = ''
as $$
declare
  v_id uuid;
  v_sobram int[];
begin
  insert into public.listas (arquivo, hash_pdf, tipo, titulo, nome, descricao, disciplina, topico,
                             tags, total_questoes)
  values (p->>'arquivo', p->>'hash_pdf', coalesce(p->>'tipo', 'lista'), p->>'titulo',
          coalesce(p->>'nome', 'Lista de ' || (p->>'titulo')),
          coalesce(p->>'descricao', 'Lista completa de ' || (p->>'titulo')),
          p->>'disciplina', p->>'topico',
          coalesce(array(select jsonb_array_elements_text(p->'tags')), '{}'),
          jsonb_array_length(p->'questoes'))
  on conflict (hash_pdf) do update
    set arquivo = excluded.arquivo, tipo = excluded.tipo, titulo = excluded.titulo,
        nome = excluded.nome, descricao = excluded.descricao,
        disciplina = excluded.disciplina, topico = excluded.topico, tags = excluded.tags,
        total_questoes = excluded.total_questoes, status = 'rascunho', atualizado_em = now()
  returning id into v_id;

  select array_agg(numero order by numero) into v_sobram
  from public.questoes
  where lista_id = v_id
    and numero not in (select (q->>'numero')::int from jsonb_array_elements(p->'questoes') q);
  if v_sobram is not null then
    raise exception 'Reimportação deixaria de fora as questões % já cadastradas nesta lista; remova-as antes.', v_sobram;
  end if;

  insert into public.questoes (lista_id, numero, titulo, instituicao, ano, disciplina, topico,
                               assuntos, etapa, dificuldade, enunciado, alternativas, gabarito,
                               figuras, pagina, revisar, observacoes)
  select v_id, (q->>'numero')::int, q->>'titulo', nullif(q->>'instituicao', ''),
         nullif(q->>'ano', '')::int, q->>'disciplina', q->>'topico',
         coalesce(array(select jsonb_array_elements_text(q->'assuntos')), '{}'),
         q->>'etapa', (q->>'dificuldade')::smallint, q->>'enunciado', q->'alternativas',
         q->>'gabarito', coalesce(q->'figuras', '[]'), (q->>'pagina')::int,
         coalesce((q->>'revisar')::boolean, false), q->>'observacoes'
  from jsonb_array_elements(p->'questoes') q
  on conflict (lista_id, numero) do update
    set titulo = excluded.titulo, instituicao = excluded.instituicao, ano = excluded.ano,
        disciplina = excluded.disciplina, topico = excluded.topico, assuntos = excluded.assuntos,
        etapa = excluded.etapa, dificuldade = excluded.dificuldade, enunciado = excluded.enunciado,
        alternativas = excluded.alternativas, gabarito = excluded.gabarito, explicacao = null,
        figuras = excluded.figuras, pagina = excluded.pagina,
        revisar = excluded.revisar, observacoes = excluded.observacoes;

  return v_id;
end;
$$;

revoke execute on function public.importar_lista(jsonb) from public, anon, authenticated;
grant execute on function public.importar_lista(jsonb) to service_role;
