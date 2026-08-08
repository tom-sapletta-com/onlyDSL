# OpenRouter real-LLM test

## Configuration

```bash
cp .env.example .env
```

Set at minimum:

```dotenv
LLM_BACKEND=openrouter
OPENROUTER_API_KEY=sk-or-...
OPENROUTER_MODEL=~openai/gpt-latest
```

The key is read only from the environment. The status endpoint exposes `api_key_present: true/false`, never the value.

## Run web application

```bash
docker compose up -d nats postgres app
```

Open `http://localhost:8787` and execute:

1. Bootstrap twin.
2. Scan sources.
3. Update twin.
4. Generate plan.

## Isolated paid smoke test

```bash
docker compose --profile llm run --rm openrouter-smoke
```

Expected markers:

```text
BOOTSTRAP_OK ...
UPDATE_OK ...
PLAN_OK ...
OPENROUTER_SMOKE_PASS
```

The test goes through `IfuriRuntime` and the registered LLM capabilities. It does not call the provider client from application/domain code.

## Failure behavior

If the model emits prose or invalid DSL, the result is rejected. The application may retry with a generated `ValidationDSL` error block. Rejected model text is not echoed into the retry context.

## Cost control

The smoke command performs three model calls at minimum: bootstrap, update, and build plan. Repair retries can add calls when the model violates the DSL contract. Use an OpenRouter key with a suitable credit limit for development.
