-- Reddit Skincare Rank: Postgres schema (Supabase-compatible)
-- Scores are computed at read time from mentions (see views at the bottom), never stored.

create table topics (
  id           serial primary key,
  name         text not null unique,
  subreddits   text[] not null,
  categories   text[] not null
);

create table threads (
  reddit_id    text primary key,
  topic_id     int references topics(id),
  subreddit    text not null,
  title        text,
  url          text,
  created_at   timestamptz,
  score        int,
  last_fetched timestamptz default now()
);

create table comments (
  reddit_id    text primary key,
  thread_id    text references threads(reddit_id) on delete cascade,
  author_hash  text not null,          -- salted hash; usernames are never stored
  body         text not null,
  score        int,
  created_at   timestamptz,
  deleted      boolean default false   -- set by the weekly deleted-content sweep
);

create table entities (
  id             serial primary key,
  type           text not null check (type in ('product', 'ingredient')),
  canonical_name text not null unique,
  brand          text,
  category       text not null
);

create table aliases (
  alias      text primary key,          -- stored lowercase
  entity_id  int references entities(id),
  approved   boolean default false      -- you approve merges in the review queue
);

create table entity_ingredients (
  product_id    int references entities(id),
  ingredient_id int references entities(id),
  primary key (product_id, ingredient_id)
);

create table mentions (
  id            bigserial primary key,
  comment_id    text references comments(reddit_id) on delete cascade,
  entity_id     int references entities(id),
  sentiment     text check (sentiment in ('positive','negative','mixed','neutral')),
  experience    text check (experience in ('firsthand','secondhand','question')),
  reason        text,
  skin_context  text,
  reaction_flag text check (reaction_flag in ('breakout','irritation','purging','none')),
  extracted_at  timestamptz default now()
);
create index on mentions (entity_id);

create table evidence (
  id            serial primary key,
  ingredient_id int references entities(id),
  claim         text not null,
  verdict       text check (verdict in ('supported','mixed','contradicted','not studied')),
  source_url    text,
  checked_at    date,
  approved      boolean default false
);

-- Latest firsthand mention per user per entity
create view latest_mentions as
select distinct on (m.entity_id, c.author_hash)
  m.*, c.author_hash, c.created_at as comment_at
from mentions m
join comments c on c.reddit_id = m.comment_id
where m.experience = 'firsthand' and not c.deleted
order by m.entity_id, c.author_hash, c.created_at desc;

-- Rankings computed at read time: net = (P - N) / U, score = U * (1 + net) / 2
create view entity_scores as
with agg as (
  select entity_id,
    count(*)::numeric as u,
    sum(case sentiment when 'positive' then 1 when 'mixed' then 0.5 else 0 end) as p,
    sum(case sentiment when 'negative' then 1 when 'mixed' then 0.5 else 0 end) as n,
    avg(case when reaction_flag in ('breakout','irritation') then 1 else 0 end) as reaction_rate
  from latest_mentions group by entity_id
)
select e.canonical_name, e.type, e.category, a.u as unique_users,
  round((a.p - a.n) / a.u, 2) as net,
  round(a.u * (1 + (a.p - a.n) / a.u) / 2, 2) as score,
  round(a.reaction_rate, 2) as reaction_rate
from agg a join entities e on e.id = a.entity_id;
