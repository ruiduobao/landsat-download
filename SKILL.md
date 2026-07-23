---
name: landsat-download
display_name: Landsat Downloader
version: 0.1.2
author: rui.duobao
license: MIT-0
description: |
  通过 STAC 搜索和下载 Landsat 8 / Landsat 9 Collection 2 Level 2 影像。
  默认后端是 Microsoft Planetary Computer（公开数据，无需账号）。
  支持云量过滤、WRS-2 路径/行过滤、单波段选择、安全的 .part 临时文件写入
  以及可视化下载进度（速度 + ETA）。
  Use for Landsat 8/9 imagery search by bounding box / date / cloud cover,
  asset selection (SR_B1..SR_B7, ST_B10, QA_PIXEL, QA_RADSAT), and large-file
  downloads with visual progress.

  English: STAC-based Landsat 8/9 Collection 2 Level 2 downloader.
  Data source: Microsoft Planetary Computer (USGS Landsat Collection 2,
  public domain). Supports cloud-cover filter, WRS-2 path/row filter,
  band selection, safe .part temp writes, and visual progress (speed + ETA).
runtime: python>=3.9
tags: [gis, remote-sensing, landsat, stac, planetary-computer, earth-observation, 下载]
---

# Landsat Downloader | Landsat 8/9 影像下载器

