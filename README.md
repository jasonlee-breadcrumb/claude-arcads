# claude-arcads

Clone winning UGC ads with your own assets using Claude Code and the Arcads Seedance 2.0 API.

Find an ad that's performing in your niche. Drop in your product. Get a clone in under 10 minutes.

---

## How It Works

**You don't write prompts. Claude Code does.**

1. Find a winning ad (TikTok Ad Library, Meta Ad Library, competitor research)
2. Drop the reference video/image + your product assets into the template folder
3. Tell Claude Code: *"Clone this ad with my product"*
4. Claude Code analyzes the reference -- extracts the script, setting, character, and beat structure
5. Claude Code writes the adapted prompt for your product and shows it to you
6. You approve it, Claude Code runs the generation
7. Video lands in `outputs/` in ~5-10 minutes

---

## Prerequisites

- [Claude Code](https://claude.ai/code) (the CLI or desktop app)
- Python 3.8+
- An Arcads API key ([get one at arcads.ai](https://arcads.ai))

---

## Setup

**Clone this repo as a standalone folder** (not inside another project):

```bash
git clone https://github.com/jasonlee-breadcrumb/claude-arcads
cd claude-arcads
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Add your API credentials:

```bash
cp .env.example .env
# Edit .env and add your ARCADS_KEY and ARCADS_PRODUCT_ID
```

Open Claude Code in this folder and you're ready.

---

## Finding Winning Ads

- **TikTok Ad Library:** [library.tiktok.com](https://library.tiktok.com) — filter by industry, sort by impressions
- **Meta Ad Library:** [facebook.com/ads/library](https://facebook.com/ads/library) — search competitors or keywords
- Look for ads that have been running for 30+ days — if they're still spending, they're working

---

## The 5 Clone Types

### 01 — Talking Head
An influencer speaks directly to camera about a product. Selfie-style, bedroom or outdoor setting.

```
Drop your reference image in: 01_talking_head/assets/
Tell Claude Code: "Clone this talking head ad with my product [X]"
```

### 02 — Product Unboxing
Creator opens packaging and reacts to the product. Great for physical products with distinctive packaging.

```
Drop in: box image + product image → 02_product_unboxing/assets/
Tell Claude Code: "Clone this unboxing ad with my product"
```

### 03 — Faceless Lifestyle
Aesthetic shots with no face — hands, feet, and product. Lower moderation risk. Works for beauty, fashion, wellness.

```
Drop in: reference frames + product image → 03_faceless_lifestyle/assets/
Tell Claude Code: "Clone this faceless lifestyle ad with my product"
```

### 04 — App Promo
Influencer talks about an app + shows it on their phone. Includes hard cuts between the influencer and live app footage.

```
Drop in: style reference + app screen recording → 04_app_promo/assets/
Tell Claude Code: "Clone this app promo with my app"
```

### 05 — Extend and Stitch
Take a generated 15-second clip and extend it to 30 seconds. Part 2 goes deeper on product details and benefits. Both clips are stitched with continuous audio.

```
Drop your existing part 1 video in: 05_extend_and_stitch/assets/part1.mp4
Tell Claude Code: "Extend this video with a part 2 focused on [product detail]"
```

---

## Important

- Clone this repo into its own standalone folder -- not inside another project
- Never commit your `.env` file -- it's already in `.gitignore`
- Outputs are automatically versioned (v1, v2, v3...) and never overwritten
- Claude Code writes every prompt -- you only approve or adjust

---

## Built with

Made by [@JasonLeeFinance](https://youtube.com/@JasonLeeFinance) in collaboration with Claude.
