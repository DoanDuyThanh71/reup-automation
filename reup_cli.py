"""
Reup Automation One-Command CLI (Low-Token AI Skill Runner & User Automation Tool).

Các lệnh chính:
  1. Chạy toàn trình 1-Click từ link video (Gemini xem video dịch Sub + Vbee + Shopee + Đăng FB & TikTok):
     python reup_cli.py run "https://v.douyin.com/..."
  2. Test riêng tính năng Gemini xem video & tách dịch SRT tiếng Việt:
     python reup_cli.py sub-test "outputs/multi-vid01/source_video.mp4"
  3. Đăng thử 1 video có sẵn lên cả Facebook (Kênh 71) và TikTok (@tra_sua_nuong_71):
     python reup_cli.py publish "outputs/multi-vid01/final_multi-vid01.mp4" --title "..." --caption "..." --fb --tt
  4. Xem thống kê theo dõi đa kênh (Views/Likes Facebook, Followers TikTok, Shopee Affiliate, Pool Token):
     python reup_cli.py analytics
  5. Kiểm tra toàn bộ kết nối & vân tay bảo mật:
     python reup_cli.py verify-all
  6. Thêm nhanh API Key vào Pool xoay vòng:
     python reup_cli.py add-key "AIzaSy..."
"""
import os
import sys
import uuid
import json
import argparse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app.database import SessionLocal, Base, engine
from app.models import JobModel
from app.config import config
from app.agents.orchestrator import orchestrator
from app.services.gemini_video_client import GeminiVideoAnalyzer
from app.services.facebook_client import FacebookPublisher
from app.services.tiktok_client import TikTokClient
from app.services.shopee_client import ShopeeAffiliateClient
from app.services.vbee_client import VbeeClient
from app.services.quota_pool import QuotaPoolManager
from app.services.analytics_service import AnalyticsService


def _print_json(obj):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(obj, indent=2, ensure_ascii=False))


def cmd_verify_all():
    fb = FacebookPublisher(
        page_id=config.get("FACEBOOK_PAGE_ID"),
        page_access_token=config.get("FACEBOOK_PAGE_ACCESS_TOKEN"),
    ).test_connection()
    tt = TikTokClient().verify_account()
    sh = ShopeeAffiliateClient().test_connection()
    vb = VbeeClient().test_connection()
    qp = QuotaPoolManager.detect_local_quota_gateways()
    _print_json({
        "facebook": fb,
        "tiktok": tt,
        "shopee": {
            "success": sh.get("success"),
            "affiliate_id": sh.get("affiliate_id"),
            "sub_id": sh.get("sub_id"),
            "username": (sh.get("profile") or {}).get("shopee_user_name"),
            "sample_link": sh.get("sample_link"),
        },
        "vbee": vb,
        "quota_pool": {
            "total_keys": qp["total_keys"],
            "healthy_keys": qp["healthy_keys"],
            "providers": qp["providers"],
        },
    })


def cmd_analytics():
    db = SessionLocal()
    try:
        data = AnalyticsService().collect_dashboard_analytics(db)
        _print_json(data)
    finally:
        db.close()


def cmd_sub_test(video_input: str, hint: str = ""):
    work_dir = os.path.join(BASE_DIR, "temp", "sub_test")
    os.makedirs(work_dir, exist_ok=True)
    if video_input.startswith(("http://", "https://")):
        local_vid = os.path.join(work_dir, "source_test.mp4")
        orchestrator.ingestion_agent.run(video_input, local_vid)
    else:
        local_vid = os.path.abspath(video_input)

    analyzer = GeminiVideoAnalyzer()
    res = analyzer.analyze_and_translate_video(local_vid, work_dir=work_dir, product_hint=hint)
    if not res:
        _print_json({"success": False, "error": "Không gọi được Gemini Multimodal, hãy kiểm tra Pool Key."})
        sys.exit(1)

    srt_file = os.path.join(work_dir, "gemini_vietnamese.srt")
    with open(srt_file, "w", encoding="utf-8") as f:
        f.write(res["vietnamese_srt"])
    res["saved_srt_path"] = srt_file
    res["success"] = True
    _print_json(res)


def cmd_run_pipeline(url: str, hint: str = "", post_fb: bool = True, post_tt: bool = True):
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    job_id = str(uuid.uuid4())[:10]
    try:
        new_job = JobModel(
            id=job_id,
            source_url=url.strip(),
            status="PENDING",
            current_stage="Khởi tạo từ CLI 1-Click",
            progress=0,
        )
        db.add(new_job)
        db.commit()
    finally:
        db.close()

    orchestrator.execute_pipeline(
        job_id=job_id,
        custom_product_hint=hint or None,
        auto_post_fb=post_fb,
        auto_post_tt=post_tt,
    )

    db = SessionLocal()
    try:
        finished = db.query(JobModel).filter(JobModel.id == job_id).first()
        _print_json(finished.to_dict() if finished else {"error": "Job not found"})
    finally:
        db.close()


