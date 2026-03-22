import requests
import time
import json
import random
from concurrent.futures import ThreadPoolExecutor
from requests.exceptions import (
    ConnectTimeout,
    ReadTimeout,
    RequestException,
    ConnectionError
)

# ===================== 核心配置（可根据需求修改） =====================
class Config:
    # 代理接口配置（关键！替换为实际可用的接口地址）
    PROXY_API_LIST = [
        {
            "url": "https://www.66daili.com/get-ip/",  # 示例接口地址 
            "params": {"num": 50, "type": "http"},  # 接口请求参数（数量、类型）
            "timeout": 10  # 接口请求超时时间
        },
        # 可添加更多接口源，格式同上，提升代理获取量
        {
             "url": "https://free-proxy-list.net/zh-cn/",
             "params": {"count": 30},
             "timeout": 8
         }
    ]
    
    # 代理验证配置
    TEST_URL = "http://www.baidu.com"  # 验证代理可用性的测试地址
    TEST_TIMEOUT = 5  # 代理验证超时时间（秒）
    THREAD_NUM = 20   # 多线程验证的线程数（越多越快，建议不超过50）
    
    # 代理存储配置
    SORT_BY_SPEED = True  # 是否按响应速度排序有效代理

# ===================== 代理IP池核心类 =====================
class FreeProxyPool:
    def __init__(self):
        """初始化代理池，创建存储原始代理和有效代理的列表"""
        self.raw_proxies = []  # 存储从接口获取的原始代理
        self.valid_proxies = []  # 存储验证后的有效代理

    def fetch_proxies(self):
        """从接口批量获取代理IP，无需解析网页，直接获取数据"""
        print("===== 开始从接口获取代理IP =====")
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        }

        for api in Config.PROXY_API_LIST:
            try:
                # 调用接口获取代理数据
                response = requests.get(
                    url=api["url"],
                    params=api["params"],
                    headers=headers,
                    timeout=api["timeout"]
                )
                
                # 处理接口返回结果（关键！需根据实际接口返回格式调整）
                # 假设接口返回格式为：IP:端口 一行一个，如 "123.45.67.89:8080"
                if response.status_code == 200:
                    # 按行分割，过滤空行，避免无效数据
                    api_proxies = [p.strip() for p in response.text.split("\n") if p.strip()]
                    # 去重并添加到原始代理列表，避免重复验证
                    for proxy in api_proxies:
                        if proxy not in self.raw_proxies:
                            self.raw_proxies.append(proxy)
                    print(f"从 {api['url']} 获取到 {len(api_proxies)} 个代理")
                else:
                    print(f"接口请求失败 {api['url']}，状态码：{response.status_code}")

            except Exception as e:
                print(f"获取代理失败 {api['url']}，错误：{str(e)}")
            finally:
                time.sleep(1)  # 避免请求过快被接口限流

        print(f"===== 接口获取完成，共获取 {len(self.raw_proxies)} 个原始代理 =====\n")

    def validate_single_proxy(self, proxy):
        """验证单个代理的可用性（核心方法），过滤失效代理"""
        # 构造requests可用的代理格式，适配HTTP/HTTPS请求
        proxy_format = {
            "http": f"http://{proxy}",
            "https": f"https://{proxy}"
        }

        try:
            start_time = time.time()
            # 发送验证请求（禁止重定向，提高验证效率）
            response = requests.get(
                Config.TEST_URL,
                proxies=proxy_format,
                timeout=Config.TEST_TIMEOUT,
                allow_redirects=False,
                verify=False  # 忽略SSL证书验证（避免部分代理报错）
            )
            
            # 响应状态码为200，判定为有效代理，记录响应速度和验证时间
            if response.status_code == 200:
                response_time = round(time.time() - start_time, 2)  # 计算响应时间
                self.valid_proxies.append({
                    "proxy": proxy,
                    "speed": response_time,  # 响应速度（秒）
                    "validate_time": time.strftime("%Y-%m-%d %H:%M:%S")  # 验证时间
                })
                #print(f"✅ 有效代理：{proxy} | 响应速度：{response_time}s")

        except (ConnectTimeout, ReadTimeout):
            # 超时：代理响应过慢，判定为无效
            pass
        except (ConnectionError, RequestException):
            # 连接失败/请求异常：代理不可用
            pass
        except Exception as e:
            # 其他异常：静默跳过（避免单个代理验证失败影响整体）
            pass

    def save_valid_proxies_to_json(self, file_path="valid_proxies.json"):
        """将筛选出的有效代理保存到 JSON 文件"""
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(self.valid_proxies, f, ensure_ascii=False, indent=4)
            print(f"✅ 已将 {len(self.valid_proxies)} 个有效代理保存到 {file_path}")
        except Exception as e:
            print(f"❌ 保存 JSON 文件失败：{e}")

    def validate_all_proxies(self):
        """批量验证所有原始代理（多线程提速），提升验证效率"""
        print("===== 开始验证代理有效性（多线程） =====")
        # 使用线程池并发验证，大幅提升验证速度
        with ThreadPoolExecutor(max_workers=Config.THREAD_NUM) as executor:
            executor.map(self.validate_single_proxy, self.raw_proxies)
        
        # 按响应速度排序（可选），优先使用速度更快的代理
        if Config.SORT_BY_SPEED and self.valid_proxies:
            self.valid_proxies.sort(key=lambda x: x["speed"])
        
        print(f"\n===== 代理验证完成，共筛选出 {len(self.valid_proxies)} 个有效代理 =====\n")
        self.save_valid_proxies_to_json("valid_proxies.json")
        
    def build_proxy_pool(self):
        """构建代理池主入口（一键执行获取+验证），新手直接调用即可"""
        # 1. 从接口获取代理
        self.fetch_proxies()
        # 2. 验证代理有效性
        self.validate_all_proxies()

# ===================== 运行示例 =====================
if __name__ == "__main__":
    # 初始化代理池
    proxy_pool = FreeProxyPool()
    # 构建代理池（一键执行获取+验证）
    proxy_pool.build_proxy_pool()

   