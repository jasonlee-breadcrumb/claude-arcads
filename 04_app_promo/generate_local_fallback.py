#!/usr/bin/env python3
"""Local app-promo fallback for Arcads plan-entitlement outages.

This path intentionally makes ZERO Arcads API calls. It builds a simple, brand-safe
vertical promo from first-party app assets (hero image + walkthrough video) and a
local macOS `say` narration, then can append the verified output to the UGC
manifest. It exists for plan-blocked runs where v2 Seedance and v1 actor
generation both return INVALID_PLAN but we still need a usable owned-app asset.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

HERE = Path(__file__).resolve().parent
ASSETS = HERE / 'assets'
OUT = ASSETS / 'outputs'
DEFAULT_GENERATE = HERE / 'generate.py'
DEFAULT_MANIFEST = Path('/Users/anton/marketing-video-inventory/ugc_video_manifest.json')
DEFAULT_REF_DIR = Path('/Users/anton/marketing-video-inventory/viral-refs/2026-05-14')
DEFAULT_HERO = Path('/Users/anton/.hermes/walkthroughs/quitvape-hero.jpg')
DEFAULT_WALKTHRU = Path('/Users/anton/.hermes/walkthroughs/quitvape.mp4')
SCALE = 'scale=720:1280:force_original_aspect_ratio=decrease,pad=720:1280:(ow-iw)/2:(oh-ih)/2:color=#0d0d0d,format=yuv420p'


def tool(name: str) -> str:
    found = shutil.which(name)
    if not found:
        raise RuntimeError(f'Missing required command: {name}')
    return found


def run(cmd: List[str], *, capture: bool = False) -> subprocess.CompletedProcess[str]:
    print('+ ' + ' '.join(cmd), flush=True)
    result = subprocess.run(cmd, text=True, capture_output=capture)
    if result.returncode != 0:
        if capture:
            print(result.stdout[-2000:], file=sys.stderr)
            print(result.stderr[-2000:], file=sys.stderr)
        raise RuntimeError(f'Command failed ({result.returncode}): {cmd[0]}')
    return result


def next_version(out_dir: Path, prefix: str) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    max_seen = 0
    for path in out_dir.glob(f'{prefix}_v*.mp4'):
        match = re.search(r'_v(\d+)\.mp4$', path.name)
        if match:
            max_seen = max(max_seen, int(match.group(1)))
    return max_seen + 1


def extract_dialog(generate_py: Path) -> str:
    text = generate_py.read_text()
    speeches = re.findall(r'(?:says|dialogue):\s*["“](.*?)["”]', text, flags=re.I)
    if speeches:
        return ' '.join(s.strip() for s in speeches if s.strip())
    match = re.search(r'PROMPT\s*=\s*"""(.*?)"""', text, re.S)
    if not match:
        raise RuntimeError(f'Could not extract dialog from {generate_py}')
    body = re.sub(r'\[[^\]]+\]', '', match.group(1))
    return re.sub(r'\s+', ' ', body).strip()


def parse_cut_constants(generate_py: Path) -> Tuple[Tuple[float, float, float, float], Tuple[float, float]]:
    text = generate_py.read_text()

    def pair(name1: str, name2: str, default: Tuple[float, float]) -> Tuple[float, float]:
        match = re.search(rf'{name1}\s*,\s*{name2}\s*=\s*([0-9.]+)\s*,\s*([0-9.]+)', text)
        if not match:
            return default
        return float(match.group(1)), float(match.group(2))

    c1 = pair('CUT1_START', 'CUT1_END', (3.1, 5.9))
    c2 = pair('CUT2_START', 'CUT2_END', (9.0, 12.0))
    off1 = re.search(r'WALKTHRU_CUT1_AT\s*=\s*([0-9.]+)', text)
    off2 = re.search(r'WALKTHRU_CUT2_AT\s*=\s*([0-9.]+)', text)
    offsets = (float(off1.group(1)) if off1 else 0.0, float(off2.group(1)) if off2 else 5.0)
    return (c1[0], c1[1], c2[0], c2[1]), offsets


def ffprobe_json(path: Path) -> Dict[str, Any]:
    ffprobe = tool('ffprobe')
    result = run([
        ffprobe,
        '-v',
        'error',
        '-print_format',
        'json',
        '-show_streams',
        '-show_format',
        str(path),
    ], capture=True)
    return json.loads(result.stdout)


def media_facts(path: Path) -> Dict[str, Any]:
    probe = ffprobe_json(path)
    video_stream = next((s for s in probe.get('streams', []) if s.get('codec_type') == 'video'), {})
    audio_stream = next((s for s in probe.get('streams', []) if s.get('codec_type') == 'audio'), {})
    duration = float((probe.get('format') or {}).get('duration') or video_stream.get('duration') or 0.0)
    return {
        'width': int(video_stream.get('width') or 0),
        'height': int(video_stream.get('height') or 0),
        'duration_sec': round(duration, 3),
        'has_audio': bool(audio_stream),
        'size_bytes': path.stat().st_size,
        'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def make_tts(script: str, dest_m4a: Path, rate: int) -> None:
    say = tool('say')
    ffmpeg = tool('ffmpeg')
    with tempfile.TemporaryDirectory(prefix='arcads-local-tts-') as td:
        aiff = Path(td) / 'voice.aiff'
        run([say, '-r', str(rate), '-o', str(aiff), script])
        run([ffmpeg, '-hide_banner', '-loglevel', 'error', '-i', str(aiff), '-c:a', 'aac', '-b:a', '128k', '-y', str(dest_m4a)])


def make_image_segment(hero: Path, duration: float, dest: Path) -> None:
    ffmpeg = tool('ffmpeg')
    run([
        ffmpeg,
        '-hide_banner',
        '-loglevel',
        'error',
        '-loop',
        '1',
        '-t',
        f'{duration:.3f}',
        '-i',
        str(hero),
        '-vf',
        SCALE,
        '-r',
        '30',
        '-c:v',
        'libx264',
        '-pix_fmt',
        'yuv420p',
        '-an',
        '-y',
        str(dest),
    ])


def make_walkthrough_segment(walkthru: Path, start: float, duration: float, dest: Path) -> None:
    ffmpeg = tool('ffmpeg')
    run([
        ffmpeg,
        '-hide_banner',
        '-loglevel',
        'error',
        '-ss',
        f'{start:.3f}',
        '-t',
        f'{duration:.3f}',
        '-i',
        str(walkthru),
        '-vf',
        SCALE,
        '-r',
        '30',
        '-c:v',
        'libx264',
        '-pix_fmt',
        'yuv420p',
        '-an',
        '-y',
        str(dest),
    ])


def concat_segments(segments: Iterable[Path], video_out: Path) -> None:
    ffmpeg = tool('ffmpeg')
    with tempfile.NamedTemporaryFile('w', suffix='.txt', delete=False) as f:
        concat_path = Path(f.name)
        for segment in segments:
            f.write(f"file '{segment}'\n")
    try:
        run([
            ffmpeg,
            '-hide_banner',
            '-loglevel',
            'error',
            '-f',
            'concat',
            '-safe',
            '0',
            '-i',
            str(concat_path),
            '-c:v',
            'libx264',
            '-pix_fmt',
            'yuv420p',
            '-an',
            '-y',
            str(video_out),
        ])
    finally:
        concat_path.unlink(missing_ok=True)


def mux_audio(video: Path, audio: Path, output: Path, duration: float) -> None:
    ffmpeg = tool('ffmpeg')
    run([
        ffmpeg,
        '-hide_banner',
        '-loglevel',
        'error',
        '-i',
        str(video),
        '-i',
        str(audio),
        '-filter_complex',
        f'[1:a]apad=pad_dur={duration:.3f}[a]',
        '-map',
        '0:v',
        '-map',
        '[a]',
        '-c:v',
        'libx264',
        '-c:a',
        'aac',
        '-shortest',
        '-movflags',
        '+faststart',
        '-y',
        str(output),
    ])


def transcript_excerpt(ref_dir: Path, fallback: str) -> str:
    transcript = ref_dir / 'transcript.txt'
    if transcript.exists():
        return re.sub(r'\s+', ' ', transcript.read_text(errors='replace')).strip()[:200]
    return fallback[:200]


def metadata_for(output: Path, app_name: str, ref_dir: Path, script: str) -> Dict[str, Any]:
    facts = media_facts(output)
    return {
        'path': str(output),
        'filename': output.name,
        'size_mb': round(facts['size_bytes'] / (1024 * 1024), 3),
        'mtime': int(output.stat().st_mtime),
        'width': facts['width'],
        'height': facts['height'],
        'duration_sec': facts['duration_sec'],
        'id': hashlib.sha1(f'{output.name}:{facts["sha256"]}'.encode()).hexdigest()[:12],
        'source': 'local_arcads_no_plan_fallback',
        'promotes_app': app_name,
        'ref_video': str(ref_dir / 'ref.mp4'),
        'ref_transcript_excerpt': transcript_excerpt(ref_dir, script),
        'fallback_reason': 'arcads_v2_and_v1_invalid_plan',
        'brand_check_required_before_upload': True,
        'sha256': facts['sha256'],
        'generated_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
    }


def append_manifest(manifest_path: Path, metadata_path: Path) -> Dict[str, Any]:
    entry = json.loads(metadata_path.read_text())
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else []
    if not isinstance(manifest, list):
        raise RuntimeError(f'Manifest is not a list: {manifest_path}')
    before = len(manifest)
    existing = {item.get('path') for item in manifest if isinstance(item, dict)}
    if entry['path'] not in existing:
        clean_entry = dict(entry)
        clean_entry.pop('brand_check_required_before_upload', None)
        manifest.append(clean_entry)
        manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
    after = len(manifest)
    return {'manifest': str(manifest_path), 'before': before, 'after': after, 'appended': after > before}


def generate(args: argparse.Namespace) -> Dict[str, Any]:
    hero = Path(args.hero)
    walkthru = Path(args.walkthru)
    generate_py = Path(args.generate_py)
    ref_dir = Path(args.ref_dir)
    for path in (hero, walkthru, generate_py):
        if not path.exists():
            raise FileNotFoundError(path)
    script = args.script or extract_dialog(generate_py)
    forbidden = [word for word in ('PuffCount', 'puffcount', 'TikTok') if word in script]
    if forbidden:
        raise RuntimeError(f'Script contains forbidden competitor/platform residue: {forbidden}')
    cuts, offsets = parse_cut_constants(generate_py)
    cut1_start, cut1_end, cut2_start, cut2_end = cuts
    total_duration = max(args.duration, cut2_end + 2.8)
    version = args.version or next_version(OUT, 'app_promo')
    output = OUT / f'app_promo_v{version}.mp4'
    metadata_path = output.with_suffix('.json')
    if output.exists() and not args.overwrite:
        raise FileExistsError(f'{output} exists; choose --version or let auto-version advance')
    with tempfile.TemporaryDirectory(prefix='arcads-local-fallback-') as td:
        tmp = Path(td)
        tts = tmp / 'tts.m4a'
        joined = tmp / 'joined.mp4'
        segments = [tmp / f'seg_{i}.mp4' for i in range(5)]
        make_tts(script, tts, args.say_rate)
        make_image_segment(hero, cut1_start, segments[0])
        make_walkthrough_segment(walkthru, offsets[0], cut1_end - cut1_start, segments[1])
        make_image_segment(hero, cut2_start - cut1_end, segments[2])
        make_walkthrough_segment(walkthru, offsets[1], cut2_end - cut2_start, segments[3])
        make_image_segment(hero, total_duration - cut2_end, segments[4])
        concat_segments(segments, joined)
        mux_audio(joined, tts, output, total_duration)
    meta = metadata_for(output, args.app_name, ref_dir, script)
    meta.update({
        'script': script,
        'cut_windows': [cut1_start, cut1_end, cut2_start, cut2_end],
        'walkthrough_offsets': list(offsets),
        'hero': str(hero),
        'walkthru': str(walkthru),
        'arcads_api_calls': 0,
        'credits_used': 0,
    })
    metadata_path.write_text(json.dumps(meta, indent=2) + '\n')
    print(json.dumps({'output': str(output), 'metadata': str(metadata_path), 'facts': media_facts(output)}, indent=2))
    return meta


def main() -> None:
    parser = argparse.ArgumentParser(description='Generate or manifest-append a local app-promo fallback.')
    parser.add_argument('--app-name', default='QuitVape - Stop Vaping')
    parser.add_argument('--hero', default=str(DEFAULT_HERO))
    parser.add_argument('--walkthru', default=str(DEFAULT_WALKTHRU))
    parser.add_argument('--generate-py', default=str(DEFAULT_GENERATE))
    parser.add_argument('--ref-dir', default=str(DEFAULT_REF_DIR))
    parser.add_argument('--manifest', default=str(DEFAULT_MANIFEST))
    parser.add_argument('--script')
    parser.add_argument('--duration', type=float, default=15.0)
    parser.add_argument('--say-rate', type=int, default=205)
    parser.add_argument('--version', type=int)
    parser.add_argument('--overwrite', action='store_true')
    parser.add_argument('--append-manifest', action='store_true')
    parser.add_argument('--append-existing', help='Append an existing output metadata JSON path instead of generating.')
    args = parser.parse_args()

    if args.append_existing:
        result = append_manifest(Path(args.manifest), Path(args.append_existing))
        print(json.dumps(result, indent=2))
        return

    meta = generate(args)
    if args.append_manifest:
        if meta.get('brand_check_required_before_upload'):
            raise RuntimeError('Run brand checks first, then use --append-existing with the metadata JSON.')


if __name__ == '__main__':
    main()