通过 STAC API 搜索并下载 Landsat 8 / Landsat 9 Collection 2 Level 2 影像。
本 skill 沿用 [Sentinel Downloader](https://clawhub.ai/skills/sentinel-downloader-skill)
的架构（STAC + 单文件 CLI + 可视化进度 + `.part` 安全写入），但适配
Landsat 8/9 的元数据约定（WRS-2 路径/行、Collection 2 Level 2 资产命名、
`eo:cloud_cover` 云量字段）。

## 依赖

```bash
pip install 'requests>=2.28.0'
```

> Planetary Computer 搜索与签名均通过 `requests` 完成，**无需**安装
> `pystac-client` / `planetary-computer` SDK。
> Windows 用户直接用 `python landsat-download.py`；Linux / macOS 可用
> `./landsat-download.sh --check-deps` 自动检查依赖。

## 数据源 / Source

| 后端 | URL | 凭证 | 默认 |
|---|---|---|---|
| **Planetary Computer**（推荐） | `https://planetarycomputer.microsoft.com/api/stac/v1/` | 无（公开） | ✅ |
| AWS Open Data（高级） | `https://earth-search.aws.element84.com/v1/` | 无（公开） | — |

> **License** — Landsat Collection 2 数据由 USGS 持有，**公共领域**（public
> domain）。本 skill 抓取的是公开的 STAC 索引 + 公开的 S3 资产，不需要任何
> 账号或凭证。

## 使用方法

所有检索命令都必须包含 `--bbox`、`--start-date` 和 `--end-date`。

### 搜索 Landsat 8/9 影像（仅查询，不下载）

```bash
python landsat-download.py \
    --bbox 116.0 39.0 117.0 40.0 \
    --start-date 2024-01-01 \
    --end-date 2024-12-31
```

### 限制云量（推荐 ≤ 20%）

```bash
python landsat-download.py \
    --bbox 116.0 39.0 117.0 40.0 \
    --start-date 2024-01-01 \
    --end-date 2024-12-31 \
    --max-cloud-cover 20
```

### 搜索 + 下载（默认下载到 `./landsat_data/`）

```bash
python landsat-download.py \
    --bbox 116.0 39.0 117.0 40.0 \
    --start-date 2024-01-01 \
    --end-date 2024-12-31 \
    --max-cloud-cover 20 \
    --download \
    --output-dir ./data
```

### 仅 Landsat 9（排除 Landsat 8）

```bash
python landsat-download.py \
    --bbox 116.0 39.0 117.0 40.0 \
    --start-date 2024-01-01 \
    --end-date 2024-12-31 \
    --platform landsat-9
```

### 按 WRS-2 路径/行过滤

```bash
python landsat-download.py \
    --bbox 116.0 39.0 117.0 40.0 \
    --start-date 2024-01-01 \
    --end-date 2024-12-31 \
    --path 123 --row 34
```

### 只下载特定波段（红 / 绿 / 蓝）

```bash
python landsat-download.py \
    --bbox 116.0 39.0 117.0 40.0 \
    --start-date 2024-01-01 \
    --end-date 2024-12-31 \
    --bands red green blue \
    --download
```

### 以 JSON 格式输出（用于程序化处理）

```bash
python landsat-download.py \
    --bbox 116.0 39.0 117.0 40.0 \
    --start-date 2024-01-01 \
    --end-date 2024-12-31 \
    --output-format json
```

---

## 常用参数 / Parameters

| 参数 / Parameter | 说明 / Description | 必填 / Required |
|---|---|---|
| `--bbox` | 地理范围 `[minLon minLat maxLon maxLat]` / Geographic extent | ✅ |
| `--start-date` | 开始日期 `YYYY-MM-DD` | ✅ |
| `--end-date` | 结束日期 `YYYY-MM-DD` | ✅ |
| `--platform` | `landsat-8` / `landsat-9` / `both`（默认 `both`） | ❌ |
| `--max-cloud-cover` | 最大云量百分比 0–100（S2 / Landsat 均支持） | ❌ |
| `--path` | WRS-2 路径号 0–233 | ❌ |
| `--row` | WRS-2 行号 0–248 | ❌ |
| `--limit` | 限制返回条目数（先小范围试检索） | ❌ |
| `--bands` | 下载的资产列表（默认 `red green blue nir08 swir16 swir22`） | ❌ |
| `--download` | 触发实际下载（默认仅查询） | ❌ |
| `--output-dir` | 下载目录（默认 `./landsat_data`） | ❌ |
| `--output-format` | `text`（默认）/ `json` | ❌ |
| `--no-progress` | 关闭动态进度条（脚本 / CI 环境） | ❌ |
| `--download-timeout` | 单个请求超时秒数（默认 600，适合大文件） | ❌ |
| `--source` | `pc`（Planetary Computer，默认）/ `aws`（Element84 Earth Search） | ❌ |
| `--quiet` | 同时关闭进度条 + 隐私告示 | ❌ |

## 支持的 Landsat 任务

| 任务 / Mission | 卫星 | 发射 | 传感器 | 空间分辨率 |
|---|---|---|---|---|
| **Landsat 8** | LDCM | 2013-02-11 | OLI / TIRS | 30 m multispectral, 15 m pan, 100 m thermal |
| **Landsat 9** | Landsat 9 | 2021-09-27 | OLI-2 / TIRS-2 | 同 Landsat 8 |

> Landsat 5 / 7 在 Collection 2 Level 2 中也已包含（`landsat-c2-l2`
> collection 涵盖 Landsat 4-9 全部），但需要时可通过 `--platform
> landsat-5` / `--platform landsat-7` 显式指定。

## 默认下载波段 / Default Bands

| 资产 / Asset | 含义 (USGS) | 波长 | 分辨率 |
|---|---|---|---|
| `red` | Red (SR_B4) | 0.64–0.67 µm | 30 m |
| `green` | Green (SR_B3) | 0.53–0.60 µm | 30 m |
| `blue` | Blue (SR_B2) | 0.45–0.51 µm | 30 m |
| `nir08` | NIR (SR_B5) | 0.85–0.88 µm | 30 m |
| `swir16` | SWIR1 (SR_B6) | 1.57–1.65 µm | 30 m |
| `swir22` | SWIR2 (SR_B7) | 2.11–2.29 µm | 30 m |
| `lwir11` | Thermal (ST_B10) | 10.60–11.19 µm | 100 m |
| `qa` | 云 / 雪 / 水掩膜 (QA_PIXEL) | — | — |
| `mtl.txt` / `mtl.xml` | 元数据 | — | — |
| `ang` | 角度系数 | — | — |

> 资产名是 STAC 公开的 key（Planetary Computer 标准化），与 USGS Collection 2
> 文件名（`SR_B2.TIF` 等）不同。所有可用 asset 详见
> https://planetarycomputer.microsoft.com/dataset/landsat-c2-l2
> 或运行 `python landsat-download.py --list-bands`。

## 输出示例

### 文本格式（默认）

```
$ python landsat-download.py --bbox 116.0 39.0 117.0 40.0 --start-date 2024-01-01 --end-date 2024-12-31 --max-cloud-cover 20

[landsat-download] searching Planetary Computer STAC ...
[landsat-download] collection: landsat-c2-l2
[landsat-download] bbox:       [116.0, 39.0, 117.0, 40.0]
[landsat-download] date:       2024-01-01 → 2024-12-31
[landsat-download] platform:   landsat-8 + landsat-9
[landsat-download] cloud:      ≤ 20%

[landsat-download] found 8 scene(s)
[landsat-download] cloud cover ≤ 20.0%

  1. LC09_L2SP_122033_20240831_02_T1
     Date:    2024-08-31
     Cloud:   25.34%
     Platform: landsat-9
     Path/Row: 122 / 033
     Assets:  qa ang red blue drad emis emsd trad urad atran cdist gree...

  2. LC08_L2SP_123033_20240830_02_T1
     Date:    2024-08-30
     Cloud:   0.20%
     Platform: landsat-8
     Path/Row: 123 / 033
     ...

[landsat-download] search done. Add --download to fetch.
```

### JSON 格式

```json
{
  "query": {
    "bbox": [116.0, 39.0, 117.0, 40.0],
    "start_date": "2024-01-01",
    "end_date": "2024-12-31",
    "max_cloud_cover": 20,
    "platform": "both"
  },
  "source": "planetary-computer",
  "count": 8,
  "scenes": [
    {
      "id": "LC09_L2SP_122033_20240831_02_T1",
      "datetime": "2024-08-31T02:47:30.469664Z",
      "platform": "landsat-9",
      "cloud_cover": 25.34,
      "path": "122",
      "row": "033",
      "assets": ["red", "green", "blue", "nir08", "swir16", "swir22", "qa", "lwir11", "ang", ...]
    }
  ]
}
```

## 下载进度与文件保护

- 已知文件大小时显示 **进度条 / 百分比 / 已下载 / 总大小 / 瞬时速度 / 预计剩余时间**
- 服务端未提供文件大小时显示 **动态下载状态 / 已下载大小 / 速度**
- 下载过程写入同目录的 **`.part` 临时文件**；仅成功完成后才替换为最终文件
- 失败会清除临时文件，**不会覆盖已有的最终文件**

```
[landsat-download] downloading LC09_L2SP_122033_20240831_02_T1
  ↳ red.tif     10.2 MB ┃████████████░░░░░░░░░░░░░░░░░░░░░░░░│  38%  2.1 MB/s  ETA 0:00:03
  ↳ green.tif    8.9 MB ┃██████████████████████████████░░░░│  92%  2.3 MB/s  ETA 0:00:00
  ...
  ✔ 6/6 assets downloaded (62.4 MB) in 28s
```

## STAC 端点

| 用途 | URL |
|---|---|
| Planetary Computer 搜索 | `https://planetarycomputer.microsoft.com/api/stac/v1/search` |
| Planetary Computer 资产签名 | `https://planetarycomputer.microsoft.com/api/sas/v1/token/{collection}` |
| Element84 Earth Search（AWS） | `https://earth-search.aws.element84.com/v1/search` |

## Permissions

- **网络出口**：
  - `https://planetarycomputer.microsoft.com`（默认后端，STAC 搜索 + 资产签名）
  - `https://landsateuwest.blob.core.windows.net` 或 `s3://usgs-landsat/`（实际数据存储）
  - `https://earth-search.aws.element84.com`（可选后端）
  - 默认**直连**。通过 `LANDSAT_DOWNLOAD_USE_PROXY=1` 走系统代理。
- **环境变量读取**：
  - `LANDSAT_DOWNLOAD_USE_PROXY=1` — 启用系统代理（默认直连，不走代理）
  - `LANDSAT_DOWNLOAD_QUIET=1` — 同时关闭进度条 + 隐私告示
  - `LANDSAT_DOWNLOAD_NO_STAC=1` — 跳过 STAC 搜索（仅用于已经预签名的资产列表）
  - `LANDSAT_DOWNLOAD_OUTPUT_DIR` — 覆盖默认 `--output-dir`
- **文件读取**：无（公开 STAC 数据）
- **文件写入**：当前工作目录的 `--output-dir`（默认 `./landsat_data`）

## Notes

- **Planetary Computer signing**：每个 `HREF` 都需要一次 SAS token 签名
  才能下载。脚本会缓存每个 collection 的 token（默认有效期 1 小时）以
  减少重复签名请求。
- **数据是公开的**：Landsat Collection 2 由 USGS 持有，公共领域。本
  skill 不绕过任何认证或访问控制。
- **STAC API** 是开放标准，详见 https://stacspec.org/。本 skill 用
  `requests` 直接拼 STAC JSON 请求，**不依赖** `pystac-client` /
  `planetary-computer` 等 SDK，保持依赖最小。
- **首次运行** 可能比较慢（Planetary Computer 冷启动 + token 签名）。
- **ClawHub 上的姊妹 skill**：[Sentinel Downloader](https://clawhub.ai/skills/sentinel-downloader-skill)
  使用相同的 STAC + `.part` + 进度条模式。

## License

MIT-0 — 详见 [LICENSE](./LICENSE)。
Landsat Collection 2 数据由 USGS 持有，公共领域（public domain）。
本 skill 仅做只读搜索 + 下载公共数据。
