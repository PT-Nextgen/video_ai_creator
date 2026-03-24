import os
import sys
import json
import argparse
import time
import requests
import urllib.parse

# Ensure project root is importable
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from logging_config import setup_logging, get_logger
from scripts.server_config import get_server_address

setup_logging()
logger = get_logger(__name__)

API_PRODUCTION = os.path.join(ROOT, 'api_production')


def find_audiocraft_key():
    cfg_path = os.path.join(ROOT, 'keys.cfg')
    if not os.path.exists(cfg_path):
        return None
    try:
        with open(cfg_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip().startswith('AUDIOCRAFTKEY'):
                    parts = line.split('=', 1)
                    if len(parts) == 2:
                        return parts[1].strip()
    except Exception:
        return None
    return None


def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def safe_filename(prompt: str) -> str:
    # Replace spaces with underscore, keep other chars
    return prompt.strip().replace(' ', '_')


def generate_sound_for_prompt(server: str, api_key: str, prompt: str, duration: int, out_path: str, timeout: int = 120):
    q = urllib.parse.quote_plus(prompt)
    url = f'http://{server}/generate?prompt={q}&duration={duration}'
    headers = {'X-API-Key': api_key}
    logger.info('Requesting %s', url)
    resp = requests.get(url, headers=headers, stream=True, timeout=timeout)
    if resp.status_code != 200:
        logger.error('Audio server returned status %s for prompt "%s": %s', resp.status_code, prompt, resp.text[:200])
        return False
    try:
        # if an old file exists, archive it with a timestamp suffix
        if os.path.exists(out_path):
            base, ext = os.path.splitext(out_path)
            archive_path = f"{base}_{int(time.time())}{ext}"
            try:
                os.rename(out_path, archive_path)
                logger.info('Archived existing audio to %s', archive_path)
            except Exception as e:
                logger.warning('Failed to archive existing file %s: %s', out_path, e)

        with open(out_path, 'wb') as f:
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        logger.info('Wrote audio %s for prompt "%s"', out_path, prompt)
        return True
    except Exception as e:
        logger.error('Failed to write audio to %s: %s', out_path, e)
        return False


def main(specific_scenes=None, server=None):
    server = server or get_server_address("audio")
    if not os.path.exists(API_PRODUCTION):
        print('api_production folder not found:', API_PRODUCTION)
        return

    scenes = sorted([d for d in os.listdir(API_PRODUCTION) if d.startswith('scene_')])
    if specific_scenes:
        scenes = [s for s in scenes if s in specific_scenes]

    api_key = find_audiocraft_key()
    if not api_key:
        print('AUDIOCRAFTKEY not found. Put keys.cfg in project root or set env variable AUDIOCRAFTKEY')
        return

    for scene in scenes:
        scene_dir = os.path.join(API_PRODUCTION, scene)
        meta_path = os.path.join(scene_dir, 'scene_meta.json')
        if not os.path.exists(meta_path):
            logger.debug('no scene_meta.json in %s', scene_dir)
            continue
        try:
            meta = load_json(meta_path)
        except Exception as e:
            logger.error('Failed to load %s: %s', meta_path, e)
            continue

        sound_prompt = meta.get('sound_prompt')
        duration = meta.get('duration_seconds') or meta.get('duration')
        try:
            duration = int(duration)
        except Exception:
            duration = None

        if not sound_prompt:
            logger.debug('no sound_prompt for %s', scene)
            continue
        if duration is None:
            logger.warning('no valid duration for %s, skipping', scene)
            continue

        prompts = [p.strip() for p in sound_prompt.split(',') if p.strip()]
        for p in prompts:
            filename = safe_filename(p) + '.wav'
            out_path = os.path.join(scene_dir, filename)
            logger.info('Generating audio %s (will overwrite if exists)', out_path)
            ok = generate_sound_for_prompt(server, api_key, p, duration, out_path)
            if not ok:
                logger.error('Failed to generate audio for scene %s prompt "%s"', scene, p)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Generate sound assets via nextgenserver audio API')
    parser.add_argument('--scene', '-s', action='append', help='Scene to process (repeatable)')
    parser.add_argument('--server', default=get_server_address("audio"), help='Audio server host:port')
    args = parser.parse_args()
    main(specific_scenes=args.scene, server=args.server)
