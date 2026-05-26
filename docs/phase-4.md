# Phase 4: Vector Clustering (pgvector)

## Scope
Phase 4 clusters normalized posts into trend buckets using Supabase pgvector. Each trend explicitly links the top 5 highest-engagement example posts for UI rendering.

## Implemented Module

### Clustering
- Entry point: `cluster_posts(normalized_posts, config)`
- Source: `app/pipeline/clustering.py`

#### Expected input
Each normalized post must include:
- Standard normalized fields (`source`, `source_id`, `community`, `text`, etc.)
- `metrics.score` and `metrics.num_comments` for engagement ranking
- `embedding`: a list of floats with length **1024**

#### What it does
1. Upserts normalized posts into `posts`.
2. Upserts embeddings into `post_embeddings` (pgvector column, 1024 dimensions).
3. Calls Supabase RPC `match_posts` to find similar neighbors per seed.
4. Inserts a trend into `trends` and links the top 5 example posts in `trend_examples`.

## Required Supabase Objects
Tables must exist as created in setup:
- `posts`
- `post_embeddings` (vector(1024))
- `trends`
- `trend_examples`

### Required RPC Function
The clustering step expects a function named `match_posts`:
```sql
create or replace function match_posts(
  query_embedding vector(1024),
  match_threshold float,
  match_count int
)
returns table (post_id uuid, similarity float)
language sql stable as $$
  select post_id,
         1 - (embedding <=> query_embedding) as similarity
  from post_embeddings
  where 1 - (embedding <=> query_embedding) > match_threshold
  order by embedding <=> query_embedding
  limit match_count;
$$;
```

## Environment
The module reads:
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`

## Notes
- Clusters are built via neighbor matches per seed.
- Example posts are selected by engagement score (score + num_comments).
- The module does not compute embeddings; it requires them to be pre-attached.
