# UdyamAI backend

See the root [README](../README.md) for complete local setup, migrations, seed commands, frontend connection steps, API routes, authentication limitations, and test instructions.

The service is FastAPI + SQLAlchemy with Alembic migrations. SQLite is the no-server development default; PostgreSQL is supported by setting `DATABASE_URL`. API credentials and LLM keys are read only by backend configuration.
