import subprocess
import time
import json
import math
import os
import glob
import sys
import requests
from datetime import datetime

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
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        # print("命令执行成功")
        pass
    except subprocess.CalledProcessError as e:
        print(color_text("命令执行失败", '31'))

def euclidean_distance(lon1, lat1, lon2, lat2):
    return math.sqrt((lon2 - lon1) ** 2 + (lat2 - lat1) ** 2)

def interpolate_path(points, max_distance=5, loop=True):
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
    total = len(path_points)
    for idx, (lon, lat) in enumerate(path_points):
        print_progress_bar(idx + 1, total)
        # 可选：显示当前坐标
        # print(f"坐标 {idx+1}/{total}: 经度 {lon}, 纬度 {lat}")
        change_location(vm_indexes, lon, lat, mumu_path)
        if idx < total - 1:
            time.sleep(interval)

def load_path(max_distance=5, loop=True, location=None):
    try:
        geojson_path = resource_path('path.geojson')
        with open(geojson_path, 'r', encoding='utf-8') as f:
            geo = json.load(f)
        coords = geo['features'][0]['geometry']['coordinates']
        points = [(lon, lat) for lon, lat in coords]
        path_points = interpolate_path(points, max_distance=max_distance, loop=loop)
        if location and len(location) == 2:
            lon0, lat0 = points[0]
            dlon = location[0] - lon0
            dlat = location[1] - lat0
            path_points = [(lon + dlon, lat + dlat) for lon, lat in path_points]
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

    # 查找所有 .cfg 文件
    cfg_files = glob.glob("conf/*.cfg")
    config_file = None

    if not cfg_files:
        config_file = "default.cfg"
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
            config_path = resource_path(config_file)
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
            default_config.update(config)
        except Exception as e:
            print("配置文件读取失败，使用默认配置。")
    return default_config, config_file

def save_config(config, config_file):
    if not config_file:
        print("未指定配置文件，无法保存。")
        return
    try:
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        print(f"配置已保存到 {config_file}")
    except Exception as e:
        print("配置文件保存失败：", e)

def get_network_time():
    apis = [
        "http://worldtimeapi.org/api/timezone/Etc/UTC",
        "http://quan.suning.com/getSysTime.do",  # 苏宁时间API
        "http://api.m.taobao.com/rest/api3.do?api=mtop.common.getTimestamp",  # 淘宝时间API
    ]
    for api in apis:
        try:
            resp = requests.get(api, timeout=5)
            resp.raise_for_status()
            if "worldtimeapi" in api:
                utc_time_str = resp.json()["utc_datetime"]
                return datetime.fromisoformat(utc_time_str.replace("Z", "+00:00"))
            elif "suning" in api:
                # 返回格式：{"sysTime2":"2024-06-24 17:00:00"}
                return datetime.strptime(resp.json()["sysTime2"], "%Y-%m-%d %H:%M:%S")
            elif "taobao" in api:
                # 返回格式：{"data":{"t":"1720000000000"}}
                ts = int(resp.json()["data"]["t"]) // 1000
                return datetime.fromtimestamp(ts)
        except Exception:
            continue
    return None

def check_network_time():
    return
    current_time = get_network_time()
    deadline = datetime(2025, 7, 15)
    if not current_time:
        print("无法联网，请重试。")
        sys.exit(1)
    if current_time > deadline:
        print("虚拟机api已过期，请更新程序。")
        sys.exit(1)

def resource_path(relative_path):
    """获取资源文件的绝对路径，兼容开发环境和 PyInstaller 打包后的环境"""
    if hasattr(sys, '_MEIPASS'):
        # PyInstaller 打包后的临时目录
        base_path = sys._MEIPASS
    else:
        # 源码运行时的目录
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def main():
    check_network_time()
    config, config_file = load_config()
    cfg_path = resource_path('conf/sifang.cfg')
    with open(cfg_path, 'r', encoding='utf-8') as f:
        # 你的读取逻辑
        ...
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
            if config.get("loop", True):
                print("循环模式已开启，按 Ctrl+C 停止模拟。")
                try:
                    while True:
                        simulate_path(path_points, vm_indexes=config["vm_indexes"], interval=config["interval"], mumu_path=config["mumu_path"])
                except KeyboardInterrupt:
                    print("\n模拟已停止。")
            else:
                simulate_path(path_points, vm_indexes=config["vm_indexes"], interval=config["interval"], mumu_path=config["mumu_path"])
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
                        config["vm_indexes"] = int(new_vm) if new_vm.isdigit() else new_vm
                elif cfg_choice == "3":
                    new_interval = input("请输入移动间隔秒数：").strip()
                    if new_interval:
                        try:
                            config["interval"] = float(new_interval)
                        except:
                            print("输入无效，未修改。")
                elif cfg_choice == "4":
                    new_dist = input("请输入插值最大间距（米）：").strip()
                    if new_dist:
                        try:
                            config["max_distance"] = float(new_dist)
                        except:
                            print("输入无效，未修改。")
                        config["path_points"] = load_path(max_distance=config["max_distance"], loop=config["loop"], location=config.get("location", []))
                elif cfg_choice == "5":
                    new_loop = input("是否循环路径？(y/n)：").strip().lower()
                    if new_loop in ["y", "n"]:
                        config["loop"] = (new_loop == "y")
                        config["path_points"] = load_path(max_distance=config["max_distance"], loop=config["loop"], location=config.get("location", []))
                elif cfg_choice == "6":
                    print("请通过 https://geojson.io/#map=2/0/20 获取 path.geojson 文件并放在当前目录下。")
                    ref = input("请输入参考坐标（格式：经度,纬度）：").strip()
                    try:
                        lon, lat = map(float, ref.split(","))
                        config["location"] = [lon, lat]
                    except Exception:
                        print("输入格式错误，未修改参考坐标。")
                    config["path_points"] = load_path(max_distance=config["max_distance"], loop=config["loop"], location=config.get("location", []))
                elif cfg_choice == "7":
                    save_config(config, config_file)
                    break
                else:
                    print("无效选择，请重新输入。")
        elif choice == "3":
            print("已退出。")
            break
        else:
            print("无效选择，请重新输入。")

if __name__ == "__main__":
    main()