-- Área de preparo para importar payloads grandes em partes (usada quando o envio
-- não pode ser feito pela API REST). Esquema privado: não é exposto pela API.
create schema if not exists preparo;
revoke all on schema preparo from public, anon, authenticated;

create table preparo.importacao (
  lote      text not null,
  parte     int  not null,
  texto     text not null,
  criado_em timestamptz not null default now(),
  primary key (lote, parte)
);
alter table preparo.importacao enable row level security;
