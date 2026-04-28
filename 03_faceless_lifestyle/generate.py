import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from arcads_client import upload_file, generate_video, poll, download, next_version

ASSETS = os.path.join(os.path.dirname(__file__), "assets")
OUT    = os.path.join(ASSETS, "outputs")
os.makedirs(OUT, exist_ok=True)

# ── EDIT YOUR PROMPT BELOW ────────────────────────────────────
# Note: avoid bare legs, shorts, or bodycon clothing -- triggers content moderation.
# Use "light linen wide-leg trousers" or similar covered clothing.
PROMPT = """
REPLACE THIS WITH YOUR PROMPT.
Claude Code will write this for you based on your reference ad and product assets.
"""
# ─────────────────────────────────────────────────────────────

# Reference frames extracted from the winning ad (use ffmpeg or screenshot tool)
# Claude Code will extract these from your reference video automatically.
REF_WIDE    = "assets/ref_wide.jpg"    # wide shot showing the setting
REF_DETAIL  = "assets/ref_detail.jpg"  # close-up / angle reference
PRODUCT_IMG = "assets/product.jpg"     # your product

def main():
    v = next_version(OUT, "faceless")
    out_file = os.path.join(OUT, f"faceless_v{v}.mp4")

    print("Uploading reference frames and product...", flush=True)
    wide_path    = upload_file(os.path.join(os.path.dirname(__file__), REF_WIDE), "image/jpeg")
    detail_path  = upload_file(os.path.join(os.path.dirname(__file__), REF_DETAIL), "image/jpeg")
    product_path = upload_file(os.path.join(os.path.dirname(__file__), PRODUCT_IMG), "image/jpeg")

    print(f"\n=== Generating faceless clip (15s) ===", flush=True)
    clip_id, credits = generate_video(
        PROMPT, duration=15,
        ref_images=[wide_path, detail_path, product_path]
    )

    clip_data = poll(clip_id, "Faceless")
    if not download(clip_data, out_file):
        print("Generation failed. If output is 0KB, check clothing description for moderation issues.")
        exit(1)

    print(f"\nDONE. {out_file}", flush=True)

if __name__ == "__main__":
    main()
