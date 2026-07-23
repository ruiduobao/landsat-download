# 更新日志

所有显著的改动都记录在此。版本号遵循 [语义化版本](https://semver.org/)。

## [0.1.1] — 2026-07-23

### Bug 修复
- **AWS STAC 400 错误**：`sortby: [{field: "datetime", ...}]` 在 AWS Earth Search
  的 `landsat-c2-l2` collection 上不支持（索引无 datetime 排序字段）。修复：
  只在 Planetary Computer 后端发 `sortby`，AWS 后端跳过。
- **Skip-existing 不可见**：`download_asset` 命中"已存在则跳过"分支时只在返回值里
  有消息，stderr 不打印。修复：非 quiet 模式打印一行
  `↳ red.tif already exists, skipping`，方便用户看到重跑时的行为。
- **测试 bug（`tests/test_download.py` 旧版 + `_test_20_cases.py`）**：
  - 旧 `test_download_asset_404_does_not_overwrite` 预先创建了 final 文件，
    被"已存在则跳过"早返回挡了，未真正测试 404 不创建文件的行为。改名为
    `test_download_asset_404_does_not_create_file` 并去掉 pre-create。
  - `_test_20_cases.py` case 14 找文件路径少一层（应在
    `output_dir/<scene_id>/red.tif` 而非 `output_dir/red.tif`）。用
    `rglob('*.tif')` 修。
  - `_test_20_cases.py` case 15 测试用 `--quiet` 屏蔽了 skip 打印。去掉。

### 新增
- `_test_20_cases.py`：20 个真实网络 e2e 测试（覆盖搜索 / 下载 / 边界 / 错误），
  全部通过。详见 `_test_results.log`。
- 测试覆盖：
  - 4 个边界 case（缺参数 / 单天 / 全空 bbox / 无效日期）
  - 3 个跨场景（多平台 / WRS path+row / JSON 输出）
  - 3 个下载（单 band / RGB / skip-existing）
  - 1 个 --list-bands
  - 1 个 --quiet + 1 个 LANDSAT_DOWNLOAD_QUIET=1
  - 1 个 AWS 后端（实际可工作）
  - 6 个不同区域 / 时间窗口

### 验证
- 41/41 单元测试通过
- 20/20 真实网络 e2e 测试通过（用 Microsoft Planetary Computer）
- AWS Earth Search 后端可工作（下载未测，asset key 与 PC 略有差异，
  详见 `data/README.md` STAC ↔ USGS 对照表）

## [0.1.0] — 2026-07-23

### 新增
- 首次发布。
- **STAC 搜索** Landsat 8 / Landsat 9 Collection 2 Level 2 影像：
  - 默认后端：Microsoft Planetary Computer（公开，无需账号）
  - 可选后端：Element84 Earth Search（AWS Open Data）
- **过滤能力**：
  - `--bbox` 地理范围
  - `--start-date` / `--end-date` 时间窗口
  - `--max-cloud-cover 0-100`
  - `--platform landsat-8|landsat-9|both`（默认 both）
  - `--path` / `--row` WRS-2 路径/行过滤
  - `--limit N` 限制返回条目
- **下载**：
  - `--download` 触发实际下载
  - `--bands` 选择要下载的资产（默认 SR_B2..SR_B7）
  - `--output-dir` 下载目录
  - `.part` 临时文件保护，失败不覆盖已有文件
- **可视化进度**：
  - 已知文件大小：进度条 + 百分比 + 已下载/总大小 + 瞬时速度 + ETA
  - 未知文件大小：动态下载状态 + 已下载大小 + 速度
- **输出格式**：
  - `text`（人类可读，默认）
  - `json`（程序化处理）
- **依赖最小**：只依赖 `requests>=2.28.0`，不引入 `pystac-client` / `planetary-computer` SDK
- **安全基线**（沿用 satellite_search v0.4.1）：
  - 公开 STAC 数据 + USGS 公共领域，模块 docstring 明确"不绕认证"
  - 无 anti-bot / stealth 代码
  - 无 LLM 依赖
  - `LANDSAT_DOWNLOAD_QUIET=1` 一次性关闭进度 + 隐私告示
- **双语文档**：SKILL.md / README.md 全部中英对照表
- **Bash 包装**：`./landsat-download.sh --check-deps` 自动检查依赖
- **测试**：tests/ 覆盖搜索、下载、i18n、参数解析
