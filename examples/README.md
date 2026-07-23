# Examples

## 1. 搜索北京周边 2024 年云量 < 20% 的 Landsat 9 影像

```bash
python landsat-download.py \
    --bbox 116.0 39.5 116.8 40.2 \
    --start-date 2024-01-01 \
    --end-date 2024-12-31 \
    --max-cloud-cover 20 \
    --platform landsat-9
```

## 2. 搜索 + 下载全国 2020 年云量 < 10% 的 Landsat 8 影像（按 WRS 路径/行）

```bash
# 全国覆盖需要分块下载；这里以一条 path/row 为例
python landsat-download.py \
    --bbox 100.0 30.0 110.0 35.0 \
    --start-date 2020-06-01 \
    --end-date 2020-09-30 \
    --max-cloud-cover 10 \
    --platform landsat-8 \
    --path 130 --row 36 \
    --download \
    --output-dir ./data
```

## 3. 只下载 RGB（红 / 绿 / 蓝）

```bash
python landsat-download.py \
    --bbox 121.0 30.5 122.0 31.5 \
    --start-date 2024-03-01 \
    --end-date 2024-06-30 \
    --max-cloud-cover 30 \
    --bands red green blue \
    --download
```

## 4. JSON 输出供程序化处理

```bash
python landsat-download.py \
    --bbox 116.0 39.0 117.0 40.0 \
    --start-date 2024-01-01 \
    --end-date 2024-12-31 \
    --output-format json | jq '.scenes[0]'
```

## 5. CI / 自动化环境（关闭进度 + 隐私告示）

```bash
LANDSAT_DOWNLOAD_QUIET=1 python landsat-download.py \
    --bbox 116.0 39.0 117.0 40.0 \
    --start-date 2024-01-01 \
    --end-date 2024-12-31 \
    --no-progress \
    --download \
    --output-dir /var/data/landsat
```

## 6. AWS 后端（仅在 Planetary Computer 不可用时）

```bash
python landsat-download.py \
    --bbox 116.0 39.0 117.0 40.0 \
    --start-date 2024-01-01 \
    --end-date 2024-12-31 \
    --source aws \
    --download
```