def cmd_publish(video_or_job: str, title: str, caption: str, hashtags: str, do_fb: bool, do_tt: bool):
    db = SessionLocal()
    job = None
    try:
        if not os.path.exists(video_or_job):
            job = db.query(JobModel).filter(JobModel.id == video_or_job).first()
            if not job or not job.output_video_path:
                _print_json({"success": False, "error": f"Không tìm thấy file hoặc Job ID: {video_or_job}"})
                sys.exit(1)
            video_path = job.output_video_path
            title = title or job.title or "Video Xu Hướng"
            caption = caption or job.caption or ""
            hashtags = hashtags or job.hashtags or "#Kenh71 #review #xuhuong"
            aff_link = job.affiliate_link or ""
        else:
            video_path = os.path.abspath(video_or_job)
            sh = ShopeeAffiliateClient()
            aff_link = sh.convert_to_affiliate_link(sh.search_product(title or "đồ gia dụng thông minh"), campaign_tag="cli_pub")

        out = {"video_path": video_path, "affiliate_link": aff_link}
        if do_fb:
            fb_res = orchestrator.publisher_agent.publish_to_facebook(
                video_path=video_path,
                title=title or "Video Review Kênh 71",
                caption=caption or title or "Xem đến cuối video để không bỏ lỡ nhé!",
                hashtags=hashtags or "#Kenh71 #review #xuhuong #reels",
                affiliate_link=aff_link,
            )
            out["facebook"] = fb_res
            if job and fb_res.get("success"):
                job.published_facebook = True
                job.facebook_post_id = str(fb_res.get("post_id", ""))
                db.commit()

        if do_tt:
            tt_res = orchestrator.publisher_agent.publish_to_tiktok(
                video_path=video_path,
                title=title or "",
                caption=caption or "Xem hết video nhé cả nhà!",
                hashtags=hashtags or "#Kenh71 #xuhuong #review",
            )
            out["tiktok"] = tt_res
            if job and tt_res.get("success"):
                job.published_tiktok = True
                job.tiktok_post_id = str(tt_res.get("post_id", ""))
                db.commit()

        _print_json(out)
    finally:
        db.close()


def cmd_add_key(new_key: str):
    from app.services.quota_pool import is_google_native_key
    k = new_key.strip()
    if not k:
        return
    if is_google_native_key(k):
        cur = config.get("GEMINI_API_KEYS", "")
        keys = [x.strip() for x in cur.splitlines() if x.strip()]
        if k not in keys:
            keys.append(k)
            config.set("GEMINI_API_KEYS", "\n".join(keys))
    else:
        cur = config.get("AI_KEY_POOL", "")
        keys = [x.strip() for x in cur.splitlines() if x.strip()]
        if k not in keys:
            keys.append(k)
            config.set("AI_KEY_POOL", "\n".join(keys))
    _print_json(QuotaPoolManager.detect_local_quota_gateways())


def main():
    parser = argparse.ArgumentParser(description="Reup Automation 1-Command CLI")
    sub = parser.add_subparsers(dest="cmd")

    p_run = sub.add_parser("run", help="Chạy 1-Click toàn trình từ link video")
    p_run.add_argument("url")
    p_run.add_argument("--hint", default="")
    p_run.add_argument("--no-fb", action="store_true")
    p_run.add_argument("--no-tt", action="store_true")

    p_sub = sub.add_parser("sub-test", help="Gemini xem video & tách dịch SRT")
    p_sub.add_argument("video")
    p_sub.add_argument("--hint", default="")

    p_pub = sub.add_parser("publish", help="Đăng video lên Facebook & TikTok")
    p_pub.add_argument("target", help="Đường dẫn file MP4 hoặc Job ID")
    p_pub.add_argument("--title", default="")
    p_pub.add_argument("--caption", default="")
    p_pub.add_argument("--hashtags", default="#Kenh71 #review #xuhuong #trending")
    p_pub.add_argument("--fb", action="store_true")
    p_pub.add_argument("--tt", action="store_true")

    sub.add_parser("analytics", help="Xem báo cáo thống kê Facebook, TikTok, Shopee, Token Pool")
    sub.add_parser("verify-all", help="Kiểm tra toàn bộ kết nối & vân tay bảo mật")
    sub.add_parser("hw-check", help="Quét thông số máy & gợi ý cấu hình Voice Local")
    sub.add_parser("install-local-voice", help="Tự động tải & cài đặt bộ Giọng Local Tiếng Việt (64MB)")

    p_key = sub.add_parser("add-key", help="Thêm API key vào Pool xoay vòng")
    p_key.add_argument("key")

    args = parser.parse_args()
    if args.cmd == "verify-all":
        cmd_verify_all()
    elif args.cmd == "analytics":
        cmd_analytics()
    elif args.cmd == "sub-test":
        cmd_sub_test(args.video, hint=args.hint)
    elif args.cmd == "run":
        cmd_run_pipeline(args.url, hint=args.hint, post_fb=not args.no_fb, post_tt=not args.no_tt)
    elif args.cmd == "publish":
        do_fb = args.fb or (not args.fb and not args.tt)
        do_tt = args.tt or (not args.fb and not args.tt)
        cmd_publish(args.target, args.title, args.caption, args.hashtags, do_fb, do_tt)
    elif args.cmd == "add-key":
        cmd_add_key(args.key)
    elif args.cmd == "hw-check":
        from app.services.hardware_advisor import HardwareAdvisor
        _print_json(HardwareAdvisor.inspect_and_recommend())
    elif args.cmd == "install-local-voice":
        from app.services.local_tts_client import LocalTTSClient
        _print_json(LocalTTSClient.install_sherpa_vietnamese())
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
