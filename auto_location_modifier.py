import subprocess
import time
import json
import math
import os
import glob
import sys
import random
import argparse
import tempfile


def positive_number(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError(f'{name} 必须是大于 0 的有限数值')
    return value


def validate_points(points, name='path_points', require_path=False):
    if not isinstance(points, (list, tuple)):
        raise ValueError(f'{name} 必须是坐标列表')
    if require_path and len(points) < 2:
        raise ValueError(f'{name} 至少需要两个坐标点')
    for point in points:
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            raise ValueError(f'{name} 中每个点必须是 [经度, 纬度]')
        lon, lat = point
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) for value in point):
            raise ValueError(f'{name} 坐标必须是有限数值')
        if not -180 <= lon <= 180 or not -90 <= lat <= 90:
            raise ValueError(f'{name} 坐标超出经纬度范围')
    return points


def validate_config(config, require_path=False):
    if not isinstance(config, dict):
        raise ValueError('配置文件顶层必须是 JSON 对象')
    positive_number(config.get('interval', 1), 'interval')
    positive_number(config.get('max_distance', 5), 'max_distance')
    if not isinstance(config.get('loop', True), bool):
        raise ValueError('loop 必须是 true 或 false')
    vm = config.get('vm_indexes', 0)
    if vm != 'all' and (isinstance(vm, bool) or not isinstance(vm, int) or vm < 0):
        raise ValueError('vm_indexes 必须是非负整数或 all')
    manager = config.get('mumu_path', '')
    if not isinstance(manager, str) or not manager.strip():
        raise ValueError('mumu_path 必须是管理器文件路径')
    location = config.get('location', [])
    if location:
        validate_points([location], 'location')
    elif not isinstance(location, (list, tuple)):
        raise ValueError('location 必须是空列表或 [经度, 纬度]')
    validate_points(config.get('path_points', []), require_path=require_path)
    return config

def color_text(text, color_code):
    return f"\033[{color_code}m{text}\033[0m"

def print_progress_bar(iteration, total, length=30):
    percent = int(100 * (iteration / total))
    filled_len = int(length * iteration // total)
    bar = '█' * filled_len + '-' * (length - filled_len)
    print(f"\r{color_text('进度', '36')}: |{bar}| {percent}% ({iteration}/{total})", end='', flush=True)
    if iteration == total:
        print()  # 换行

def change_location(vm_indexes, longitude, latitude, mumu_path):
    cmd = [
        mumu_path,
        "control",
        "-v", str(vm_indexes),
        "tool", "location",
        "-lon", str(longitude),
        "-lat", str(latitude)
    ]
    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=15)
    except subprocess.TimeoutExpired as error:
        raise RuntimeError('MuMu 管理器超过 15 秒未响应，已停止本次模拟') from error
    except subprocess.CalledProcessError as error:
        raise RuntimeError(f'MuMu 管理器执行失败，退出码 {error.returncode}') from error
    except OSError as error:
        raise RuntimeError('无法启动 MuMu 管理器，请核对 mumu_path') from error

def euclidean_distance(lon1, lat1, lon2, lat2):
    return math.sqrt((lon2 - lon1) ** 2 + (lat2 - lat1) ** 2)

