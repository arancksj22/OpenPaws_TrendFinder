-- Enable the pgvector extension just in case it's missing
CREATE EXTENSION IF NOT EXISTS vector;

-- Create the required vector similarity search RPC
CREATE OR REPLACE FUNCTION public.match_posts(
  query_embedding vector(1024),
  match_threshold float,
  match_count int
)
RETURNS TABLE (post_id uuid, similarity float)
LANGUAGE sql STABLE AS $$
  SELECT post_id,
         1 - (embedding <=> query_embedding) AS similarity
  FROM public.post_embeddings
  WHERE 1 - (embedding <=> query_embedding) > match_threshold
  ORDER BY embedding <=> query_embedding
  LIMIT match_count;
$$;
