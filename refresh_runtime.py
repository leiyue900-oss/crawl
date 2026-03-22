import json
import time
import re
import random
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


# =========================================================
# 1. 配置区
# =========================================================
CITY_EN_NAME = "Nanning"
CITY_ID = 380

# 自动从今天开始
TODAY = datetime.now().date()
CHECK_IN = TODAY.strftime("%Y-%m-%d")
CHECK_OUT = (TODAY + timedelta(days=1)).strftime("%Y-%m-%d")

OUTPUT_JSON = "ctrip_runtime_config.json"

# 第一次建议 False，方便观察页面
HEADLESS = False

# 等待页面发请求的时间
LIST_PAGE_WAIT_SECONDS = random.randint(20, 50)
DETAIL_PAGE_WAIT_SECONDS = 70


# =========================================================
# 2. 自动生成地区列表页 URL
# =========================================================
REGION_LIST_URL = (
    f"https://hotels.ctrip.com/hotels/list"
    f"?city={CITY_EN_NAME}"
    f"&cityId={CITY_ID}"
    f"&checkin={CHECK_IN}"
    f"&checkout={CHECK_OUT}"
)


# =========================================================
# 3. 工具函数
# =========================================================
def safe_json_loads(text: Optional[str]) -> Dict[str, Any]:
    if not text or not isinstance(text, str):
        return {}
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def normalize_string(v: Any) -> str:
    if v is None:
        return ""
    return str(v).strip().replace("\r", "").replace("\n", "")


