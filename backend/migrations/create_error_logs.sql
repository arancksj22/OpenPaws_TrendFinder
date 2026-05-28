-- ============================================================
-- OpenPaws TrendFinder — Create API Error Logs Table
-- Run this once in your Supabase SQL Editor
-- ============================================================

CREATE TABLE IF NOT EXISTS public.api_error_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    timestamp TIMESTAMPTZ NOT NULL DEFAULT now(),
    endpoint TEXT NOT NULL,
    method TEXT NOT NULL,
    error_message TEXT NOT NULL,
    stack_trace TEXT NOT NULL
);

-- Enable RLS but since this is internal logging, we only want the backend to insert
ALTER TABLE public.api_error_logs ENABLE ROW LEVEL SECURITY;

-- Allow only the service_role (backend) to insert and view logs
CREATE POLICY "Service Role Full Access" 
    ON public.api_error_logs 
    FOR ALL 
    TO service_role 
    USING (true) 
    WITH CHECK (true);
