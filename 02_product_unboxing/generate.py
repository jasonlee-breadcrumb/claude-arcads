import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from arcads_client import upload_file, generate_video, poll, download, next_version

ASSETS = os.path.join(os.path.dirname(__file__), "assets")
OUT    = os.path.join(ASSETS, "outputs")
os.makedirs(OUT, exist_ok=True)

# ── EDIT YOUR PROMPT BELOW ────────────────────────────────────
PROMPT = """
REPLACE THIS WITH YOUR PROMPT.
Claude Code will write this for you based on your reference ad and product assets.
"""
# ─────────────────────────────────────────────────────────────

# Drop your images in assets/ and update these filenames
BOX_IMAGE     = "assets/box.jpg"      # packaging / box image
PRODUCT_IMAGE = "assets/product.jpg"  # the product itself

def main():
    v = next_version(OUT, "unboxing")
    out_file = os.path.join(OUT, f"unboxing_v{v}.mp4")

    print("Uploading assets...", flush=True)
    box_path     = upload_file(os.path.join(os.path.dirname(__file__), BOX_IMAGE), "image/jpeg")
    product_path = upload_file(os.path.join(os.path.dirname(__file__), PRODUCT_IMAGE), "image/jpeg")
    print(f"  Box: {box_path}\n  Product: {product_path}", flush=True)

    print(f"\n=== Generating unboxing clip (15s) ===", flush=True)
    clip_id, credits = generate_video(PROMPT, duration=15, ref_images=[box_path, product_path])

    clip_data = poll(clip_id, "Unboxing")
    if not download(clip_data, out_file):
        print("Generation failed.")
        exit(1)

    print(f"\nDONE. {out_file}", flush=True)

if __name__ == "__main__":
    main()