def interpolate_path(points, max_distance=5, loop=True):
    positive_number(max_distance, 'max_distance')
    validate_points(points)
    points = [tuple(point) for point in points]
    max_distance_deg = max_distance / 111000
    if len(points) < 2:
        return points
    new_points = [points[0]]
    n = len(points)
    last_index = n if not loop else n + 1
    for i in range(1, last_index):
        lon1, lat1 = new_points[-1]
        lon2, lat2 = points[i % n]
        dist = euclidean_distance(lon1, lat1, lon2, lat2)
        if dist <= max_distance_deg:
            new_points.append((lon2, lat2))
        else:
            num_insert = int(dist // max_distance_deg)
            if len(new_points) + num_insert + 1 > 100000:
                raise ValueError('插值点数超过 100000，请增大 max_distance 或缩短路径')
            for j in range(1, num_insert + 1):
                frac = j / (num_insert + 1)
                lon = lon1 + (lon2 - lon1) * frac
                lat = lat1 + (lat2 - lat1) * frac
                new_points.append((lon, lat))
            new_points.append((lon2, lat2))
    if not loop:
        return new_points
    if new_points[-1] == new_points[0]:
        new_points.pop()
    return new_points

def simulate_path(path_points, vm_indexes, interval, mumu_path):
    positive_number(interval, 'interval')
    validate_points(path_points, require_path=True)
    meters_to_deg = 1.0 / 111000.0

    total = len(path_points)
    # 每圈的基础偏移（米）
    base_dlon_m = random.uniform(-2.0, 2.0)
    base_dlat_m = random.uniform(-2.0, 2.0)
    base_dlon = base_dlon_m * meters_to_deg
    base_dlat = base_dlat_m * meters_to_deg

    for idx, (lon, lat) in enumerate(path_points):
        print_progress_bar(idx + 1, total)
        # 每个点的额外偏移（米）
        point_dlon_m = random.uniform(-0.5, 0.5)
        point_dlat_m = random.uniform(-0.5, 0.5)
        point_dlon = point_dlon_m * meters_to_deg
        point_dlat = point_dlat_m * meters_to_deg

        final_lon = lon + base_dlon + point_dlon
        final_lat = lat + base_dlat + point_dlat

        change_location(vm_indexes, final_lon, final_lat, mumu_path)
        if idx < total - 1:
            time.sleep(interval)

def load_path(max_distance=5, loop=True, location=None):
    try:
        geojson_path = resource_path('path.geojson')
        with open(geojson_path, 'r', encoding='utf-8') as f:
            geo = json.load(f)
        if geo.get('type') != 'FeatureCollection' or not geo.get('features'):
            raise ValueError('GeoJSON 必须包含非空的 FeatureCollection')
        geometry = geo['features'][0]['geometry']
        if geometry.get('type') != 'LineString':
            raise ValueError('第一个 Feature 必须是 LineString')
        coords = validate_points(geometry['coordinates'], 'GeoJSON', require_path=True)
        points = [(lon, lat) for lon, lat in coords]
        path_points = interpolate_path(points, max_distance=max_distance, loop=loop)
        if location and len(location) == 2:
            validate_points([location], 'location')
            lon0, lat0 = points[0]
            dlon = location[0] - lon0
            dlat = location[1] - lat0
            path_points = [(lon + dlon, lat + dlat) for lon, lat in path_points]
        validate_points(path_points, require_path=True)
        print("已从 path.geojson 读取路径点并修正位置。")
        return path_points
    except Exception as e:
        print("路径点加载失败，错误信息：", e)
        return []

def load_config():
    default_config = {
        "mumu_path": r"C:\Program Files\Netease\MuMu Player 12\shell\MuMuManager.exe",
        "vm_indexes": 0,
        "interval": 1,
        "max_distance": 5,
        "loop": True,
        "location": [],
        "path_points": []
    }

    # 配置文件保存在程序目录下，便于源码运行和打包后使用。
    config_dir = resource_path("conf")
    os.makedirs(config_dir, exist_ok=True)
    cfg_files = sorted(glob.glob(os.path.join(config_dir, "*.cfg")))
    config_file = None

    if not cfg_files:
        config_file = os.path.join(config_dir, "default.cfg")
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(default_config, f, ensure_ascii=False, indent=2)
        print(f"未找到 .cfg 配置文件，已生成默认配置文件：{config_file}")
    elif len(cfg_files) == 1:
        config_file = cfg_files[0]
        print(f"检测到配置文件：{config_file}")
    else:
        print("检测到多个配置文件：")
        for idx, fname in enumerate(cfg_files, 1):
            print(f"{idx}. {fname}")
        while True:
            sel = input(f"请选择要加载的配置文件（1-{len(cfg_files)}）：").strip()
            if sel.isdigit() and 1 <= int(sel) <= len(cfg_files):
                config_file = cfg_files[int(sel) - 1]
                break
            else:
                print("输入无效，请重新选择。")

    if config_file:
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                config = json.load(f)
            if not isinstance(config, dict):
                raise ValueError('配置文件顶层必须是 JSON 对象')
            default_config.update(config)
            validate_config(default_config)
        except Exception as e:
            raise ValueError(f'配置文件读取失败，请修复后重试：{config_file}；{e}') from e
    return default_config, config_file

def save_config(config, config_file):
    if not config_file:
        print("未指定配置文件，无法保存。")
        return False
    temporary_path = None
    try:
        validate_config(config)
        parent = os.path.dirname(os.path.abspath(config_file))
        fd, temporary_path = tempfile.mkstemp(prefix='.config-', suffix='.tmp', dir=parent)
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary_path, config_file)
        print(f"配置已保存到 {config_file}")
        return True
    except Exception as e:
        print("配置文件保存失败：", e)
        return False
    finally:
        if temporary_path and os.path.exists(temporary_path):
            os.remove(temporary_path)

def resource_path(relative_path):
    """获取程序目录中的外部资源，兼容源码和 PyInstaller 打包运行。"""
    if getattr(sys, 'frozen', False):
        base_path = os.path.dirname(sys.executable)
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)

