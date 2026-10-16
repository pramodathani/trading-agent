# openai_compatible_backend_check.py

HTTP 401 is reported as a warning, not a failure, because it proves the server is running and only the API key is missing. On 2026-10-16 the llama.cpp server on port 18434 answered `Invalid API Key`; the key is configured in milestone 4.
