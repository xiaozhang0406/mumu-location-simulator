import os
import sys
import glob
import json
import shutil
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.widgets import Slider, Button
import numpy as np

# 新增 tkinter 导入（放在文件顶部附近），但为了兼容性在函数内部处理 tkinter 初始化
import tkinter as _tk
from tkinter import simpledialog as _simpledialog

def find_geojson_files(base_dir):
    pattern = os.path.join(base_dir, '..', 'path', '*.geojson')
    return sorted(glob.glob(pattern))

def load_geojson(path):
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    # Try to extract the first coordinate sequence we can edit (list of [lon, lat])
    # Support: FeatureCollection -> Feature -> geometry, or raw geometry, or list of coords.
    def extract_coords(obj):
        if isinstance(obj, dict):
            t = obj.get('type', '').lower()
            if t == 'featurecollection':
                for feat in obj.get('features', []):
                    res = extract_coords(feat)
                    if res: return res
            if t == 'feature':
                return extract_coords(obj.get('geometry', {}))
            if t in ('linestring', 'polygon'):
                return obj.get('coordinates')
            if t == 'multilinestring':
                # flatten to single sequence (choose first part)
                coords = obj.get('coordinates', [])
                return coords[0] if coords else None
            # raw geometry-like
            if 'coordinates' in obj:
                return obj['coordinates']
        if isinstance(obj, list):
            # If it's a list of coordinate pairs, detect shape: [ [lon, lat], ... ]
            if len(obj) and isinstance(obj[0], list) and len(obj[0]) >= 2 and all(isinstance(v, (int, float)) for v in obj[0][:2]):
                return obj
            # maybe first element contains coords
            for item in obj:
                res = extract_coords(item)
                if res: return res
        return None

    coords = extract_coords(data)
    if coords is None:
        raise ValueError("无法在 GeoJSON 中找到坐标数组")
    return data, coords

def save_geojson(original_data, coords_ref, out_path, backup=True):
    # Update first occurrence of coords in original_data with coords_ref
    def replace_coords(obj):
        if isinstance(obj, dict):
            if 'coordinates' in obj and isinstance(obj['coordinates'], list):
                # Heuristic: replace the first coordinates list that matches length
                if len(obj['coordinates']) == len(coords_ref) or True:
                    obj['coordinates'] = coords_ref
                    return True
            for k, v in obj.items():
                if replace_coords(v):
                    return True
        if isinstance(obj, list):
            for i, item in enumerate(obj):
                if replace_coords(item):
                    return True
        return False

    data_copy = original_data
    replaced = replace_coords(data_copy)
    if not replaced:
        raise RuntimeError("保存失败，未能替换坐标")
    if backup and os.path.exists(out_path):
        bak = out_path + '.bak'
        shutil.copy2(out_path, bak)
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(data_copy, f, ensure_ascii=False, indent=2)

class DraggablePath:
    def __init__(self, coords, ax, marker_size=50, line_width=2.0):
        # coords: list of [lon, lat]
        self.coords = np.array(coords, dtype=float)
        self.ax = ax
        self.marker_size = marker_size
        self.line_width = line_width

        self.line, = ax.plot(self.coords[:,0], self.coords[:,1], '-o', picker=5, color='C0',
                             linewidth=self.line_width, markersize=6)
        self.scat = ax.scatter(self.coords[:,0], self.coords[:,1], s=self.marker_size, color='C1', zorder=5)
        self.cid_press = self.line.figure.canvas.mpl_connect('button_press_event', self.on_press)
        self.cid_release = self.line.figure.canvas.mpl_connect('button_release_event', self.on_release)
        self.cid_motion = self.line.figure.canvas.mpl_connect('motion_notify_event', self.on_motion)
        self._dragging_index = None

    def on_press(self, event):
        if event.inaxes != self.ax:
            return
        # find nearest point
        xy = np.array([event.xdata, event.ydata])
        dist = np.hypot(self.coords[:,0] - xy[0], self.coords[:,1] - xy[1])
        idx = np.argmin(dist)
        if dist[idx] < 0.005:  # threshold in degrees; adjust as needed
            self._dragging_index = int(idx)

    def on_motion(self, event):
        if self._dragging_index is None:
            return
        if event.inaxes != self.ax:
            return
        # update point
        x, y = event.xdata, event.ydata
        if x is None or y is None:
            return
        self.coords[self._dragging_index, 0] = x
        self.coords[self._dragging_index, 1] = y
        self._redraw()

    def on_release(self, event):
        self._dragging_index = None

    def _redraw(self):
        self.line.set_data(self.coords[:,0], self.coords[:,1])
        self.scat.set_offsets(self.coords[:, :2])
        self.line.figure.canvas.draw_idle()

    def update_style(self, marker_size=None, line_width=None):
        if marker_size is not None:
            self.marker_size = marker_size
            self.scat.set_sizes([self.marker_size]*len(self.coords))
        if line_width is not None:
            self.line_width = line_width
            self.line.set_linewidth(self.line_width)
        self.line.figure.canvas.draw_idle()

    def get_coords_list(self):
        return self.coords.tolist()

