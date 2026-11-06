# masar demo - regenerate with:  vhs docs/demo.tape
# Requires the gateway running on :8000 (mock backend, no API keys):
#   uv run uvicorn masar.app:create_app --factory --port 8000
Output docs/demo.gif

Require curl
Require jq

Set Shell "bash"
Set FontSize 19
Set Width 1260
Set Height 760
Set Padding 26
Set Theme "Catppuccin Mocha"
Set TypingSpeed 28ms
Set WindowBar Colorful

# ---------- hidden setup: request bodies + a pretty `route` helper ----------
Hide
Type "clear"
Enter
Type `AR='{"messages":[{"role":"user","content":"راسلني على sana@example.com"}]}'`
Enter
Type `EN='{"messages":[{"role":"user","content":"What is the capital of Qatar?"}]}'`
Enter
Type `TL='{"messages":[{"role":"user","content":"book a flight"}],"tools":[{"type":"function","function":{"name":"book"}}]}'`
Enter
Type `route(){ printf '\033[1;36m# %s\033[0m\n' "$1"; curl -sD - -o /dev/null -X POST localhost:8000/v1/chat/completions -H 'Content-Type: application/json' -d "$2" | grep -iE '^x-masar-(route|model|classification|cost|latency)'; echo; }`
Enter
Type "clear"
Enter
Show

# ---------- intro ----------
Type "# masar - an OpenAI-compatible gateway that routes each request by"
Enter
Type "# data sensitivity, language, and task type.   (mock backend, no API keys)"
Enter
Enter
Sleep 1.1s

# ---------- 1) sovereign ----------
Type `route "Arabic message containing an email address (PII)  ->  must stay SOVEREIGN" "$AR"`
Sleep 400ms
Enter
Sleep 1.9s

# ---------- 2) default ----------
Type `route "Plain English question  ->  cheap DEFAULT route" "$EN"`
Sleep 400ms
Enter
Sleep 1.9s

# ---------- 3) tool_use ----------
Type `route "Request carrying tools  ->  classified as TOOL_USE" "$TL"`
Sleep 400ms
Enter
Sleep 1.9s

# ---------- aggregated accounting ----------
Type "# Aggregated cost + latency accounting, per route and model:"
Enter
Type "curl -s localhost:8000/stats | jq"
Sleep 400ms
Enter
Sleep 3.2s

Sleep 1s
