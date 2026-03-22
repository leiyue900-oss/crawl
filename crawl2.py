import requests
import pandas as pd
import time
import random
import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from fake_useragent import UserAgent

# =========================================================
# 1. 配置区：先改这里
# =========================================================
def load_runtime_config(path="ctrip_runtime_config.json"):
    import json
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

runtime = load_runtime_config()

COOKIE = runtime["cookie"]
PHANTOM_TOKEN = runtime["phantom_token"]
CID = runtime["cid"]
SID = runtime["sid"]
VID = runtime["vid"]
PAGE_ID = runtime["page_id"]
AID = runtime["aid"]

CALENDAR_WCLIENT_REQ = runtime["calendar_wclient_req"]
ROOM_WCLIENT_REQ = runtime["room_wclient_req"]

LIST_API_URL = runtime["list_api_url"]
PRICE_CALENDAR_URL = runtime["price_calendar_url"]
ROOM_LIST_URL = runtime["room_list_url"]

START_CHECK_IN = runtime["check_in"]

# 地区与日期
CITY_ID = 380
CITY_NAME = "南宁"
DAYS = 3

# 抓多少页酒店列表、最多处理多少家酒店
MAX_PAGES = 1
PAGE_SIZE = 5
MAX_HOTELS = 3

# 输出文件
OUT_HOTEL_LIST = "region_hotels.xlsx"
#OUT_MIN_PRICE = "region_hotels_min_price_15days.xlsx"
OUT_ROOM_PIVOT = "region_hotels_room_price_pivot_15days.xlsx"


# =========================================================
# 3. 公共工具
# =========================================================
ua = UserAgent()
def load_proxy_pool(json_path="valid_proxies.json"):
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)

def get_random_proxy(proxy_pool):
    if not proxy_pool:
        raise ValueError("代理池为空")

    item = random.choice(proxy_pool)
    proxy = item["proxy"] if isinstance(item, dict) else item

    return {
        "http": f"http://{proxy}",
        "https": f"http://{proxy}"
    }

def ymd_to_compact(date_str: str) -> str:
    return date_str.replace("-", "")


def generate_date_pairs(start_check_in: str, days: int = 15) -> List[tuple]:
    base = datetime.strptime(start_check_in, "%Y-%m-%d")
    pairs = []
    for i in range(days):
        check_in = (base + timedelta(days=i)).strftime("%Y-%m-%d")
        check_out = (base + timedelta(days=i + 1)).strftime("%Y-%m-%d")
        pairs.append((check_in, check_out))
    return pairs

def build_headers(cookie: str, phantom_token: str, wclient_req: str) -> Dict[str, str]:
    cookie = cookie.strip().replace("\r", "").replace("\n", "")
    phantom_token = phantom_token.strip().replace("\r", "").replace("\n", "")
    wclient_req = wclient_req.strip()

    return {
        "accept": "application/json",
        "content-type": "application/json",
        "origin": "https://hotels.ctrip.com",
        "referer": "https://hotels.ctrip.com/",
        "user-Agent": ua.random,
        "cookie": cookie,
        "phantom-token": phantom_token,
        "x-ctx-country": "CN",
        "x-ctx-currency": "CNY",
        "x-ctx-locale": "zh-CN",
        "x-ctx-ubt-pageid": PAGE_ID,
        "x-ctx-ubt-vid": VID,
        "x-ctx-wclient-req": wclient_req,
    }

def build_list_headers(cookie: str) -> Dict[str, str]:
    cookie = cookie.strip().replace("\r", "").replace("\n", "")
    return {
        "accept": "application/json, text/plain, */*",
        "content-type": "application/json;charset=UTF-8",
        "origin": "https://hotels.ctrip.com",
        "referer": "https://hotels.ctrip.com/",
        "user-Agent": ua.random,
        "cookie": cookie,
    }

def build_head(check_in: str, check_out: str) -> Dict[str, Any]:
    return {
        "cid": CID,
        "ctok": "",
        "cver": "0",
        "lang": "01",
        "sid": SID,
        "syscode": "09",
        "auth": "",
        "xsid": "",
        "extension": [
            {"name": "cityId", "value": ""},
            {"name": "checkIn", "value": check_in},
            {"name": "checkOut", "value": check_out},
        ],
        "platform": "PC",
        "bu": "HBU",
        "group": "ctrip",
        "aid": AID,
        "ouid": "",
        "locale": "zh-CN",
        "region": "CN",
        "timezone": "8",
        "currency": "CNY",
        "pageId": PAGE_ID,
        "vid": VID,
        "guid": "",
        "isSSR": False,
    }


