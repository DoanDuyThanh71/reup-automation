---
name: reup-video-automation
description: >-
  Use this skill whenever the user wants to download/reup a Douyin or TikTok video,
  extract & translate Vietnamese subtitles using Gemini Video Vision, dub with Vbee,
  generate Shopee Affiliate links (Kênh 71 / Affiliate ID 17374600599), publish to
  Facebook Reels (Kênh 71) or TikTok (@tra_sua_nuong_71), manage AI/Gemini token pools,
  or check cross-channel video analytics with minimal token consumption.
---

# Reup Video Automation & Multi-Channel Analytics Skill (Zero-Bloat Runner)

To save tokens, **DO NOT** read source files across `app/` unless debugging a code bug. Execute `reup_cli.py` directly.

## 1. One-Click Full Video Pipeline (Send Link -> Done)
Downloads video, runs **Gemini Multimodal Video Viewing** (watches frames + hardsubs + audio -> Vietnamese SRT + Shopee product), dubs 48kHz Vbee voice, renders with anti-duplicate video fingerprint, and publishes to Facebook (`Kênh 71`) & TikTok (`@tra_sua_nuong_71`):
```powershell
python "d:\RepoGithub\reup-automation\reup_cli.py" run "<VIDEO_URL>"
```
- Optional flags: `--hint "tên sản phẩm"`, `--no-fb`, `--no-tt`.

## 2. Gemini Direct Video Subtitle & Product Detection Only
```powershell
python "d:\RepoGithub\reup-automation\reup_cli.py" sub-test "<VIDEO_PATH_OR_URL>"
```

## 3. Publish an Existing MP4 or Job ID to Facebook & TikTok
```powershell
python "d:\RepoGithub\reup-automation\reup_cli.py" publish "<MP4_PATH_OR_JOB_ID>" --title "TIÊU ĐỀ" --caption "Mô tả" --fb --tt
```

## 4. Check Live Analytics & Tracking (Facebook Views/Likes, TikTok Followers, Shopee, Quota Pool)
```powershell
python "d:\RepoGithub\reup-automation\reup_cli.py" analytics
```

## 5. Verify Accounts, Security Fingerprints & Add API Keys to Pool
```powershell
python "d:\RepoGithub\reup-automation\reup_cli.py" verify-all
python "d:\RepoGithub\reup-automation\reup_cli.py" add-key "<GEMINI_OR_GATEWAY_KEY>"
```
- Secrets are encrypted at rest in SQLite (`ENC:v1:...`) and displayed only as `fp:<sha256_12>`. Never print raw cookies or tokens in chat.
