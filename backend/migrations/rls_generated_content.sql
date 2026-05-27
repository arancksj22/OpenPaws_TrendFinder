-- ============================================================
-- OpenPaws TrendFinder — Row Level Security for generated_content
-- Run this once in your Supabase SQL Editor
-- ============================================================

-- 1. Enable RLS on the table
ALTER TABLE generated_content ENABLE ROW LEVEL SECURITY;

-- 2. Users can only SELECT their own records
CREATE POLICY "Users see own records"
  ON generated_content
  FOR SELECT
  USING (auth.uid()::text = user_id);

-- 3. Users can only INSERT rows for themselves
CREATE POLICY "Users insert own records"
  ON generated_content
  FOR INSERT
  WITH CHECK (auth.uid()::text = user_id);

-- 4. (Optional) Service role bypass — needed for backend writes using service key
-- If your backend inserts with the service_role key, RLS is bypassed automatically.
-- If you want the backend to use the anon key + user JWT instead, no extra policy needed.
