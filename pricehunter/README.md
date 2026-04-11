# PriceHunter

PriceHunter is a hybrid price comparison engine that searches e-commerce platforms and nearby local vendors in parallel, then ranks both result sets into a single response.

## What it does

- Structures natural-language shopping queries into product, category, location, and intent.
- Runs an online pipeline with platform discovery plus pluggable adapters.
- Runs an offline pipeline with vendor discovery plus live or mock voice calling.
- Normalizes everything into one `UnifiedResult` schema for comparison.
- Degrades gracefully into convincing demo data when live APIs are unavailable.

## Stack

- Backend: FastAPI, Motor, MongoDB, Anthropic SDK, httpx
- Frontend: React 18, Vite, Tailwind CSS
- Voice: Bland.ai
- Vendor discovery: Google Places API

## Local setup

1. Copy `.env.example` to `.env` in the project root.
2. Keep `MOCK_VOICE_CALLS=true` for hackathon demo mode, or provide live API keys to enable real integrations.
3. Start the backend:
   ```bash
   python3.12 -m venv .venv
   . .venv/bin/activate
   pip install -r backend/requirements.txt
   cd backend
   uvicorn app.main:app --reload
   ```
4. Start the frontend in a second terminal:
   ```bash
   cd frontend
   npm install
   npm run dev
   ```

## Docker

```bash
docker compose up --build
```

## Demo behavior

- Missing Anthropic credentials falls back to heuristic query structuring and platform selection.
- Missing Google Places credentials falls back to mock Indian vendor discovery.
- Missing Bland.ai credentials or `MOCK_VOICE_CALLS=true` falls back to instant mock call transcripts.
- Missing MongoDB does not break search; results still return and persistence logs a warning.
