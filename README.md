# 自动定位模拟器

使用 MuMu Player 12 的 `MuMuManager.exe`，按配置中的路径点移动模拟器位置。主程序只使用 Python 标准库；绘图工具需要额外依赖。

## 运行

1. 在 Windows 上安装 MuMu Player 12，并按需要修改配置中的 `mumu_path`。
2. 把 `path.example.geojson` 复制为 `path.geojson`，再将其中的示例坐标换成自己的路径。
3. 运行 `python auto_location_modifier.py`。首次运行会生成 `conf/default.cfg`。
4. 在菜单中选择“修改配置” → “重设路径”，根据提示设置参考坐标并生成路径点，然后保存配置并开始模拟。

也可以把 `conf/example.cfg.example` 复制为 `conf/自定义名称.cfg`，自行编辑参数和 `path_points`。如果有多个 `.cfg` 文件，启动时会要求选择。`interval` 为两次更新之间的秒数，`max_distance` 为插值时相邻点的最大间距（米）。

`path.geojson` 需要是首个 `Feature` 的 `LineString` 坐标数组，形如 `[[经度, 纬度], ...]`。绘图工具可用以下命令安装依赖并运行：

```bash
python -m pip install -r requirements-draw.txt
python utils/draw.py
python utils/path_drawing.py conf/default.cfg
```

如需打包，可安装 PyInstaller 后运行 `pyinstaller auto_location_modifier.spec`。配置目录和 `path.geojson` 是外部文件，应放在生成的可执行文件旁边；首次运行会创建配置目录和默认配置。

本地配置、路径文件和构建产物已加入 `.gitignore`，可直接在项目目录中使用。

## 离线校验与稳定性

无需安装或启动 MuMu 即可检查配置：

```bash
python auto_location_modifier.py --check-config conf/example.cfg.example
python -m unittest discover -s tests -v
```

配置校验会检查间隔/间距为正的有限数值、经纬度范围、模拟器索引及坐标结构。空路径的模板可通过格式校验，开始模拟前仍要求至少两个路径点以及存在的管理器程序。

配置保存先写临时文件，再原子替换；写入失败保留原文件。坏配置不会被静默替换成默认值，加载失败的路径也不会清空已存路径。MuMu 命令最多等待 15 秒，失败后停止本轮并返回菜单，非循环模式也可用 Ctrl+C 停止。

插值超过 100000 点时会拒绝生成，避免极小间距导致大量内存分配。距离换算仍使用原来的近似算法，不能视作精确测绘结果。

自动测试使用合成坐标和模拟进程，不调用真实 MuMu；真实版本兼容性需在本机管理器中另行验证。
