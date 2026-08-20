import requests
from scripts.timeout_config import COMFYUI_WORKFLOW_TIMEOUT_SECONDS
import os
import json
from datetime import datetime
from logging_config import get_logger, write_log

logger = get_logger(__name__)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VRAM_CLEANER_API_PATH = os.path.join(PROJECT_ROOT, "api_template", "vram-cleaner-api.json")

def _normalize_server(server: str) -> str:
    if not server.startswith('http://') and not server.startswith('https://'):
        server = 'http://' + server
    server = server.rstrip('/')
    return server


def post_workflow_api(workflow_json: dict, server: str):
    server = _normalize_server(server)
    # Try the newer /api/workflow endpoint first; fall back to legacy /prompt if server returns 405
    url_api = f"{server}/api/workflow"
    resp = requests.post(url_api, json=workflow_json)
    if resp.status_code == 405:
        # fallback to legacy prompt endpoint
        url_prompt = f"{server}/prompt"
        resp2 = requests.post(url_prompt, json={"prompt": workflow_json})
        resp2.raise_for_status()
        return resp2.json()
    resp.raise_for_status()
    return resp.json()


def run_vram_cleaner(server: str, workflow_path: str = VRAM_CLEANER_API_PATH) -> bool:
    try:
        with open(workflow_path, "r", encoding="utf-8") as f:
            workflow = json.load(f)
    except Exception as e:
        write_log(f"Failed to load VRAM cleaner workflow: {e}", level="error")
        return False
    try:
        result = post_workflow_api(workflow, server)
        write_log(f"Posted VRAM cleaner workflow: {json.dumps(result, ensure_ascii=False)}")
        return True
    except Exception as e:
        write_log(f"Failed to post VRAM cleaner workflow: {e}", level="error")
        return False


def upload_file(server: str, file_path: str, file_type: str = "image"):
    server = _normalize_server(server)
    basename = os.path.basename(file_path)
    attempts = []
    if file_type == "image":
        attempts = [
            (f"{server}/upload/image", "image"),
            (f"{server}/api/upload/image", "image"),
            (f"{server}/upload/image", "file"),
            (f"{server}/api/upload/image", "file"),
        ]
    else:
        attempts = [
            (f"{server}/upload/{file_type}", file_type),
            (f"{server}/upload/{file_type}", "file"),
            (f"{server}/api/upload/{file_type}", file_type),
            (f"{server}/api/upload/{file_type}", "file"),
            # Some ComfyUI servers accept non-image inputs through the standard image upload endpoint.
            (f"{server}/upload/image", "image"),
            (f"{server}/api/upload/image", "image"),
        ]
    errors = []
    for url, field in attempts:
        try:
            with open(file_path, 'rb') as f:
                files = {field: (basename, f)}
                resp = requests.post(url, files=files)
                # Collect response text for diagnostics if status >= 400
                if resp.status_code >= 400:
                    errors.append({'url': url, 'field': field, 'status': resp.status_code, 'text': resp.text[:1000]})
                    continue
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            errors.append({'url': url, 'field': field, 'error': str(e)})

    # All attempts failed; raise with diagnostic info
    raise Exception(f"Upload to /upload/{file_type} failed for {file_path}; attempts: {errors}")


def download_file_url(file_url: str, out_path: str):
    write_log(f"download_file_url called: url={file_url} out_path={out_path}", level='debug')
    resp = requests.get(file_url, stream=True)
    resp.raise_for_status()
    os.makedirs(os.path.dirname(out_path) or '.', exist_ok=True)
    with open(out_path, 'wb') as f:
        for chunk in resp.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)
    write_log(f"download_file_url succeeded: out_path={out_path}", level='debug')
    return out_path


def get_file_url(server: str, filename: str, subfolder: str = None, type_: str = None) -> str:
    server = _normalize_server(server)
    # If a full URL was passed as filename, return it unchanged
    if not filename:
        raise ValueError("filename must be provided")
    if filename.startswith('http://') or filename.startswith('https://'):
        return filename
    # URL-encode filename and optional subfolder to ensure valid query params
    from urllib.parse import quote
    enc_fn = quote(filename, safe='')
    url = f"{server}/view?filename={enc_fn}"
    params = []
    if subfolder:
        params.append(f"subfolder={quote(subfolder, safe='')}" )
    if type_:
        params.append(f"type={quote(type_, safe='')}" )
    if params:
        url += "&" + "&".join(params)
    return url


