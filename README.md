# Ctrip 酒店数据抓取工具

一个面向携程酒店页面的抓取脚本集合，包含：

- **运行时参数采集**（`refresh_runtime.py`）：通过 Playwright 自动捕获接口参数与请求头。
- **代理池构建**（`IP.py`）：批量获取代理并做可用性验证，输出到 `valid_proxies.json`。
- **酒店列表/房型价格抓取**（`crawl2.py`）：读取运行时配置与代理池，抓取酒店信息并导出 Excel。

> ⚠️ 本项目仅用于学习与研究用途。请遵守目标网站服务条款、robots 协议及当地法律法规，合理控制访问频率。

---

## 目录结构

```text
.
├── crawl2.py                  # 主抓取脚本（酒店列表 + 房型价格）
├── refresh_runtime.py         # 自动刷新运行时参数（cookie/token/url等）
├── IP.py                      # 免费代理获取与验证
├── ctrip_runtime_config.json  # 运行时配置（由 refresh_runtime.py 生成/更新）
└── valid_proxies.json         # 有效代理池（由 IP.py 生成/更新）
```

---

## 环境要求

- Python 3.9+
- 建议使用虚拟环境（venv/conda）

### 依赖安装

```bash
pip install requests pandas fake-useragent playwright openpyxl
python -m playwright install chromium
```

> `openpyxl` 用于导出 Excel。

---

## 快速开始

### 1）刷新运行时配置

先运行：

```bash
python refresh_runtime.py
```

该脚本会访问携程页面并抓取动态参数，写入 `ctrip_runtime_config.json`，包括：

- `cookie`
- `phantom_token`
- `cid/sid/vid/page_id/aid`
- `list_api_url`
- `price_calendar_url`
- `room_list_url`
- 其他上下文字段

> 首次运行可将 `HEADLESS = False`，方便观察浏览器行为与登录状态。

### 2）构建代理池（可选但推荐）

```bash
python IP.py
```

脚本会从配置的代理源拉取代理，批量验证后输出到 `valid_proxies.json`。

### 3）执行抓取

```bash
python crawl2.py
```

默认会读取：

- `ctrip_runtime_config.json`
- `valid_proxies.json`

并导出结果到 Excel（文件名由脚本内配置控制）。

---

## 常用配置说明

在 `crawl2.py` 中重点关注：

- 区域与日期
  - `CITY_ID`
  - `CITY_NAME`
  - `START_CHECK_IN`
  - `DAYS`
- 抓取规模
  - `MAX_PAGES`
  - `PAGE_SIZE`
  - `MAX_HOTELS`
- 输出文件
  - `OUT_HOTEL_LIST`
  - `OUT_ROOM_PIVOT`

在 `refresh_runtime.py` 中可调整：

- `CITY_EN_NAME`
- `CITY_ID`
- `HEADLESS`
- 页面等待时长（`LIST_PAGE_WAIT_SECONDS` / `DETAIL_PAGE_WAIT_SECONDS`）

在 `IP.py` 中可调整：

- 代理源（`Config.PROXY_API_LIST`）
- 验证地址（`Config.TEST_URL`）
- 超时与线程数（`TEST_TIMEOUT` / `THREAD_NUM`）

---

## 常见问题

### 1. 抓取返回空数据或 403

- 先重新执行 `python refresh_runtime.py` 更新运行时参数。
- 检查 `ctrip_runtime_config.json` 是否生成了完整字段。
- 降低抓取频率，增加随机 sleep。
- 更换或更新代理池。

### 2. Playwright 启动失败

- 确认已执行：
  ```bash
  python -m playwright install chromium
  ```
- Linux 环境下可能缺少系统依赖，按 Playwright 提示补齐。

### 3. fake-useragent 报错

- 可尝试升级：
  ```bash
  pip install -U fake-useragent
  ```

---

## 建议工作流

每次抓取前按下面顺序执行：

1. `python refresh_runtime.py`
2. `python IP.py`
3. `python crawl2.py`

这样可以最大限度减少动态参数过期导致的问题。

---

## 免责声明

本项目仅用于技术研究与学习交流，请勿用于任何违反法律法规或平台规则的用途。使用者应自行承担相关风险与责任。
