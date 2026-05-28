# Self-Hosting Guide for OpenPaws TrendFinder

Welcome! This guide is written specifically for non-profit organizations and IT staff who want to deploy the OpenPaws TrendFinder on their own infrastructure.

TrendFinder uses a modern but standard stack:
- **Frontend**: React (Vite)
- **Backend**: Python (FastAPI)
- **Database & Auth**: Supabase
- **Background Jobs**: Upstash Redis & Python RQ
- **AI Models**: Cerebras (or local models via Ollama) and Pollinations AI

You can host the code on platforms like **Render**, **Railway**, or **Heroku**. This guide assumes you are using **Render** for hosting the code, **Supabase** for the database, and **Upstash** for Redis.

---

## Step 1: Set up Supabase (Database, Auth, and Storage)

Supabase is an open-source alternative to Firebase. It will store your users, the trend data, and the generated images.

1. **Create an account** at [supabase.com](https://supabase.com) and create a new project.
2. **Database Setup**:
   - Go to the **SQL Editor** in your Supabase dashboard.
   - You need to run the SQL migration scripts located in the `backend/migrations/` folder.
   - First, run `create_error_logs.sql` to set up error tracking.
   - Next, run the schema for the generated content:
     ```sql
     CREATE TABLE IF NOT EXISTS generated_content (
         id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
         user_id         text        NOT NULL,
         trend_id        text        NOT NULL,
         advocacy_brief  text,
         positioning_angle text,
         suggested_hashtags jsonb,
         scored_drafts   jsonb       NOT NULL,
         recommended_index integer,
         image_url       text,
         image_prompt    text,
         total_prompt_tokens   integer,
         total_completion_tokens integer,
         created_at      timestamptz NOT NULL DEFAULT now()
     );
     CREATE INDEX IF NOT EXISTS generated_content_user_idx ON generated_content (user_id, created_at DESC);
     ```
3. **Storage Setup**:
   - Go to **Storage** in the left sidebar and click **New Bucket**.
   - Name it exactly `trend-images`.
   - Make sure to set the bucket to **Public** so the dashboard can load the images.
4. **Authentication Setup** (Optional but recommended):
   - Go to **Authentication** > **Providers** and ensure **Email** is enabled.
   - You can disable "Confirm email" if you want to invite your staff manually without email verifications.

---

## Step 2: Set up Upstash Redis (For Background Jobs)

TrendFinder uses a queue to run heavy trend ingestion tasks in the background so the dashboard doesn't freeze.

1. **Create an account** at [upstash.com](https://upstash.com).
2. Click **Create Database**.
3. Name it `trendfinder-redis`, select a region close to your Supabase region, and click Create.
4. Scroll down to the **Connect to your database** section.
5. Look for the **Rediss (TLS)** connection string. It will look something like: `rediss://default:password@region.upstash.io:6379`. Copy this; you will need it later.

---

## Step 3: Get your API Keys

You will need a few API keys to power the AI.

1. **Cerebras**: Go to [Cerebras Inference](https://inference.cerebras.ai/), create an account, and generate an API key. (You can also use an OpenAI key if you change the provider in the code).
2. **Supabase Keys**: Go to your Supabase Project Settings > **API**.
   - Copy the **Project URL**.
   - Copy the **anon / public** key.
   - Copy the **service_role / secret** key.

---

## Step 4: Configure Environment Variables

Create a file named `.env` in the `backend/` folder on your computer. Copy the contents of `backend/.env.example` and fill in the values you collected in the previous steps.

```env
# Supabase
SUPABASE_URL=https://your-project-id.supabase.co
SUPABASE_ANON_KEY=your-anon-key
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key

# Redis
REDIS_URL=rediss://default:password@region.upstash.io:6379

# AI Models
CEREBRAS_API_KEY=your-cerebras-key
```

---

## Step 5: Deploying to Render (or similar platforms)

You need to deploy three things: The Frontend, the Backend API, and the Background Worker.

### 1. Deploy the Backend API (Web Service)
- Connect your GitHub repository to Render.
- Create a new **Web Service**.
- **Build Command**: `cd backend && pip install -r requirements.txt`
- **Start Command**: `cd backend && uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Under **Environment Variables**, copy everything from your `.env` file.

### 2. Deploy the Background Worker (Background Worker)
- Create a new **Background Worker** in Render.
- **Build Command**: `cd backend && pip install -r requirements.txt`
- **Start Command**: `cd backend && rq worker trends-queue --url $REDIS_URL`
- Under **Environment Variables**, copy everything from your `.env` file.

### 3. Deploy the Frontend (Static Site)
- Create a new **Static Site** in Render.
- **Build Command**: `cd frontend && npm install && npm run build`
- **Publish Directory**: `frontend/dist`
- *Note*: If you are hosting the backend on Render, you need to tell the frontend where to find it. In `frontend/src/App.jsx`, change `const API_BASE = '/api/v1/trends'` to point to your new Render backend URL (e.g., `const API_BASE = 'https://your-backend.onrender.com/api/v1/trends'`).

---

## Success!

Once all three services are live, you can navigate to your Frontend URL. Log in using a user account you created in Supabase Auth, and you will see the OpenPaws TrendFinder dashboard!
