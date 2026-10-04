$env:OLLAMA_MODELS = "E:\FYP\LLMs"
$env:OLLAMA_HOST = "127.0.0.1:11434"
Write-Host "Starting Ollama serve with OLLAMA_MODELS=$env:OLLAMA_MODELS, OLLAMA_HOST=$env:OLLAMA_HOST..."
ollama serve
