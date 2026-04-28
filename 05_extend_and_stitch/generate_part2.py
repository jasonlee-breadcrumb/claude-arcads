import os, sys, subprocess
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from arcads_client import upload_file, generate_video, poll, download, next_version, get_ffmpeg

FFMPEG = get_ffmpeg()
ASSETS = os.path.join(os.path.dirname(__file__), "assets")
OUT    = os.path.join(ASSETS, "outputs")
os.makedirs(OUT, exist_ok=True)

# ── SETUP ─────────────────────────────────────────────────────
# Point this at the existing part 1 video you want to extend.
# Claude Code will use it as the reference (v2v) to match the same character and setting.
PART1_VIDEO = "assets/part1.mp4"

# ── EDIT YOUR PROMPT BELOW ────────────────────────────────────
# This should continue where part 1 left off.
# Claude Code will write a part 2 script focused on product details, benefits, and CTA.
PROMPT = """
REPLACE THIS WITH YOUR PART 2 PROMPT.
Claude Code will write this for you based on the part 1 video and what you want to add.
"""
# ─────────────────────────────────────────────────────────────

SCALE = "scale=720:1280:force_original_aspect_ratio=decrease,pad=720:1280:(ow-iw)/2:(oh-ih)/2"

def main():
    part1_path = os.path.join(os.path.dirname(__file__), PART1_VIDEO)
    v = next_version(OUT, "part2")
    part2_file = os.path.join(OUT, f"part2_v{v}.mp4")
    final_file = os.path.join(OUT, f"extended_v{v}.mp4")

    print("Uploading part 1 as reference (v2v)...", flush=True)
    ref_path = upload_file(part1_path, "video/mp4")

    print(f"\n=== Generating part 2 (15s v2v) ===", flush=True)
    clip_id, credits = generate_video(PROMPT, duration=15, ref_videos=[ref_path])

    clip_data = poll(clip_id, "Part2")
    if not download(clip_data, part2_file):
        print("Generation failed.")
        exit(1)

    print("\n=== Stitching part 1 + part 2 ===", flush=True)
    norm1 = os.path.join(OUT, "tmp_norm1.mp4")
    norm2 = os.path.join(OUT, "tmp_norm2.mp4")
    concat_txt = os.path.join(OUT, "tmp_concat.txt")

    subprocess.run([FFMPEG, "-i", part1_path, "-vf", SCALE, "-c:v", "libx264", "-c:a", "aac", "-r", "30", "-y", norm1], capture_output=True)
    subprocess.run([FFMPEG, "-i", part2_file,  "-vf", SCALE, "-c:v", "libx264", "-c:a", "aac", "-r", "30", "-y", norm2], capture_output=True)

    with open(concat_txt, "w") as f:
        f.write(f"file '{norm1}'\nfile '{norm2}'\n")

    subprocess.run([FFMPEG, "-f", "concat", "-safe", "0", "-i", concat_txt, "-c:v", "libx264", "-c:a", "aac", "-y", final_file], capture_output=True)

    for f in [norm1, norm2, concat_txt]:
        try: os.remove(f)
        except: pass

    print(f"\nDONE. Extended video: {final_file} ({os.path.getsize(final_file)//1024}KB)", flush=True)

if __name__ == "__main__":
    main()