# =========================================================
# 4. 酒店列表接口
# =========================================================
def extract_room_info(room_list: List[Dict[str, Any]]) -> Dict[str, Any]:
    prices = []
    room_summaries = []

    for room in room_list or []:
        price = (
            room.get("priceInfo", {}).get("price")
            or room.get("price")
            or room.get("salePrice")
        )
        if price is not None:
            prices.append(price)

        room_name = (
            room.get("summary", {}).get("saleRoomName")
            or room.get("roomName")
            or ""
        )

        if room_name:
            if price is not None:
                room_summaries.append(f"{room_name} 价格:{price}")
            else:
                room_summaries.append(room_name)

    return {
        "min_price_from_rooms": min(prices) if prices else None,
        "room_summary": " || ".join(room_summaries),
    }


def fetch_hotel_page(
    session: requests.Session,
    city_id: int,
    check_in: str,
    check_out: str,
    page_index: int,
    page_size: int = 10,
    proxy_pool: Optional[List] = None,
    max_retries: int = 3
) -> List[Dict[str, Any]]:

    payload = {
        "cityId": city_id,
        "adPositionCodes": ["HTL_LST_002", "HTL_LST_001"],
        "head": {
            "platform": "PC",
            "cver": "0",
            "cid": CID,
            "bu": "HBU",
            "group": "ctrip",
            "aid": AID,
            "sid": SID,
            "locale": "zh-CN",
            "currency": "CNY",
            "pageId": PAGE_ID,
            "vid": VID
        }
    }
    last_exception = None
    
    for attempt in range(1, max_retries + 1):
        try:
            request_kwargs = {
                "url": LIST_API_URL,
                "json": payload,
                "timeout": 20
            }

            if proxy_pool:
                proxy_str, proxies = get_random_proxy(proxy_pool)
                request_kwargs["proxies"] = proxies
                print(f"[INFO] 酒店列表请求使用代理: {proxy_str}")
            time.sleep(random.uniform(1, 5))

            resp = session.post(**request_kwargs)

            print("[DEBUG] getAdHotels status:", resp.status_code)
            print("[DEBUG] getAdHotels text:", resp.text[:500])

            resp.raise_for_status()
            data = resp.json()

            results = []
            ad_list = data.get("data", {}).get("adList", []) or []

            for block in ad_list:
                hotels = block.get("hotels", []) or []
                for hotel in hotels:
                    base = hotel.get("base", {}) or {}
                    comment = hotel.get("comment", {}) or {}
                    money = hotel.get("money", {}) or {}

                    price_raw = money.get("price", "")
                    # 例如 "¥441" -> 441
                    min_price = None
                    if isinstance(price_raw, str):
                        s = price_raw.replace("¥", "").replace(",", "").strip()
                        try:
                            min_price = float(s)
                        except Exception:
                            min_price = price_raw

                    item = {
                        "hotel_id": base.get("hotelId"),
                        "hotel_name": base.get("hotelName"),
                        "score": comment.get("score"),
                        "address": "",     # 这个接口里没有地址
                        "district": "",    # 这个接口里没有区域
                        "min_price": min_price,
                        "room_summary": "",
                        "check_in": check_in,
                        "check_out": check_out,
                        "page_index": page_index,
                        "hotel_image": base.get("hotelImage", ""),
                        "detail_url": base.get("detailUrl", ""),
                        "star": base.get("star", ""),
                        "comment_count": comment.get("number", ""),
                        "comment_desc": comment.get("description", ""),
                        "sold_out": money.get("soldOut", False),
                        "price_delete": money.get("priceDelete", ""),
                        "position": block.get("position", ""),
                        "title": block.get("title", ""),
                    }
                    results.append(item)

            return results
        except Exception as e:
            last_exception = e
            print(f"[WARN] 酒店列表请求失败，第{attempt}次重试: {e}")
            time.sleep(random.uniform(1.0, 2.0))

    raise last_exception

