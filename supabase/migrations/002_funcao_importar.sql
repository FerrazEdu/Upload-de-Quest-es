-- Importa (ou reimporta) uma lista inteira numa transação: ou entra tudo, ou nada.
-- Nunca apaga: se a reimportação deixaria de fora questões já cadastradas, recusa.
create or replace function public.importar_lista(p jsonb)
returns uuid
language plpgsql
set search_path = ''
as $$
declare
  v_id uuid;
  v_sobram int[];
begin
  insert into public.listas (arquivo, hash_pdf, tipo, titulo, disciplina, topico, total_questoes)
  values (p->>'arquivo', p->>'hash_pdf', coalesce(p->>'tipo', 'lista'), p->>'titulo',
          p->>'disciplina', p->>'topico', jsonb_array_length(p->'questoes'))
  on conflict (hash_pdf) do update
    set arquivo = excluded.arquivo, tipo = excluded.tipo, titulo = excluded.titulo,
        disciplina = excluded.disciplina, topico = excluded.topico,
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
                               etapa, dificuldade, enunciado, alternativas, gabarito, explicacao,
                               figuras, pagina, revisar, observacoes)
  select v_id, (q->>'numero')::int, q->>'titulo', nullif(q->>'instituicao', ''),
         nullif(q->>'ano', '')::int, q->>'disciplina', q->>'topico', q->>'etapa',
         (q->>'dificuldade')::smallint, q->>'enunciado', q->'alternativas', q->>'gabarito',
         q->>'explicacao', coalesce(q->'figuras', '[]'), (q->>'pagina')::int,
         coalesce((q->>'revisar')::boolean, false), q->>'observacoes'
  from jsonb_array_elements(p->'questoes') q
  on conflict (lista_id, numero) do update
    set titulo = excluded.titulo, instituicao = excluded.instituicao, ano = excluded.ano,
        disciplina = excluded.disciplina, topico = excluded.topico, etapa = excluded.etapa,
        dificuldade = excluded.dificuldade, enunciado = excluded.enunciado,
        alternativas = excluded.alternativas, gabarito = excluded.gabarito,
        explicacao = excluded.explicacao, figuras = excluded.figuras, pagina = excluded.pagina,
        revisar = excluded.revisar, observacoes = excluded.observacoes;

  return v_id;
end;
$$;

revoke execute on function public.importar_lista(jsonb) from public, anon, authenticated;
grant execute on function public.importar_lista(jsonb) to service_role;

-- Bucket das figuras (leitura pública por URL; upload só com a chave de serviço).
insert into storage.buckets (id, name, public) values ('figuras', 'figuras', true)
on conflict (id) do nothing;
