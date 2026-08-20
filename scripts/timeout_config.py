"""Central timeout policy for external model/service calls."""

COMFYUI_WORKFLOW_TIMEOUT_SECONDS = 7200
LLM_CALL_TIMEOUT_SECONDS = 600
TTS_CALL_TIMEOUT_SECONDS = 600

# Poll intervals are not operation timeouts and remain independent.
COMFYUI_POLL_INTERVAL_SECONDS = 10.0
SHORT_POLL_INTERVAL_SECONDS = 2.0