def choose_file_interactive(files):
    if not files:
        print("未找到任何 ../path/*.geojson 文件")
        sys.exit(1)
    if len(files) == 1:
        print("找到文件:", files[0])
        return files[0]
    print("找到多个文件，输入要打开的序号：")
    for i, f in enumerate(files):
        print(f"{i}: {f}")
    while True:
        s = input("序号> ").strip()
        if s.isdigit():
            idx = int(s)
            if 0 <= idx < len(files):
                return files[idx]
        print("无效输入，请重试。")

def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    files = find_geojson_files(base_dir)
    chosen = choose_file_interactive(files)

    data, coords = load_geojson(chosen)
    # coords might be nested (e.g., polygon -> list of rings); try to pick a simple list of pairs
    if not coords or not isinstance(coords[0], (list, tuple)) or len(coords[0]) < 2:
        raise ValueError("Parsed coordinates format is not supported. Expect list of [lon, lat]")

    # Create plot
    fig, ax = plt.subplots(figsize=(10, 6))
    plt.subplots_adjust(left=0.1, bottom=0.25)
    ax.set_title(f"Edit: {os.path.basename(chosen)} — drag points to modify coordinates")

    dp = DraggablePath(coords, ax)

    # Sliders for marker size and line width
    axcolor = 'lightgoldenrodyellow'
    ax_marker = plt.axes([0.15, 0.12, 0.65, 0.03], facecolor=axcolor)
    ax_line = plt.axes([0.15, 0.07, 0.65, 0.03], facecolor=axcolor)

    s_marker = Slider(ax_marker, 'Marker Size', 10, 200, valinit=dp.marker_size)
    s_line = Slider(ax_line, 'Line Width', 0.5, 10.0, valinit=dp.line_width)

    def update_marker(val):
        dp.update_style(marker_size=s_marker.val)
    def update_line(val):
        dp.update_style(line_width=s_line.val)
    s_marker.on_changed(update_marker)
    s_line.on_changed(update_line)

    # Save button
    ax_save = plt.axes([0.82, 0.01, 0.15, 0.05])
    b_save = Button(ax_save, 'Save to file')

    def on_save(event):
        out_path = chosen
        new_coords = dp.get_coords_list()
        try:
            save_geojson(data, new_coords, out_path, backup=True)
            print(f"Saved and backed up: {out_path}.bak")
        except Exception as e:
            print("Save failed:", e)
    b_save.on_clicked(on_save)

    # Offset correction button (new)
    ax_offset = plt.axes([0.64, 0.01, 0.17, 0.05])
    b_offset = Button(ax_offset, 'Apply Offset')

    def parse_coord_str(s):
        # accepts "lon,lat" or "lon lat"
        if not s:
            return None
        s = s.strip()
        for sep in [',', ' ']:
            if sep in s:
                parts = [p for p in s.split(sep) if p!='']
                if len(parts) >= 2:
                    try:
                        lon = float(parts[0])
                        lat = float(parts[1])
                        return lon, lat
                    except:
                        return None
        # single token cannot parse
        return None

    def ask_coordinates_via_tk(prompt):
        try:
            root = _tk.Tk()
            root.withdraw()
            ans = _simpledialog.askstring("Input", prompt, parent=root)
            root.destroy()
            return ans
        except Exception:
            return None

    def ask_coordinates(prompt):
        # try tkinter dialog first
        s = ask_coordinates_via_tk(prompt)
        if s:
            return parse_coord_str(s)
        # fallback to console input
        try:
            s2 = input(prompt + " (format: lon,lat) > ")
        except Exception:
            s2 = None
        return parse_coord_str(s2) if s2 else None

    def on_offset(event):
        # prompt for calibration and corrected coordinates
        calib = ask_coordinates("Enter calibration coordinate (lon,lat)")
        if calib is None:
            print("Calibration coordinate not provided or invalid.")
            return
        corrected = ask_coordinates("Enter corrected coordinate (lon,lat)")
        if corrected is None:
            print("Corrected coordinate not provided or invalid.")
            return
        dx = corrected[0] - calib[0]
        dy = corrected[1] - calib[1]
        # apply offset to all points
        dp.coords[:,0] += dx
        dp.coords[:,1] += dy
        dp._redraw()
        print(f"Applied offset: dx={dx}, dy={dy} to all points.")

    b_offset.on_clicked(on_offset)

    # Initial autoscale with padding
    xs, ys = np.array(coords).T
    margin_x = (xs.max() - xs.min()) * 0.1 if xs.max() != xs.min() else 0.001
    margin_y = (ys.max() - ys.min()) * 0.1 if ys.max() != ys.min() else 0.001
    ax.set_xlim(xs.min() - margin_x, xs.max() + margin_x)
    ax.set_ylim(ys.min() - margin_y, ys.max() + margin_y)
    ax.set_xlabel('lon')
    ax.set_ylabel('lat')

    print("Instructions: click and drag points to modify coordinates; use sliders to adjust marker size and line width; click 'Save to file' to write back to GeoJSON (creates .bak backup).")
    plt.show()

if __name__ == '__main__':
    main()