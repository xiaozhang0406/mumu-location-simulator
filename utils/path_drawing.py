import matplotlib.pyplot as plt
import json

CONFIG_FILE = ""

with open(CONFIG_FILE, "r", encoding="utf-8") as f:
    config = json.load(f)

path_points = config.get("path_points", [])

if not path_points:
    print("配置文件中未找到路径点。")
    exit(1)

lons, lats = zip(*path_points)

plt.figure(figsize=(8, 6))
plt.plot(lons, lats, marker='o', color='b', linestyle='-', label='轨迹')
plt.scatter(lons, lats, color='r')
for i, (lon, lat) in enumerate(path_points):
    plt.text(lon, lat, str(i+1), fontsize=9, ha='right')

plt.title('路径点轨迹')
plt.xlabel('经度')
plt.ylabel('纬度')
plt.legend()
plt.grid(True)
plt.axis('equal')
plt.show()