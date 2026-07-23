# Landsat Downloader · Landsat 8/9 影像下载器

> 通过 STAC 搜索和下载 **Landsat 8 / Landsat 9** Collection 2 Level 2 影像。
> 默认后端是 **Microsoft Planetary Computer**（公开数据，无需账号）。
> MIT-0 开源。

## 为什么做这个

做遥感时常需要 Landsat 数据来算 NDVI / NDBI / 时序变化 / 长时序土地利用。
USGS EarthExplorer 流程繁琐，AWS Open Data 需要凭证，GEE 需要注册——
大部分用户卡在"先把数据下下来"这一步。

本 skill 沿用 [Sentinel Downloader](https://clawhub.ai/skills/sentinel-downloader-skill)
的架构（STAC + 单文件 CLI + 可视化进度 + `.part` 安全写入），但适配
Landsat 8/9 的元数据约定（WRS-2 路径/行、Collection 2 Level 2 资产命名、
`eo:cloud_cover` 云量字段）。

## Quickstart

```bash
# 1) 安装依赖
pip install 'requests>=2.28.0'

# 2) 搜索 Landsat 8/9 影像（仅查询，不下载）
python landsat-download.py \
    --bbox 116.0 39.0 117.0 40.0 \
    --start-date 2024-01-01 \
    --end-date 2024-12-31

# 3) 限制云量 + 实际下载
python landsat-download.py \
    --bbox 116.0 39.0 117.0 40.0 \
    --start-date 2024-01-01 \
    --end-date 2024-12-31 \
    --max-cloud-cover 20 \
    --download \
    --output-dir ./data
```

## 数据源

| 后端 | URL | 凭证 |
|---|---|---|
| **Planetary Computer**（默认） | `https://planetarycomputer.microsoft.com/api/stac/v1/` | 无 |
| AWS Earth Search | `https://earth-search.aws.element84.com/v1/` | 无 |

> **License** — Landsat Collection 2 由 USGS 持有，**公共领域**。

## 支持的卫星任务

| 任务 | 卫星 | 发射 | 传感器 | 空间分辨率 |
|---|---|---|---|---|
| **Landsat 8** | LDCM | 2013-02-11 | OLI / TIRS | 30 m multispectral, 15 m pan, 100 m thermal |
| **Landsat 9** | Landsat 9 | 2021-09-27 | OLI-2 / TIRS-2 | 同 Landsat 8 |

## 默认下载波段

| 资产 | 含义 (USGS) | 波长 | 分辨率 |
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

## 参数一览

| 参数 | 说明 | 必填 |
|---|---|---|
| `--bbox` | 地理范围 `[minLon minLat maxLon maxLat]` | ✅ |
| `--start-date` | 开始日期 `YYYY-MM-DD` | ✅ |
| `--end-date` | 结束日期 `YYYY-MM-DD` | ✅ |
| `--platform` | `landsat-8` / `landsat-9` / `both` | ❌ |
| `--max-cloud-cover` | 最大云量 0–100 | ❌ |
| `--path` | WRS-2 路径号 | ❌ |
| `--row` | WRS-2 行号 | ❌ |
| `--limit` | 限制返回条目数 | ❌ |
| `--bands` | 下载的资产列表 | ❌ |
| `--download` | 触发实际下载 | ❌ |
| `--output-dir` | 下载目录 | ❌ |
| `--output-format` | `text` / `json` | ❌ |
| `--source` | `pc`（默认）/ `aws` | ❌ |

## 下载进度

```
[landsat-download] downloading LC09_L2SP_122033_20240831_02_T1
  ↳ red.tif     10.2 MB ┃████████████░░░░░░░░░░░░░░░░░░░░░░░░│  38%  2.1 MB/s  ETA 0:00:03
  ↳ green.tif    8.9 MB ┃██████████████████████████████░░░░│  92%  2.3 MB/s  ETA 0:00:00
  ✔ 6/6 assets downloaded (62.4 MB) in 28s
```

`.part` 临时文件保护：失败会清除临时文件，**不会覆盖**已有的最终文件。

## 与 Sentinel Downloader 的差异

| 维度 | Sentinel | Landsat |
|---|---|---|
| 后端 | `sentinel-2-l2a` / `sentinel-1-grd` / `sentinel-5p-l2` | `landsat-c2-l2`（涵盖 Landsat 4–9） |
| 元数据 | MGRS tile ID | WRS-2 路径/行 |
| 默认波段 | B02/B03/B04/B08 | red/green/blue/nir08/swir16/swir22 |
| 云量字段 | `eo:cloud_cover`（仅 S2） | `eo:cloud_cover`（所有平台） |
| 平台过滤 | `--mission sentinel-1/2/5p` | `--platform landsat-8/9/both` |
| 高级过滤 | 无 | `--path --row`（WRS-2） |

## 详细文档

详见 [SKILL.md](./SKILL.md) — 含完整的参数说明、输出示例、STAC 端点、Permissions。

## License

MIT-0（详见 [LICENSE](./LICENSE)）。
Landsat Collection 2 数据 © USGS，公共领域（public domain）。