def main():
    config, config_file = load_config()
    while True:
        print("\n==== 自动定位模拟器 ====")
        print("1. 开始模拟")
        print("2. 修改配置")
        print("3. 退出")
        choice = input("请选择操作（1-3）：").strip()
        if choice == "1":
            path_points = config["path_points"]
            if not path_points or len(path_points) < 2:
                print("路径点数量不足，请先在配置中设置路径点。")
                continue
            try:
                validate_config(config, require_path=True)
                if not os.path.isfile(config['mumu_path']):
                    raise ValueError('未找到 MuMu 管理器，请在配置中修改 mumu_path')
                if config.get("loop", True):
                    print("循环模式已开启，按 Ctrl+C 停止模拟。")
                    while True:
                        simulate_path(path_points, vm_indexes=config["vm_indexes"], interval=config["interval"], mumu_path=config["mumu_path"])
                else:
                    simulate_path(path_points, vm_indexes=config["vm_indexes"], interval=config["interval"], mumu_path=config["mumu_path"])
            except KeyboardInterrupt:
                print("\n模拟已停止。")
            except (ValueError, RuntimeError) as error:
                print(color_text(str(error), '31'))
        elif choice == "2":
            while True:
                print("\n--- 当前配置 ---")
                print(f"1. 管理器路径：{config['mumu_path']}")
                print(f"2. 模拟器索引：{config['vm_indexes']}")
                print(f"3. 移动间隔秒数：{config['interval']}")
                print(f"4. 插值最大间距(米)：{config['max_distance']}")
                print(f"5. 是否循环路径：{'是' if config['loop'] else '否'}")
                print("6. 重设路径")
                print("7. 保存配置并返回")
                cfg_choice = input("请输入要修改的编号(1-7)：").strip()
                if cfg_choice == "1":
                    new_path = input("请输入模拟器管理器路径：").strip()
                    if new_path:
                        config["mumu_path"] = new_path
                elif cfg_choice == "2":
                    new_vm = input("请输入模拟器索引（如0或all）：").strip()
                    if new_vm:
                        if new_vm.isdigit() or new_vm == 'all':
                            config["vm_indexes"] = int(new_vm) if new_vm.isdigit() else new_vm
                        else:
                            print('模拟器索引必须是非负整数或 all，未修改。')
                elif cfg_choice == "3":
                    new_interval = input("请输入移动间隔秒数：").strip()
                    if new_interval:
                        try:
                            config["interval"] = positive_number(float(new_interval), 'interval')
                        except:
                            print("输入无效，未修改。")
                elif cfg_choice == "4":
                    new_dist = input("请输入插值最大间距（米）：").strip()
                    if new_dist:
                        try:
                            config["max_distance"] = positive_number(float(new_dist), 'max_distance')
                        except:
                            print("输入无效，未修改。")
                        loaded = load_path(max_distance=config["max_distance"], loop=config["loop"], location=config.get("location", []))
                        if loaded:
                            config["path_points"] = loaded
                elif cfg_choice == "5":
                    new_loop = input("是否循环路径？(y/n)：").strip().lower()
                    if new_loop in ["y", "n"]:
                        config["loop"] = (new_loop == "y")
                        loaded = load_path(max_distance=config["max_distance"], loop=config["loop"], location=config.get("location", []))
                        if loaded:
                            config["path_points"] = loaded
                elif cfg_choice == "6":
                    print("请通过 https://geojson.io/#map=2/0/20 获取 path.geojson 文件并放在当前目录下。")
                    ref = input("请输入参考坐标（格式：经度,纬度）：").strip()
                    try:
                        lon, lat = map(float, ref.split(","))
                        validate_points([(lon, lat)], 'location')
                        config["location"] = [lon, lat]
                    except Exception:
                        print("输入格式错误，未修改参考坐标。")
                    loaded = load_path(max_distance=config["max_distance"], loop=config["loop"], location=config.get("location", []))
                    if loaded:
                        config["path_points"] = loaded
                elif cfg_choice == "7":
                    if save_config(config, config_file):
                        break
                else:
                    print("无效选择，请重新输入。")
        elif choice == "3":
            print("已退出。")
            break
        else:
            print("无效选择，请重新输入。")

def cli(argv=None):
    parser = argparse.ArgumentParser(description='MuMu 路径模拟与离线配置校验')
    parser.add_argument('--check-config', metavar='FILE', help='只校验 JSON 配置，不启动模拟器、不修改文件')
    args = parser.parse_args(argv)
    try:
        if args.check_config:
            with open(args.check_config, encoding='utf-8') as stream:
                config = json.load(stream)
            validate_config(config)
            print(f"配置校验通过，路径点数：{len(config.get('path_points', []))}")
        else:
            main()
    except (ValueError, OSError) as error:
        print(f'错误：{error}', file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(cli())