def fetch_region_hotels(
    session: requests.Session,
    city_id: int,
    check_in: str,
    check_out: str,
    max_pages: int = 1,
    page_size: int = 10
) -> pd.DataFrame:
    all_rows = []

    for page in range(1, max_pages + 1):
        print(f"[INFO] 抓酒店列表，第 {page} 页")
        rows = fetch_hotel_page(
            session=session,
            city_id=city_id,
            check_in=check_in,
            check_out=check_out,
            page_index=page,
            page_size=page_size
        )
        all_rows.extend(rows)
        time.sleep(random.uniform(1.0, 2.0))

    df = pd.DataFrame(all_rows)
    if df.empty:
        return df

    df["hotel_id"] = df["hotel_id"].astype(str)
    df = df.drop_duplicates(subset=["hotel_id"], keep="first").reset_index(drop=True)
    return df




# =========================================================
# 6. 房型列表接口
# =========================================================
#
def build_room_list_payload(hotel_id: int, city_id: int, check_in: str, check_out: str) -> Dict[str, Any]:
    return {
        "search": {
            "isRSC": False,
            "isSSR": False,
            "hotelId": int(hotel_id),
            "roomId": 0,
            "checkIn": ymd_to_compact(check_in),
            "checkOut": ymd_to_compact(check_out),
            "roomQuantity": 1,
            "adult": 1,
            "childInfoItems": [],
            "isIjtb": False,
            "priceType": 2,
            "hotelUniqueKey": "",
            "mustShowRoomList": [],
            "location": {
                "geo": {
                    "cityID": int(city_id)
                }
            },
            "filters": [
                {"filterId": "17|1", "type": "17", "value": "1", "title": ""}
            ],
            "meta": {
                "fgt": -1,
                "roomkey": "",
                "minCurr": "",
                "minPrice": "",
                "roomToken": ""
            },
            "hasAidInUrl": False,
            "cancelPolicyType": 0,
            "fixSubhotel": 0
        },
        "head": build_head(check_in, check_out)
    }

def fetch_room_list(
    session: requests.Session,
    hotel_id: int,
    city_id: int,
    check_in: str,
    check_out: str,
    proxy_pool: Optional[List] = None,
    max_retries: int = 3
) -> Dict[str, Any]:
    payload = build_room_list_payload(hotel_id, city_id, check_in, check_out)

    last_exception = None
    for attempt in range(1, max_retries + 1):
        try:
            request_kwargs = {
                "url": ROOM_LIST_URL,
                "json": payload,
                "timeout": 25
            }

            if proxy_pool:
                proxy_str, proxies = get_random_proxy(proxy_pool)
                request_kwargs["proxies"] = proxies
                print(f"[INFO] 房型请求使用代理: {proxy_str} | hotel_id={hotel_id} | date={check_in}")
            time.sleep(random.uniform(1, 5))
            resp = session.post(**request_kwargs)

            if resp.status_code != 200:
                print(f"[DEBUG] room status={resp.status_code}, hotel_id={hotel_id}, date={check_in}")
                print("[DEBUG] room payload:", json.dumps(payload, ensure_ascii=False))
                print("[DEBUG] room response:", resp.text[:1000])

            resp.raise_for_status()
            return resp.json()

        except Exception as e:
            last_exception = e
            print(f"[WARN] 房型请求失败，第{attempt}次重试: {e}")
            time.sleep(random.uniform(1.0, 2.0))
            
    raise last_exception    
# =========================================================
# 7. 房型解析
# =========================================================
def walk_nodes(obj: Any):
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from walk_nodes(v)
    elif isinstance(obj, list):
        for item in obj:
            yield from walk_nodes(item)

def get_physical_room_id(node: Dict[str, Any]) -> str:
    # 1. 顶层直接找
    v = node.get("physicalRoomId")
    if v not in [None, "", 0]:
        return str(v)

    # 2. 常见嵌套层找
    for sub_key in ["base", "roomBaseInfo", "basicRoomInfo", "roomInfo", "baseRoomInfo"]:
        sub = node.get(sub_key)
        if isinstance(sub, dict):
            v = sub.get("physicalRoomId")
            if v not in [None, "", 0]:
                return str(v)

    # 3. 从 availParam.extendParam 里找
    avail_param = node.get("availParam")
    if isinstance(avail_param, dict):
        ext = avail_param.get("extendParam")
        if isinstance(ext, str) and ext.strip():
            try:
                ext_json = json.loads(ext)
                for k in ["physicalRoomId", "physical_room_id", "physicalroomid"]:
                    v = ext_json.get(k)
                    if v not in [None, "", 0]:
                        return str(v)
            except Exception:
                pass

    return ""


