#!/usr/bin/env python3
"""Arcads v1 fallback for app-promo videos when v2/Seedance is plan-blocked.

Default mode is a read-only dry run: it verifies assets, extracts the spoken
script from 04_app_promo/generate.py, scans v1 inventory, and prints the exact
resource ids a live run would use. Pass --run to create the v1 script/video job.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests

ROOT = Path(__file__).resolve().parents[1]
HERE = Path(__file__).resolve().parent
ASSETS = HERE / "assets"
OUT = ASSETS / "outputs"
sys.path.insert(0, str(ROOT))

import arcads_client as ac  # noqa: E402

DEFAULT_CUTS = (3.5, 6.5, 10.0, 13.0)
DEFAULT_WALKTHRU_OFFSETS = (0.0, 5.0)


def _items(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("items", "data", "results"):
        value = payload.get(key)
        if isinstance(value, list):
            return [x for x in value if isinstance(x, dict)]
        if isinstance(value, dict):
            nested = _items(value)
            if nested:
                return nested
    return []


def _extract_id(payload: Any) -> Optional[str]:
    if isinstance(payload, dict):
        for key in ("id", "assetId", "videoId", "scriptId"):
            if payload.get(key):
                return str(payload[key])
        for key in ("data", "item", "asset", "video", "script"):
            found = _extract_id(payload.get(key))
            if found:
                return found
    return None


def api_get(path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    response = requests.get(ac.BASE + path, headers=ac.HEADERS, params=params or {}, timeout=45)
    try:
        payload = response.json()
    except Exception as exc:  # pragma: no cover - defensive, printed for operator diagnostics
        raise RuntimeError(f"Arcads GET {path} returned non-JSON HTTP {response.status_code}: {response.text[:300]}") from exc
    if response.status_code >= 400:
        raise RuntimeError(f"Arcads GET {path} failed HTTP {response.status_code}: {json.dumps(payload)[:500]}")
    return payload


def api_post(path: str, body: Dict[str, Any]) -> Dict[str, Any]:
    response = requests.post(ac.BASE + path, headers=ac.HEADERS, json=body, timeout=60)
    try:
        payload = response.json()
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(f"Arcads POST {path} returned non-JSON HTTP {response.status_code}: {response.text[:300]}") from exc
    if response.status_code >= 400:
        safe = {k: v for k, v in body.items() if k not in {"text", "prompt"}}
        raise RuntimeError(
            f"Arcads POST {path} failed HTTP {response.status_code}: {json.dumps(payload)[:500]} request={safe}"
        )
    return payload


def extract_dialog(generate_py: Path) -> str:
    text = generate_py.read_text()
    # Prefer quoted speech lines from the current prompt. Supports curly and straight quotes.
    speeches = re.findall(r"says:\s*[\"“](.*?)[\"”]", text)
    if speeches:
        return "\n".join(s.strip() for s in speeches if s.strip())
    match = re.search(r'PROMPT\s*=\s*"""(.*?)"""', text, re.S)
    if match:
        body = re.sub(r"\[[^\]]+\]", "", match.group(1))
        return re.sub(r"\s+", " ", body).strip()
    raise RuntimeError(f"Could not extract dialog from {generate_py}")


def parse_cut_constants(generate_py: Path) -> Tuple[Tuple[float, float, float, float], Tuple[float, float]]:
    text = generate_py.read_text()
    def pair(name1: str, name2: str, default: Tuple[float, float]) -> Tuple[float, float]:
        match = re.search(rf"{name1}\s*,\s*{name2}\s*=\s*([0-9.]+)\s*,\s*([0-9.]+)", text)
        if not match:
            return default
        return float(match.group(1)), float(match.group(2))
    c1 = pair("CUT1_START", "CUT1_END", DEFAULT_CUTS[:2])
    c2 = pair("CUT2_START", "CUT2_END", DEFAULT_CUTS[2:])
    off1 = re.search(r"WALKTHRU_CUT1_AT\s*=\s*([0-9.]+)", text)
    off2 = re.search(r"WALKTHRU_CUT2_AT\s*=\s*([0-9.]+)", text)
    offsets = (
        float(off1.group(1)) if off1 else DEFAULT_WALKTHRU_OFFSETS[0],
        float(off2.group(1)) if off2 else DEFAULT_WALKTHRU_OFFSETS[1],
    )
    return (c1[0], c1[1], c2[0], c2[1]), offsets


def score_situation(situation: Dict[str, Any], desired_gender: str) -> int:
    tags = {str(t).lower() for t in situation.get("tags") or []}
    accessories = {str(a).lower() for a in situation.get("accessories") or []}
    actor = situation.get("actor") or {}
    score = 0
    if situation.get("showYourAppEnabled"):
        score += 100
    if situation.get("talkingActorEnabled"):
        score += 30
    if "phone" in accessories:
        score += 14
    if "home" in tags:
        score += 8
    if actor.get("gender") == desired_gender:
        score += 8
    if not situation.get("isPro"):
        score += 4
    if situation.get("defaultVoiceId"):
        score += 3
    return score


def find_situation(max_pages: int, desired_gender: str) -> Tuple[Dict[str, Any], int, int, int]:
    best: Optional[Dict[str, Any]] = None
    seen = talking = show_app = 0
    for page in range(1, max_pages + 1):
        payload = api_get("/v1/situations", {"limit": 200, "page": page})
        page_items = _items(payload)
        if not page_items:
            break
        for situation in page_items:
            seen += 1
            if situation.get("talkingActorEnabled"):
                talking += 1
            if situation.get("showYourAppEnabled"):
                show_app += 1
            if not situation.get("talkingActorEnabled"):
                continue
            if best is None or score_situation(situation, desired_gender) > score_situation(best, desired_gender):
                best = situation
        # Native app-screen situations are decisive; no need to scan forever once one is found.
        if best and best.get("showYourAppEnabled"):
            break
    if not best:
        raise RuntimeError(f"No talkingActorEnabled Arcads v1 situation found in {seen} scanned situations")
    return best, seen, talking, show_app


def select_voice(situation: Dict[str, Any], desired_gender: str) -> Tuple[str, str]:
    if situation.get("defaultVoiceId"):
        return str(situation["defaultVoiceId"]), "situation.defaultVoiceId"
    voices = _items(api_get("/v1/voices", {"limit": 200}))
    for voice in voices:
        if voice.get("language") == "English" and voice.get("gender") == desired_gender:
            return str(voice["id"]), f"voice:{voice.get('name')}"
    for voice in voices:
        if voice.get("language") == "English":
            return str(voice["id"]), f"voice:{voice.get('name')}"
    raise RuntimeError("No English Arcads voice found in first v1 voices page")


def local_ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    raise RuntimeError("ffmpeg not found on PATH")


def build_hard_cut(seedance_file: Path, final_file: Path, walkthru_path: Path, cuts: Tuple[float, float, float, float], offsets: Tuple[float, float]) -> None:
    ffmpeg = local_ffmpeg()
    cut1_start, cut1_end, cut2_start, cut2_end = cuts
    walk1_at, walk2_at = offsets
    scale = "scale=720:1280:force_original_aspect_ratio=decrease,pad=720:1280:(ow-iw)/2:(oh-ih)/2:color=#0d0d0d"
    tmp = {k: OUT / f"tmp_v1_fallback_{k}.mp4" for k in ["v1", "v2", "v3", "v4", "v5", "aud", "vid"]}
    concat_txt = OUT / "tmp_v1_fallback_concat.txt"
    subprocess.run([ffmpeg, "-i", str(seedance_file), "-vn", "-c:a", "aac", "-y", str(tmp["aud"])], check=True, capture_output=True)
    segments = [
        (["-i", str(seedance_file), "-t", str(cut1_start)], tmp["v1"]),
        (["-ss", str(walk1_at), "-t", str(cut1_end - cut1_start), "-i", str(walkthru_path)], tmp["v2"]),
        (["-ss", str(cut1_end), "-t", str(cut2_start - cut1_end), "-i", str(seedance_file)], tmp["v3"]),
        (["-ss", str(walk2_at), "-t", str(cut2_end - cut2_start), "-i", str(walkthru_path)], tmp["v4"]),
        (["-ss", str(cut2_end), "-i", str(seedance_file)], tmp["v5"]),
    ]
    for args, out_path in segments:
        subprocess.run([ffmpeg] + args + ["-vf", scale, "-c:v", "libx264", "-r", "30", "-an", "-y", str(out_path)], check=True, capture_output=True)
    concat_txt.write_text("".join(f"file '{seg}'\n" for _, seg in segments))
    subprocess.run([ffmpeg, "-f", "concat", "-safe", "0", "-i", str(concat_txt), "-c:v", "libx264", "-an", "-y", str(tmp["vid"])], check=True, capture_output=True)
    subprocess.run([ffmpeg, "-i", str(tmp["vid"]), "-i", str(tmp["aud"]), "-c:v", "copy", "-c:a", "aac", "-shortest", "-y", str(final_file)], check=True, capture_output=True)
    for path in list(tmp.values()) + [concat_txt]:
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Arcads v1 lipsync + local hard-cut fallback for app-promo videos")
    parser.add_argument("--run", action="store_true", help="Create Arcads v1 script/video job. Omitted means read-only dry run.")
    parser.add_argument("--max-pages", type=int, default=24, help="Max v1 situation pages to scan (50 items returned per page today).")
    parser.add_argument("--gender", choices=["Female", "Male"], default="Female")
    parser.add_argument("--script-file", type=Path, help="Plain spoken script. Defaults to speech extracted from generate.py.")
    parser.add_argument("--name", default=f"JR app-promo v1 fallback {time.strftime('%Y-%m-%d')}")
    args = parser.parse_args()

    if not ac.HEADERS.get("Authorization"):
        raise RuntimeError("ARCADS_KEY is not available")
    if not ac.PRODUCT_ID:
        raise RuntimeError("ARCADS_PRODUCT_ID is not available")

    OUT.mkdir(parents=True, exist_ok=True)
    generate_py = HERE / "generate.py"
    walkthru_path = ASSETS / "walkthru.MP4"
    if not walkthru_path.exists():
        raise RuntimeError(f"Missing walkthrough asset: {walkthru_path}")
    script_text = args.script_file.read_text().strip() if args.script_file else extract_dialog(generate_py)
    if len(script_text) < 20:
        raise RuntimeError("Extracted script is too short for Arcads v1 generation")
    cuts, offsets = parse_cut_constants(generate_py)

    situation, seen, talking, show_app = find_situation(args.max_pages, args.gender)
    actor = situation.get("actor") or {}
    actor_id = actor.get("id")
    voice_id, voice_source = select_voice(situation, args.gender)
    if not actor_id:
        raise RuntimeError(f"Selected situation {situation.get('id')} has no actor id")

    summary = {
        "dry_run": not args.run,
        "script_chars": len(script_text),
        "situation_id": situation.get("id"),
        "situation_tags": situation.get("tags"),
        "talkingActorEnabled": situation.get("talkingActorEnabled"),
        "showYourAppEnabled": situation.get("showYourAppEnabled"),
        "actor_id": actor_id,
        "actor_name": actor.get("name"),
        "actor_gender": actor.get("gender"),
        "voice_id": voice_id,
        "voice_source": voice_source,
        "situations_seen": seen,
        "talking_situations_seen": talking,
        "show_app_situations_seen": show_app,
        "walkthru": str(walkthru_path),
        "cuts": cuts,
        "walkthru_offsets": offsets,
        "native_app_screen": bool(situation.get("showYourAppEnabled")),
        "local_hard_cut_required": not bool(situation.get("showYourAppEnabled")),
    }
    print("V1_FALLBACK_SELECTION")
    print(json.dumps(summary, indent=2))

    if not args.run:
        print("DRY_RUN_OK no Arcads asset was created; pass --run to spend credits and generate.")
        return 0

    script_payload = api_post("/v1/scripts", {"name": args.name, "text": script_text})
    script_id = _extract_id(script_payload)
    if not script_id:
        raise RuntimeError(f"/v1/scripts returned no id: {json.dumps(script_payload)[:500]}")
    video_payload = api_post("/v1/videos", {
        "scriptId": script_id,
        "situationId": situation["id"],
        "actorId": actor_id,
        "voiceId": voice_id,
    })
    asset_id = _extract_id(video_payload)
    if not asset_id:
        raise RuntimeError(f"/v1/videos returned no asset id: {json.dumps(video_payload)[:500]}")
    print(f"V1_JOB_ID {asset_id}")
    clip_data = ac.poll(asset_id, "V1AppPromo")
    if clip_data.get("status") == "failed":
        raise RuntimeError(f"Arcads v1 generation failed: {json.dumps(clip_data)[:500]}")
    version = ac.next_version(str(OUT), "app_promo")
    raw_file = OUT / f"app_v1_fallback_raw_v{version}.mp4"
    final_file = OUT / f"app_promo_v{version}.mp4"
    if not ac.download(clip_data, str(raw_file)):
        raise RuntimeError("Arcads v1 generated but no downloadable URL was returned")
    build_hard_cut(raw_file, final_file, walkthru_path, cuts, offsets)
    print(f"DONE {final_file} size_bytes={final_file.stat().st_size}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
