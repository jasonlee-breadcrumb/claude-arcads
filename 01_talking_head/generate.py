import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from arcads_client import upload_file, generate_video, poll, download, next_version

ASSETS = os.path.join(os.path.dirname(__file__), "assets")
OUT    = os.path.join(ASSETS, "outputs")
os.makedirs(OUT, exist_ok=True)

# ── EDIT YOUR PROMPT BELOW ────────────────────────────────────
# Claude Code will update this based on your reference ad and product.
PROMPT = """
REPLACE THIS WITH YOUR PROMPT.
Claude Code will write this for you based on your reference ad and product assets.
"""
# ─────────────────────────────────────────────────────────────

# Reference image (optional -- drop a style reference in assets/)
# Set to None for text-to-video (no reference image)
REF_IMAGE = None  # e.g. "assets/ref.jpg"

def main():
    v = next_version(OUT, "talking_head")
    out_file = os.path.join(OUT, f"talking_head_v{v}.mp4")

    ref_paths = []
    if REF_IMAGE:
        ref_path = os.path.join(os.path.dirname(__file__), REF_IMAGE)
        print("Uploading reference image...", flush=True)
        ref_paths.append(upload_file(ref_path, "image/jpeg"))

    print(f"\n=== Generating talking head clip (15s) ===", flush=True)
    clip_id, credits = generate_video(PROMPT, duration=15, ref_images=ref_paths or None)

    clip_data = poll(clip_id, "TalkingHead")
    if not download(clip_data, out_file):
        print("Generation failed.")
        exit(1)

    print(f"\nDONE. {out_file}", flush=True)

if __name__ == "__main__":
    main()
