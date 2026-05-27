-- ============================================================
-- OpenPaws TrendFinder — Create Storage Bucket
-- Run this in your Supabase SQL Editor to create the bucket
-- ============================================================

-- 1. Create the bucket if it doesn't exist
INSERT INTO storage.buckets (id, name, public)
VALUES ('trend-images', 'trend-images', true)
ON CONFLICT (id) DO NOTHING;

-- 2. Allow public access to read the images
CREATE POLICY "Public Access" 
  ON storage.objects FOR SELECT 
  USING ( bucket_id = 'trend-images' );

-- 3. Allow authenticated users to upload images
CREATE POLICY "Auth Upload" 
  ON storage.objects FOR INSERT 
  WITH CHECK (
    bucket_id = 'trend-images' 
    AND auth.role() = 'authenticated'
  );

-- 4. Allow users to update their own images
CREATE POLICY "Auth Update" 
  ON storage.objects FOR UPDATE 
  USING (
    bucket_id = 'trend-images' 
    AND auth.role() = 'authenticated'
  );
