# Frontend

This folder contains a self-contained web client for the CreditAssistant backend.

## What it does

- Loads customers from `GET /users`
- Loads profile context from:
  - `GET /users/{user_id}`
  - `GET /credit/profile/{user_id}`
  - `GET /credit/recommendations/{user_id}`
- Sends chat requests to `POST /chat`
- Consumes backend SSE when `stream=true`
- Renders typed progress events and streamed answer text in the chat UI

## Run options

### Preferred: serve from FastAPI

The backend mounts this folder at `/app`, so once the backend is running:

```bash
cd backend
PYTHONPATH=. uvicorn main:app --reload
```

Then open:

```text
http://localhost:8000/app/
```

### Static file option

If you want to serve the frontend separately:

```bash
cd frontend
python3 -m http.server 4173
```

Then open:

```text
http://localhost:4173
```

In that mode, set the backend URL in the UI to `http://localhost:8000`.
