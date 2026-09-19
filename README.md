# CSES Agent

CSES Agent is the backend AI service for the CSES Life OS Dashboard. It provides an intelligent workflow assistant that allows the dashboard to query, insert, and analyze data using natural language.

The agent is built with **FastAPI** and uses **Ollama** to run large language models locally. It interfaces directly with the dashboard's SQLite database (managed by Prisma in the `cses-dashboard` project).

## Features

- **FastAPI Backend**: Exposes a Server-Sent Events (SSE) streaming endpoint at `POST /api/chat`.
- **Local LLM Integration**: Uses Ollama for fast, local, and private AI inference.
- **SQL Tools**: The agent is equipped with tools to dynamically inspect the database schema (`get_database_schema`) and execute queries (`execute_sql_query`) to read/write data on behalf of the user.
- **CORS Enabled**: Configured to accept requests from the local Next.js frontend.

## Prerequisites

- Python 3.9+
- [Ollama](https://ollama.com/) running locally (with your preferred model pulled, e.g., `qwen2.5:7b`).
- The `cses-dashboard` project and its SQLite database initialized.

## Setup

1. **Navigate to the directory**:
   ```bash
   cd cses-agent
   ```

2. **Create a virtual environment** (recommended):
   ```bash
   python -m venv venv
   # On macOS/Linux:
   source venv/bin/activate
   # On Windows:
   venv\Scripts\activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure Environment Variables**:
   Copy the example environment file and update the variables if necessary.
   ```bash
   cp .env.example .env
   ```
   Ensure `DATABASE_URL` in `.env` points to the absolute path of your `cses-dashboard`'s `dev.db` file (e.g., `sqlite:///C:/path/to/cses-dashboard/prisma/dev.db`).

## Running the Agent

Start the FastAPI server:

```bash
python main.py
```

The server will start on `http://localhost:8000` with hot-reload enabled. The `cses-dashboard` frontend will communicate with this agent via the `/api/chat` endpoint.
