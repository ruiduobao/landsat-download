# data/ 目录

默认下载目录是 `./landsat_data/`，**不是** `data/`。本目录保留为空，
仅用于存放本地 fixture / scratch 数据。

## 资产说明

Landsat Collection 2 Level 2 science products 在 Planetary Computer STAC
中暴露的资产 key（用 `--bands` 指定）：

| STAC asset | USGS Collection 2 文件 | 含义 | 波长 | 分辨率 |
|---|---|---|---|---|
| `coastal` | `SR_B1.TIF` | Coastal Aerosol | 0.43–0.45 µm | 30 m |
| `blue` | `SR_B2.TIF` | Blue | 0.45–0.51 µm | 30 m |
| `green` | `SR_B3.TIF` | Green | 0.53–0.60 µm | 30 m |
| `red` | `SR_B4.TIF` | Red | 0.64–0.67 µm | 30 m |
| `nir08` | `SR_B5.TIF` | NIR | 0.85–0.88 µm | 30 m |
| `swir16` | `SR_B6.TIF` | SWIR1 | 1.57–1.65 µm | 30 m |
| `swir22` | `SR_B7.TIF` | SWIR2 | 2.11–2.29 µm | 30 m |
| `lwir11` | `ST_B10.TIF` | Thermal | 10.60–11.19 µm | 100 m |
| `qa` | `QA_PIXEL.TIF` | Cloud / Snow / Water mask | — | — |
| `drad` | `ST_DRAD.TIF` | Downwelled Radiance | — | — |
| `urad` | `ST_URAD.TIF` | Upwelled Radiance | — | — |
| `atran` | `ST_ATRAN.TIF` | Atmospheric Transmittance | — | — |
| `cdist` | `ST_CDIST.TIF` | Cloud Distance | — | — |
| `emis` | `ST_EMIS.TIF` | Emissivity | — | — |
| `emsd` | `ST_EMSD.TIF` | Emissivity Stddev | — | — |
| `trad` | `ST_TRAD.TIF` | Thermal Radiance | — | — |
| `mtl.txt` | `*_MTL.txt` | Metadata (text) | — | — |
| `mtl.xml` | `*_MTL.xml` | Metadata (XML) | — | — |
| `ang` | `*_ANG.txt` | Angle Coefficients | — | — |

> 全部 STAC asset 详见 https://planetarycomputer.microsoft.com/dataset/landsat-c2-l2
> 或运行 `python landsat-download.py --list-bands`。

## License

Landsat Collection 2 由 USGS 持有，**公共领域**（public domain）。
可自由使用、复制、传输、重新分发，无需署名。