def get_history_for_prompt(server: str, prompt_id: str, timeout: int = COMFYUI_WORKFLOW_TIMEOUT_SECONDS, interval: float = 10.0):
    """Poll the server's /history/{prompt_id} until the workflow produces outputs.

    This function repeatedly GETs the history URL every `interval` seconds until either
    a non-empty `outputs` entry appears in the returned JSON (indicating image/video
    outputs are available), or `timeout` seconds elapse. Returns the last JSON object
    received (or an empty dict if none).
    """
    server = _normalize_server(server)
    url = f"{server}/history/{prompt_id}"
    import time

    deadline = time.time() + timeout
    last_json = None
    # Simpler behavior: only consider top-level 'outputs' key as a signal
    while time.time() < deadline:
        resp = requests.get(url)
        resp.raise_for_status()
        try:
            j = resp.json()
        except Exception:
            j = None

        if isinstance(j, dict):
            # Direct outputs at top-level
            if 'outputs' in j and j.get('outputs'):
                return j
            # Some servers return a mapping keyed by prompt_id -> { ... , outputs: {...} }
            # handle the common case where the response is {prompt_id: {...}}
            if len(j) == 1:
                sole_val = next(iter(j.values()))
                if isinstance(sole_val, dict) and 'outputs' in sole_val and sole_val.get('outputs'):
                    return sole_val

        last_json = j
        time.sleep(interval)

    return last_json or {}


def wait_for_output(server: str, prompt_id: str, output_type: str = 'image', timeout: int = COMFYUI_WORKFLOW_TIMEOUT_SECONDS, interval: float = 2.0):
    """Poll history for a specific prompt_id until an output of type `output_type` appears.
    Returns the first matching output dict or None if timeout reached.
    """
    import time
    deadline = time.time() + timeout
    def _collect_from_outputs(outputs):
        """Simple collector that looks at top-level outputs dict only."""
        if not isinstance(outputs, dict):
            return None
        # outputs: node_id -> {kind: [items]}
        for node_val in outputs.values():
            if not isinstance(node_val, dict):
                continue
            for kind, items in node_val.items():
                if not isinstance(items, list):
                    continue
                for it in items:
                    if isinstance(it, dict) and 'filename' in it:
                        fn = it.get('filename')
                        sub = it.get('subfolder')
                        typ = it.get('type') or kind
                        if fn and _matches_type_by_ext(fn, output_type):
                            return {'filename': fn, 'subfolder': sub, 'type': typ}
        return None

    while time.time() < deadline:
        # Do not nest the default 500-second history wait inside this timeout.
        # Poll history for at most one interval so the caller's deadline remains
        # authoritative (previously a 600-second wait could last ~17 minutes).
        remaining = max(0.0, deadline - time.time())
        history_timeout = min(max(float(interval), 0.1), remaining)
        hist = get_history_for_prompt(
            server,
            prompt_id,
            timeout=history_timeout,
            interval=min(max(float(interval), 0.1), history_timeout),
        )
        if not isinstance(hist, dict):
            continue

        outputs = hist.get('outputs')
        if outputs:
            info = _collect_from_outputs(outputs)
            if info:
                return info

        remaining = deadline - time.time()
        if remaining > 0 and outputs:
            time.sleep(min(float(interval), remaining))
    return None


def _matches_type_by_ext(filename: str, output_type: str) -> bool:
    filename = filename.lower()
    image_ext = ('.png', '.jpg', '.jpeg', '.webp', '.tiff', '.bmp')
    video_ext = ('.mp4', '.mov', '.webm', '.avi', '.mkv')
    if output_type == 'image':
        return filename.endswith(image_ext)
    if output_type == 'video':
        return filename.endswith(video_ext)
    return False