def get_room_name_from_physical_room_map(resp_json: Dict[str, Any], physical_room_id: str) -> str:
    if not physical_room_id:
        return ""

    physical_room_map = resp_json.get("data", {}).get("physicalRoomMap", {})
    if not isinstance(physical_room_map, dict):
        return ""

    room_meta = physical_room_map.get(str(physical_room_id), {})
    if not isinstance(room_meta, dict):
        return ""

    name = room_meta.get("name", "")
    if isinstance(name, str) and name.strip():
        return name.strip()

    return ""


def parse_room_list(resp_json: Dict[str, Any], hotel_id: int, check_in: str, check_out: str) -> List[Dict[str, Any]]:
    rows = []

    for node in walk_nodes(resp_json):
        if not isinstance(node, dict):
            continue

        price_info = node.get("priceInfo")
        if not isinstance(price_info, dict):
            continue

        price = price_info.get("price")
        if price is None:
            continue

        # 先拿 physicalRoomId
        physical_room_id = get_physical_room_id(node)

        # room_id 直接优先使用 physicalRoomId
        room_id = physical_room_id

        # 如果没拿到，再退回老逻辑
        if not room_id:
            for k in ["physicalRoomID", "id", "basicRoomId"]:
                v = node.get(k)
                if v not in [None, "", 0]:
                    room_id = str(v)
                    break

        avail_param = node.get("availParam")
        if not room_id and isinstance(avail_param, dict):
            roomkey = avail_param.get("roomkey")
            if roomkey:
                room_id = str(roomkey)

            ext = avail_param.get("extendParam")
            if not room_id and isinstance(ext, str) and ext.strip():
                try:
                    ext_json = json.loads(ext)
                    roomid = ext_json.get("roomid")
                    if roomid:
                        room_id = str(roomid)
                except Exception:
                    pass

        # 先从 physicalRoomMap 取正式房型名
        room_name = get_room_name_from_physical_room_map(resp_json, physical_room_id)

        # 如果没取到，再从当前节点兜底
        if not room_name:
            room_name = (
                node.get("name")
                or node.get("roomName")
                or node.get("saleRoomName")
                or node.get("title")
                or ""
            )

        tag_titles = []
        tag_info_list = node.get("tagInfoList", [])
        if isinstance(tag_info_list, list):
            for t in tag_info_list:
                title = t.get("tagTitle")
                if isinstance(title, str) and title.strip():
                    tag_titles.append(title.strip())

        if not room_name:
            room_name = " | ".join(tag_titles[:3]) if tag_titles else ""

        if not room_name:
            room_name = "UNKNOWN_ROOM"

        bed_type = ""
        for t in tag_titles:
            if "床" in t and "早餐" not in t and "入住" not in t:
                bed_type = t
                break

        rows.append({
            "hotel_id": hotel_id,
            "check_in": check_in,
            "check_out": check_out,
            "room_id": room_id,
            "room_name": room_name,
            "price": price,
            "display_price": price_info.get("displayPrice", ""),
            "delete_price": price_info.get("deletePrice", ""),
            "bed_type": bed_type,
            "is_min_price_room": node.get("isMinPriceRoom", False),
            "is_start_price_room": node.get("isStartPriceRoom", False),
            "tag_titles": " | ".join(tag_titles),
        })

    dedup = []
    seen = set()
    for r in rows:
        key = (r["check_in"], r["room_id"], r["room_name"], r["price"], r["display_price"])
        if key not in seen:
            seen.add(key)
            dedup.append(r)

    return dedup


# =========================================================
# 8. 单酒店抓取函数
# =========================================================
def crawl_room_prices_15days(
    session: requests.Session,
    hotel_id: int,
    city_id: int,
    start_check_in: str,
    days: int = 15
) -> pd.DataFrame:
    all_rows = []
    date_pairs = generate_date_pairs(start_check_in, days)

    for idx, (check_in, check_out) in enumerate(date_pairs, 1):
        try:
            print(f"[INFO] ({idx}/{days}) 抓房型价格: {check_in} -> {check_out}")
            resp_json = fetch_room_list(session, hotel_id, city_id, check_in, check_out)
            rows = parse_room_list(resp_json, hotel_id, check_in, check_out)
            print(f"[INFO] {check_in} 抓到 {len(rows)} 条房型报价")
            all_rows.extend(rows)
            time.sleep(random.uniform(1.2, 2.5))
        except Exception as e:
            print(f"[ERROR] {check_in} 抓取失败: {e}")

    return pd.DataFrame(all_rows)


