# -*- coding: utf-8 -*-
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, Menu
import os
import requests
import threading
import time
import re
from bs4 import BeautifulSoup
import random
from datetime import datetime
from PIL import Image, UnidentifiedImageError, ImageTk # Added ImageTk
import io
import json
import webbrowser
import sys
import tkinterdnd2 # tkinterdnd2のインポート
import zipfile
import shutil
import subprocess
from parser.eh_parser import *
from config.settings import ToolTip
from config.constants import *
from gui.main_window import EHDownloader

if __name__ == "__main__":
    try:
        # Attempt to set DPI awareness for sharper UI on Windows
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1) # Argument 1 for Per_Monitor_Aware
    except Exception:
        # self.log("DPI Awareness設定失敗 (非Windowsまたは他の問題)。", "debug")
        print("DPI Awareness setting failed (non-Windows or other issue).")
    try:
        # DnD対応のTkinterウィンドウ作成（フォールバック付き）
        try:
            app_root = tkinterdnd2.Tk()
            print("Using tkinterdnd2.Tk for DnD support")
        except Exception as dnd_error:
            print(f"tkinterdnd2.Tk failed, using regular tk.Tk: {dnd_error}")
            import tkinter as tk
            app_root = tk.Tk()
        
        downloader_app = EHDownloader(app_root)
        app_root.mainloop()
    except KeyboardInterrupt:
        print("アプリケーションが中断されました。")
    except Exception as e:
        print(f"予期しないエラーが発生しました: {e}")
        import traceback
        traceback.print_exc()