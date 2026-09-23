"""显示指定配置文件中的路径点。"""

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt


def main():
    parser = argparse.ArgumentParser(description="绘制配置文件中的轨迹")
    parser.add_argument("config", type=Path, help="包含 path_points 的 .cfg 文件")
    args = parser.parse_args()

    with args.config.open("r", encoding="utf-8") as file:
        config = json.load(file)
    path_points = config.get("path_points", [])
    if not path_points:
        parser.error("配置文件中未找到路径点")

    lons, lats = zip(*path_points)
    plt.figure(figsize=(8, 6))
    plt.plot(lons, lats, marker="o", color="b", linestyle="-", label="轨迹")
    plt.scatter(lons, lats, color="r")
    for index, (lon, lat) in enumerate(path_points, 1):
        plt.text(lon, lat, str(index), fontsize=9, ha="right")
    plt.title("路径点轨迹")
    plt.xlabel("经度")
    plt.ylabel("纬度")
    plt.legend()
    plt.grid(True)
    plt.axis("equal")
    plt.show()


if __name__ == "__main__":
    main()
