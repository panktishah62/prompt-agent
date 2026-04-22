# PriceHunter

PriceHunter is a hybrid price comparison engine that searches e-commerce platforms and nearby local vendors in parallel, then ranks both result sets into a single response.

## What it does

- Structures natural-language shopping queries into product, category, location, and intent.
- Runs an online pipeline with platform discovery plus pluggable adapters.
- Runs an offline pipeline with vendor discovery plus live or mock voice calling.
- Normalizes everything into one `UnifiedResult` schema for comparison.
- Degrades gracefully into convincing demo data when live APIs are unavailable.

## Stack

- Backend: FastAPI, Motor, MongoDB, OpenAI SDK, httpx
- Frontend: React 18, Vite, Tailwind CSS
- Voice: Bland.ai
- Vendor discovery: Google Places API
- Live online pricing: SerpApi Google Shopping API

## Local setup

1. Copy `.env.example` to `.env` in the project root.
2. Add the required live credentials to `.env`.
3. Keep `MOCK_VOICE_CALLS=true` for hackathon demo mode, or set it to `false` with a valid Bland.ai key to enable real vendor calls.
4. To test live calling safely, set `TEST_CALL_PHONE` to your own number. When set, every Bland outbound call is routed to that number instead of the discovered vendor number, while keeping the vendor name and product in the call prompt and metadata.
5. For live online prices, set `SERPAPI_API_KEY`. Without it, the online adapter layer falls back to realistic demo listings.
6. Start the backend:
   ```bash
   python3.12 -m venv .venv
   . .venv/bin/activate
   pip install -r backend/requirements.txt
   cd backend
   uvicorn app.main:app --reload
   ```
7. Start the frontend in a second terminal:
   ```bash
   cd frontend
   npm install
   npm run dev
   ```

## Docker

```bash
docker compose up --build
```

## Fast deploy

The fastest deployment path for the current app is:

1. MongoDB Atlas for the database
2. Render web service for the backend
3. Render static site for the frontend

This repo includes [render.yaml](/Users/panktishah/Desktop/prompt-agent/pricehunter/render.yaml) for that setup.

### Production environment variables

Backend:

- `OPENAI_API_KEY`
- `OPENAI_MODEL=gpt-4o-mini`
- `SERPAPI_API_KEY`
- `GOOGLE_PLACES_API_KEY`
- `BLAND_AI_API_KEY`
- `TEST_CALL_PHONE`
- `FRONTEND_ORIGINS=https://your-frontend-domain.onrender.com`
- `MONGODB_URL=mongodb+srv://...`
- `DATABASE_NAME=pricehunter`
- `BLAND_WEBHOOK_URL=https://your-backend-domain.onrender.com/api/webhooks/voice`
- `MOCK_VOICE_CALLS=true` or `false`

Frontend:

- `VITE_API_URL=https://your-backend-domain.onrender.com`

### Deploy notes

- If you are not using Docker, do not use `mongodb://mongodb:27017`; use your Atlas connection string.
- `FRONTEND_ORIGINS` accepts a comma-separated list if you need both production and preview URLs.
- Keep `MOCK_VOICE_CALLS=true` for the fastest safe launch, then turn it off after Bland is configured.

## Demo behavior

- Missing OpenAI credentials falls back to heuristic query structuring and platform selection.
- Missing `SERPAPI_API_KEY` falls back to simulated online platform listings.
- Missing Google Places credentials falls back to mock Indian vendor discovery.
- Missing Bland.ai credentials or `MOCK_VOICE_CALLS=true` falls back to instant mock call transcripts.
- Setting `TEST_CALL_PHONE` routes every real Bland call to your test phone instead of vendor phone numbers.
- Missing MongoDB does not break search; results still return and persistence logs a warning.