def write_runtime_config(path: str, runtime: Dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(runtime, f, ensure_ascii=False, indent=2)


def build_hotel_detail_url(
    city_en_name: str,
    city_id: int,
    hotel_id: str,
    check_in: str,
    check_out: str
) -> str:
    return (
        f"https://hotels.ctrip.com/hotels/detail/"
        f"?cityEnName={city_en_name}"
        f"&cityId={city_id}"
        f"&hotelId={hotel_id}"
        f"&checkIn={check_in}"
        f"&checkOut={check_out}"
        f"&adult=1"
        f"&children=0"
        f"&crn=1"
        f"&curr=CNY"
        f"&barcurr=CNY"
    )


# =========================================================
# 4. 主逻辑
# =========================================================
def main() -> None:
    runtime: Dict[str, Any] = {
        "cookie": "",
        "phantom_token": "",
        #"calendar_wclient_req": "",
        "room_wclient_req": "",
        "cid": "",
        "sid": "",
        "vid": "",
        "page_id": "",
        "aid": "",
        "list_api_url": "",
        "price_calendar_url": "",
        "room_list_url": "",
        "seed_hotel_id": "",
        "seed_hotel_name": "",
        "seed_hotel_detail_url": "",
        "city_en_name": CITY_EN_NAME,
        "city_id": str(CITY_ID),
        "check_in": CHECK_IN,
        "check_out": CHECK_OUT,
        "region_list_url": REGION_LIST_URL,
        "refreshed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    captured_requests = {
        "getAdHotels": 0,
        "ctGetHotelPriceCalendar": 0,
        "getHotelRoomListInland": 0,
    }

    state: Dict[str, Any] = {
        "seed_hotel_id": "",
        "seed_hotel_name": "",
        "got_list_api_response": False,
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        context = p.chromium.launch_persistent_context(
            user_data_dir="playwright_ctrip_profile",
            headless=HEADLESS
            )
        page = context.new_page()

        # -------------------------------------------------
        # 1) 监听 request：抓 headers / payload 里的动态参数
        # -------------------------------------------------
        def handle_request(request) -> None:
            url = request.url or ""
            headers = request.headers or {}
            post_data = request.post_data

            # 地区酒店列表接口
            if "getAdHotels" in url:
                captured_requests["getAdHotels"] += 1
                runtime["list_api_url"] = url.split("?")[0]

            # 最低价日历接口
            if "ctGetHotelPriceCalendar" in url:
                captured_requests["ctGetHotelPriceCalendar"] += 1
                runtime["price_calendar_url"] = url.split("?")[0]
                runtime["phantom_token"] = headers.get("phantom-token", runtime["phantom_token"])
                runtime["calendar_wclient_req"] = headers.get("x-ctx-wclient-req", runtime["calendar_wclient_req"])

                body = safe_json_loads(post_data)
                head = body.get("head", {}) if isinstance(body, dict) else {}

                runtime["cid"] = head.get("cid", runtime["cid"])
                runtime["sid"] = head.get("sid", runtime["sid"])
                runtime["vid"] = head.get("vid", runtime["vid"])
                runtime["page_id"] = head.get("pageId", runtime["page_id"])
                runtime["aid"] = head.get("aid", runtime["aid"])

            # 房型列表接口
            if "getHotelRoomListInland" in url:
                captured_requests["getHotelRoomListInland"] += 1
                runtime["room_list_url"] = url.split("?")[0]
                runtime["phantom_token"] = headers.get("phantom-token", runtime["phantom_token"])
                runtime["room_wclient_req"] = headers.get("x-ctx-wclient-req", runtime["room_wclient_req"])

                body = safe_json_loads(post_data)
                head = body.get("head", {}) if isinstance(body, dict) else {}

                runtime["cid"] = head.get("cid", runtime["cid"])
                runtime["sid"] = head.get("sid", runtime["sid"])
                runtime["vid"] = head.get("vid", runtime["vid"])
                runtime["page_id"] = head.get("pageId", runtime["page_id"])
                runtime["aid"] = head.get("aid", runtime["aid"])

        # -------------------------------------------------
        # 2) 监听 response：从 getAdHotels 响应里自动选代表酒店
        # -------------------------------------------------
        def handle_response(response) -> None:
            url = response.url or ""

            if "getAdHotels" not in url:
                return

            try:
                data = response.json()
            except Exception:
                return

            if not isinstance(data, dict):
                return

            state["got_list_api_response"] = True

            ad_list = data.get("data", {}).get("adList", []) or []
            for block in ad_list:
                hotels = block.get("hotels", []) or []
                for hotel in hotels:
                    base = hotel.get("base", {}) or {}
                    hotel_id = base.get("hotelId")
                    hotel_name = base.get("hotelName")
                    if hotel_id:
                        state["seed_hotel_id"] = str(hotel_id)
                        state["seed_hotel_name"] = normalize_string(hotel_name)
                        return

        page.on("request", handle_request)
        page.on("response", handle_response)

        # -------------------------------------------------
        # 3) 打开地区列表页
        # -------------------------------------------------
        print("[INFO] 打开地区酒店列表页...")
        print("[INFO] REGION_LIST_URL =", REGION_LIST_URL)

        try:
            page.goto(REGION_LIST_URL, wait_until="domcontentloaded", timeout=60000)
        except PlaywrightTimeoutError:
            print("[WARN] 列表页加载超时，继续等待网络请求...")

        print(f"[INFO] 等待 {LIST_PAGE_WAIT_SECONDS} 秒收集列表页请求...")
        time.sleep(LIST_PAGE_WAIT_SECONDS)

        # 轻微滚动，帮助触发更多请求
        try:
            page.mouse.wheel(0, 1200)
            time.sleep(2)
            page.mouse.wheel(0, 1600)
            time.sleep(2)
        except Exception:
            pass

        # -------------------------------------------------
        # 4) 自动确定代表酒店
        # -------------------------------------------------
        seed_hotel_id = normalize_string(state.get("seed_hotel_id", ""))
        seed_hotel_name = normalize_string(state.get("seed_hotel_name", ""))

        # 如果没从 getAdHotels 响应里拿到，就从页面链接兜底
        if not seed_hotel_id:
            print("[WARN] 未从 getAdHotels 响应中拿到酒店ID，尝试从页面链接中提取...")
            try:
                links = page.locator("a").evaluate_all(
                    """els => els.map(a => a.href).filter(Boolean)"""
                )
                for href in links:
                    href = normalize_string(href)
                    m = re.search(r"/hotels/(\\d+)\\.html", href)
                    if m:
                        seed_hotel_id = m.group(1)
                        break
            except Exception:
                pass

        if not seed_hotel_id:
            # 实在拿不到也先保存已有参数
            cookies = context.cookies()
            runtime["cookie"] = "; ".join(
                [f"{c['name']}={c['value']}" for c in cookies if c.get("name") and c.get("value") is not None]
            )

            for key in runtime:
                if isinstance(runtime[key], str):
                    runtime[key] = normalize_string(runtime[key])

            write_runtime_config(OUTPUT_JSON, runtime)

            print("[WARN] 没能自动找到代表酒店，只保存了列表页阶段采集到的配置。")
            print(json.dumps(runtime, ensure_ascii=False, indent=2))
            browser.close()
            return

        runtime["seed_hotel_id"] = seed_hotel_id
        runtime["seed_hotel_name"] = seed_hotel_name

        seed_detail_url = build_hotel_detail_url(
            city_en_name=CITY_EN_NAME,
            city_id=CITY_ID,
            hotel_id=seed_hotel_id,
            check_in=CHECK_IN,
            check_out=CHECK_OUT
        )
        runtime["seed_hotel_detail_url"] = seed_detail_url

        print(f"[INFO] 自动选中的代表酒店: {seed_hotel_name or 'UNKNOWN'} ({seed_hotel_id})")
        print("[INFO] 打开代表酒店详情页...")
        print("[INFO] DETAIL_URL =", seed_detail_url)

        # -------------------------------------------------
        # 5) 打开代表酒店详情页，补抓价历/房型接口
        # -------------------------------------------------
        try:
            page.goto(seed_detail_url, wait_until="domcontentloaded", timeout=60000)
        except PlaywrightTimeoutError:
            print("[WARN] 详情页加载超时，继续等待网络请求...")

        print(f"[INFO] 等待 {DETAIL_PAGE_WAIT_SECONDS} 秒收集详情页请求...")
        time.sleep(DETAIL_PAGE_WAIT_SECONDS)

        try:
            page.mouse.wheel(0, 1200)
            time.sleep(2)
            page.mouse.wheel(0, 1800)
            time.sleep(2)
        except Exception:
            pass

        # -------------------------------------------------
        # 6) 提取 Cookie
        # -------------------------------------------------
        cookies = context.cookies()
        runtime["cookie"] = "; ".join(
            [f"{c['name']}={c['value']}" for c in cookies if c.get("name") and c.get("value") is not None]
        )

        # -------------------------------------------------
        # 7) 清洗并保存
        # -------------------------------------------------
        for key in runtime:
            if isinstance(runtime[key], str):
                runtime[key] = normalize_string(runtime[key])

        write_runtime_config(OUTPUT_JSON, runtime)

        print("[DONE] 已生成运行时配置文件:", OUTPUT_JSON)
        print("[INFO] 捕获到的请求次数:")
        print(json.dumps(captured_requests, ensure_ascii=False, indent=2))
        print("[INFO] 关键配置如下:")
        print(json.dumps(runtime, ensure_ascii=False, indent=2))

        browser.close()


if __name__ == "__main__":
    main()