# =========================================================
# 9. 多酒店抓取函数
# =========================================================

def crawl_multi_hotels_room_prices(
    room_session: requests.Session,
    hotel_df: pd.DataFrame,
    city_id: int,
    start_check_in: str,
    days: int = 15,
    max_hotels: int = 20
) -> pd.DataFrame:
    all_rows = []

    if hotel_df.empty:
        return pd.DataFrame()

    hotel_df = hotel_df.head(max_hotels).copy()

    for _, row in hotel_df.iterrows():
        hotel_id = row["hotel_id"]
        hotel_name = row.get("hotel_name", "")

        print(f"\n[INFO] ===== 酒店 {hotel_name} ({hotel_id}) =====")

        try:
            room_df = crawl_room_prices_15days(
                session=room_session,
                hotel_id=hotel_id,
                city_id=city_id,
                start_check_in=start_check_in,
                days=days
            )

            if not room_df.empty:
                room_df["hotel_name"] = hotel_name
                room_df["address"] = row.get("address", "")
                room_df["score"] = row.get("score", "")
                all_rows.append(room_df)

            time.sleep(random.uniform(1.5, 3.0))

        except Exception as e:
            print(f"[ERROR] 酒店 {hotel_name} ({hotel_id}) 抓取失败: {e}")

    if not all_rows:
        return pd.DataFrame()

    return pd.concat(all_rows, ignore_index=True)


def build_room_price_pivot(room_df: pd.DataFrame) -> pd.DataFrame:
    if room_df.empty:
        return pd.DataFrame()

    df = room_df.copy()
    df["price"] = pd.to_numeric(df["price"], errors="coerce")

    pivot_df = df.pivot_table(
        #index=["hotel_id", "hotel_name", "room_id", "room_name", "bed_type", "breakfast", "cancel_rule", "payment_type"],
        index=["hotel_id", "hotel_name", "room_id", "room_name", "bed_type"],
        columns="check_in",
        values="price",
        aggfunc="first"
    ).reset_index()

    pivot_df.columns.name = None
    return pivot_df


# =========================================================
# 10. 主函数
# =========================================================
def main():
    first_check_out = (
        datetime.strptime(START_CHECK_IN, "%Y-%m-%d") + timedelta(days=1)
    ).strftime("%Y-%m-%d")

     # 先加载代理池
    proxy_pool = load_proxy_pool("valid_proxies.json")
    # 1) 先抓地区酒店列表
    list_session = requests.Session()
    list_session.headers.update(build_list_headers(COOKIE))

    list_proxies = get_random_proxy(proxy_pool)
    list_session.proxies.update(list_proxies)
    print(f"[INFO] 酒店列表使用代理: {list_proxies}")
    
    hotel_df = fetch_region_hotels(
        session=list_session,
        city_id=CITY_ID,
        check_in=START_CHECK_IN,
        check_out=first_check_out,
        max_pages=MAX_PAGES,
        page_size=PAGE_SIZE
    )

    if hotel_df.empty:
        print("[WARN] 没抓到酒店列表")
        return

    hotel_df = hotel_df.head(MAX_HOTELS).copy()
    #hotel_df.to_excel(OUT_HOTEL_LIST, index=False)
    print(f"[DONE] 已获取酒店列表 {len(hotel_df)} 家，保存到 {OUT_HOTEL_LIST}")


    # 3) 抓多酒店房型价格
    room_session = requests.Session()
    room_session.headers.update(build_headers(COOKIE, PHANTOM_TOKEN, ROOM_WCLIENT_REQ))

    room_proxies = get_random_proxy(proxy_pool)
    room_session.proxies.update(room_proxies)
    print(f"[INFO] 房型接口使用代理: {room_proxies}")
    
    multi_room_df = crawl_multi_hotels_room_prices(
        room_session=room_session,
        hotel_df=hotel_df,
        city_id=CITY_ID,
        start_check_in=START_CHECK_IN,
        days=DAYS,
        max_hotels=MAX_HOTELS
    )

    if not multi_room_df.empty:
        pivot_df = build_room_price_pivot(multi_room_df)
        pivot_df.to_excel(OUT_ROOM_PIVOT, index=False)
        print(f"[DONE] 多酒店房型透视表已保存: {OUT_ROOM_PIVOT}")
    else:
        print("[WARN] 没抓到多酒店房型价格数据")


if __name__ == "__main__":
    main()