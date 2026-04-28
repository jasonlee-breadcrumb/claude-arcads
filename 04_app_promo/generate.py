import os, sys, subprocess
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from arcads_client import upload_file, generate_video, poll, download, next_version, get_ffmpeg

FFMPEG = get_ffmpeg()
ASSETS = os.path.join(os.path.dirname(__file__), "assets")
OUT    = os.path.join(ASSETS, "outputs")
os.makedirs(OUT, exist_ok=True)

# ── EDIT YOUR PROMPT BELOW ────────────────────────────────────
PROMPT = """
REPLACE THIS WITH YOUR PROMPT.
Claude Code will write this for you based on your reference ad and app assets.
"""
# ─────────────────────────────────────────────────────────────

# Drop your assets in assets/ and update these filenames
REF_IMAGE = "assets/ref.jpg"          # style reference image (extract from winning ad)
WALKTHRU  = "assets/walkthru.MP4"     # screen recording of the app being used

# Hard cut edit structure (seconds):
CUT1_START, CUT1_END = 4, 6    # first cut to app walkthru
CUT2_START, CUT2_END = 10, 12  # second cut to app walkthru

# Which part of the walkthru to show at each cut (seconds into walkthru video)
WALKTHRU_CUT1_AT = 2   # show walkthru starting from this timestamp
WALKTHRU_CUT2_AT = 12  # show walkthru starting from this timestamp

def main():
    v = next_version(OUT, "app_promo")
    seedance_file = os.path.join(OUT, f"app_seedance_v{v}.mp4")
    final_file    = os.path.join(OUT, f"app_promo_v{v}.mp4")

    print("Uploading reference image...", flush=True)
    ref_path = upload_file(os.path.join(os.path.dirname(__file__), REF_IMAGE), "image/jpeg")

    print(f"\n=== Generating influencer clip (15s) ===", flush=True)
    clip_id, credits = generate_video(PROMPT, duration=15, ref_images=[ref_path])

    clip_data = poll(clip_id, "AppPromo")
    if not download(clip_data, seedance_file):
        print("Generation failed.")
        exit(1)

    # Build final with hard cuts to app walkthru
    print("\n=== Building composite with hard cuts ===", flush=True)
    walkthru_path = os.path.join(os.path.dirname(__file__), WALKTHRU)
    SCALE = "scale=720:1280:force_original_aspect_ratio=decrease,pad=720:1280:(ow-iw)/2:(oh-ih)/2:color=#0d0d0d"

    tmp = {k: os.path.join(OUT, f"tmp_{k}.mp4") for k in ["v1","v2","v3","v4","v5","aud","vid"]}
    concat_txt = os.path.join(OUT, "tmp_concat.txt")

    subprocess.run([FFMPEG, "-i", seedance_file, "-vn", "-c:a", "aac", "-y", tmp["aud"]], capture_output=True)

    segments = [
        (["-i", seedance_file, "-t", str(CUT1_START)], tmp["v1"]),
        (["-ss", str(WALKTHRU_CUT1_AT), "-t", str(CUT1_END - CUT1_START), "-i", walkthru_path], tmp["v2"]),
        (["-ss", str(CUT1_END), "-t", str(CUT2_START - CUT1_END), "-i", seedance_file], tmp["v3"]),
        (["-ss", str(WALKTHRU_CUT2_AT), "-t", str(CUT2_END - CUT2_START), "-i", walkthru_path], tmp["v4"]),
        (["-ss", str(CUT2_END), "-i", seedance_file], tmp["v5"]),
    ]

    for args, out in segments:
        subprocess.run([FFMPEG] + args + ["-vf", SCALE, "-c:v", "libx264", "-r", "30", "-an", "-y", out], capture_output=True)

    with open(concat_txt, "w") as f:
        for _, seg in segments:
            f.write(f"file '{seg}'\n")

    subprocess.run([FFMPEG, "-f", "concat", "-safe", "0", "-i", concat_txt, "-c:v", "libx264", "-an", "-y", tmp["vid"]], capture_output=True)
    subprocess.run([FFMPEG, "-i", tmp["vid"], "-i", tmp["aud"], "-c:v", "copy", "-c:a", "aac", "-shortest", "-y", final_file], capture_output=True)

    for f in list(tmp.values()) + [concat_txt]:
        try: os.remove(f)
        except: pass

    print(f"\nDONE. {final_file} ({os.path.getsize(final_file)//1024}KB)", flush=True)

if __name__ == "__main__":
    main()
