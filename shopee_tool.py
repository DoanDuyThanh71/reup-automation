"""
CLI & Tiện ích kết nối Shopee Affiliate bằng Cookie (hỗ trợ JSON Cookie-Editor & Header String).

Cách dùng:
  1. Kiểm tra trạng thái Cookie & thông tin tài khoản Affiliate:
     python shopee_tool.py --check

  2. Tìm sản phẩm theo từ khóa và tạo link Affiliate:
     python shopee_tool.py "quạt tích điện cầm tay mini"

  3. Chuyển đổi trực tiếp một link Shopee bất kỳ sang link Affiliate chuẩn hoa hồng:
     python shopee_tool.py "https://shopee.vn/San-pham-i.123456.789012" --sub kenh71_reel01
"""
import sys
import json
import argparse
from app.services.shopee_client import ShopeeAffiliateClient


BROWSER_CONSOLE_SNIPPET = """
// Dán đoạn này vào F12 -> Console khi đang mở https://affiliate.shopee.vn để lấy link rút gọn s.shopee.vn/xxxx hàng loạt:
async function taoLinkRutGonShopee(urls, subId1 = "kenh71") {
  const csrf = (document.cookie.match(/csrftoken=([^;]+)/) || [])[1] || "";
  const res = await fetch("https://affiliate.shopee.vn/api/v3/gql?q=batchCustomLink", {
    method: "POST",
    headers: { "Content-Type": "application/json", "csrf-token": csrf, "affiliate-program-type": "1" },
    body: JSON.stringify({
      operationName: "batchGetCustomLink",
      query: "query batchGetCustomLink($linkParams: [CustomLinkParam!], $sourceCaller: SourceCaller){ batchCustomLink(linkParams: $linkParams, sourceCaller: $sourceCaller){ shortLink longLink failCode } }",
      variables: {
        linkParams: urls.map(u => ({
          originalUrl: u,
          advancedLinkParams: { subId1, subId2: "", subId3: "", subId4: "", subId5: "" }
        })),
        sourceCaller: "CUSTOM_LINK_CALLER"
      }
    })
  });
  const data = await res.json();
  console.table((data.data || {}).batchCustomLink || data);
  return (data.data || {}).batchCustomLink;
}
// Ví dụ gọi: await taoLinkRutGonShopee(["https://shopee.vn/search?keyword=quat+mini"], "kenh71");
""".strip()


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Công cụ kết nối & tạo link Shopee Affiliate")
    parser.add_argument("query", nargs="?", help="Từ khóa sản phẩm hoặc URL Shopee gốc")
    parser.add_argument("--check", action="store_true", help="Kiểm tra phiên đăng nhập Cookie và tài khoản Affiliate")
    parser.add_argument("--sub", default=None, help="Sub-ID theo dõi chiến dịch (VD: kenh71, fb_reel_01)")
    parser.add_argument("--browser-js", action="store_true", help="In mã JS chạy trên F12 Console affiliate.shopee.vn để tạo shortlink s.shopee.vn/xxxx")
    args = parser.parse_args()

    if args.browser_js:
        print(BROWSER_CONSOLE_SNIPPET)
        return

    client = ShopeeAffiliateClient(sub_id=args.sub)

    if args.check or not args.query:
        res = client.test_connection()
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return

    target = args.query.strip()
    origin_url = target if target.startswith(("http://", "https://")) else client.search_product(target)
    aff_link = client.convert_to_affiliate_link(origin_url, campaign_tag=args.sub or "cli")
    verify = client.verify_affiliate_link(aff_link, product_keyword=target, live_check=True)

    output = {
        "input": target,
        "origin_url": origin_url,
        "affiliate_id": client.affiliate_id,
        "sub_id": client.sub_id,
        "affiliate_link": aff_link,
        "shopee_301_redirect": verify.get("resolved_location"),
        "valid": verify.get("valid"),
        "method": verify.get("method"),
    }
    print(json.dumps(output, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
