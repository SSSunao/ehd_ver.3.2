# -*- coding: utf-8 -*-
"""
Selenium安全弁ハンドラー - リトライ上限達成時のSelenium処理
"""

import traceback
import time
import os
import base64
from typing import Dict, Any, Optional
import requests

from core.interfaces import IStateManager, ILogger


class SeleniumFallbackHandler:
    """Selenium安全弁の処理を担当するハンドラー"""
    
    def __init__(self, state_manager: IStateManager, logger: ILogger, error_config: Dict[str, Any], error_stats: Dict[str, Any]):
        """
        初期化
        
        Args:
            state_manager: ステート管理インターフェース
            logger: ロガーインターフェース
            error_config: エラー設定
            error_stats: エラー統計
        """
        self.state_manager = state_manager
        self.logger = logger
        self.error_config = error_config
        self.error_stats = error_stats
    
    def execute_fallback(self, analysis: Dict[str, Any], context) -> bool:
        """
        Selenium安全弁を実行
        
        Args:
            analysis: エラー分析結果
            context: エラーコンテキスト
            
        Returns:
            bool: 成功した場合True
        """
        try:
            actual_retry_count = max(0, context.retry_count - 1)
            self.logger.log(f"[Selenium安全弁] リトライ上限達成。Seleniumで1回だけ再試行します (リトライ回数: {actual_retry_count})", "info")
            
            # stage_dataから画像URLと保存パスを取得
            stage_data = getattr(context, 'stage_data', {})
            image_url = stage_data.get('image_url', context.url)
            save_path = stage_data.get('save_path', None)
            
            if not image_url:
                self.logger.log("[Selenium安全弁] 画像URLが取得できませんでした", "warning")
                return False
            
            if not save_path:
                self.logger.log("[Selenium安全弁] 保存パスが取得できませんでした", "warning")
                return False
            
            self.logger.log(f"[Selenium安全弁] 画像URL: {image_url}", "debug")
            self.logger.log(f"[Selenium安全弁] 保存パス: {save_path}", "debug")
            
            # Selenium設定の取得
            selenium_config = self._get_selenium_config_for_error(analysis, context)
            
            # Seleniumドライバーの取得
            driver = self._get_selenium_driver_with_retry(selenium_config, max_retries=2)
            if not driver:
                self.logger.log("[Selenium安全弁] ドライバー取得に失敗しました。スキップします", "warning")
                return False
            
            try:
                # 画像URLにアクセス
                self.logger.log(f"[Selenium安全弁] 画像URLにアクセス中: {image_url[:100]}...", "debug")
                success = self._navigate_to_image_with_selenium(driver, image_url, selenium_config)
                if not success:
                    self.logger.log("[Selenium安全弁] 画像URLへのアクセスに失敗しました", "warning")
                    return False
                self.logger.log("[Selenium安全弁] 画像URLへのアクセス成功", "debug")
                
                # 画像データの取得
                self.logger.log("[Selenium安全弁] 画像データを取得中...", "debug")
                image_data = self._extract_image_data_with_selenium(driver, image_url)
                if not image_data:
                    self.logger.log("[Selenium安全弁] 画像データの取得に失敗しました", "warning")
                    return False
                
                # 画像データをファイルに保存
                self.logger.log(f"[Selenium安全弁] 画像データ取得成功: {len(image_data)} bytes", "debug")
                try:
                    # 保存先ディレクトリの存在確認
                    save_dir = os.path.dirname(save_path)
                    if not os.path.exists(save_dir):
                        os.makedirs(save_dir, exist_ok=True)
                        self.logger.log(f"[Selenium安全弁] 保存先ディレクトリを作成: {save_dir}", "debug")
                    
                    # 既存ファイルチェック
                    if os.path.exists(save_path):
                        self.logger.log(f"⏭️ Selenium: 既存ファイルスキップ - {os.path.basename(save_path)}", "info")
                        context.is_selenium_success = True
                        return True
                    
                    # 画像データをファイルに書き込む
                    with open(save_path, 'wb') as f:
                        f.write(image_data)
                    
                    self.logger.log(f"[Selenium安全弁] 画像保存完了: {os.path.basename(save_path)}", "info")
                    self.logger.log("✅ Selenium成功: 画像ダウンロード完了", "info")
                    context.is_selenium_success = True
                    return True
                    
                except Exception as save_error:
                    self.logger.log(f"[Selenium安全弁] 画像保存エラー: {save_error}", "error")
                    self.logger.log(f"[Selenium安全弁] 保存エラー詳細: {traceback.format_exc()}", "error")
                    return False
                
            finally:
                try:
                    driver.quit()
                except Exception:
                    pass
                    
        except Exception as e:
            self.logger.log(f"[Selenium安全弁] 実行エラー: {e}", "error")
            self.logger.log(f"[Selenium安全弁] 実行エラー詳細: {traceback.format_exc()}", "error")
            return False
    
    def _get_selenium_config_for_error(self, analysis: Dict[str, Any], context) -> Dict[str, Any]:
        """エラーに基づくSelenium設定の取得"""
        try:
            from core.errors import ErrorCategory
            category = analysis['category']
            
            configs = {
                ErrorCategory.NETWORK_TIMEOUT: {
                    'timeout': 60,
                    'wait_strategy': 'eager',
                    'retry_count': 2
                },
                ErrorCategory.NETWORK_RATE_LIMIT: {
                    'timeout': 120,
                    'wait_strategy': 'normal',
                    'retry_count': 1
                },
                ErrorCategory.NETWORK_SERVER_ERROR: {
                    'timeout': 45,
                    'wait_strategy': 'eager',
                    'retry_count': 3
                },
                ErrorCategory.PARSING: {
                    'timeout': 30,
                    'wait_strategy': 'normal',
                    'retry_count': 1
                },
                ErrorCategory.VALIDATION: {
                    'timeout': 30,
                    'wait_strategy': 'normal',
                    'retry_count': 1
                }
            }
            
            return configs.get(category, {
                'timeout': 30,
                'wait_strategy': 'normal',
                'retry_count': 1
            })
            
        except Exception as e:
            self.logger.log(f"Selenium設定取得エラー: {e}", "error")
            return {'timeout': 30, 'wait_strategy': 'normal', 'retry_count': 1}
    
    def _get_selenium_driver_with_retry(self, config: Dict[str, Any], max_retries: int = 3):
        """リトライ付きSeleniumドライバーの取得"""
        try:
            # Seleniumがインストールされているかチェック（遅延インポート）
            try:
                from selenium import webdriver
                from selenium.webdriver.chrome.service import Service
                from selenium.webdriver.chrome.options import Options
                from webdriver_manager.chrome import ChromeDriverManager
            except ImportError:
                self.logger.log("[Selenium安全弁] Seleniumがインストールされていません。リトライ上限達成時オプションに移行します", "warning")
                return None
            
            # Chromeがインストールされているかチェックし、パスを取得
            chrome_installed = False
            chrome_binary_path = None
            
            # カスタムChromeパスが指定されている場合はそれを使用
            if hasattr(self.state_manager, 'parent'):
                parent = self.state_manager.parent
                if parent:
                    custom_chrome_path = getattr(parent, 'selenium_chrome_path', None)
                    if custom_chrome_path and hasattr(custom_chrome_path, 'get'):
                        custom_path = custom_chrome_path.get().strip()
                        if custom_path and os.path.exists(custom_path):
                            chrome_binary_path = custom_path
                            chrome_installed = True
                            self.logger.log(f"[Selenium安全弁] カスタムChromeパスを使用: {chrome_binary_path}", "debug")
            
            # カスタムパスが指定されていない場合、自動検出
            if not chrome_binary_path:
                try:
                    import subprocess
                    result = subprocess.run(
                        ['reg', 'query', 'HKEY_CURRENT_USER\\Software\\Google\\Chrome\\BLBeacon', '/v', 'version'],
                        capture_output=True,
                        text=True,
                        timeout=2
                    )
                    if result.returncode == 0:
                        chrome_installed = True
                except:
                    pass
            
            # Chromeのパスを確認し、インストールを検証
            chrome_paths = [
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
            ]
            
            # レジストリからパスを取得
            try:
                import winreg
                try:
                    key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Google\Chrome\BLBeacon")
                    install_path, _ = winreg.QueryValueEx(key, "path")
                    winreg.CloseKey(key)
                    if install_path and os.path.exists(install_path):
                        chrome_paths.insert(0, install_path)
                except:
                    pass
                
                try:
                    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Google\Chrome\BLBeacon")
                    install_path, _ = winreg.QueryValueEx(key, "path")
                    winreg.CloseKey(key)
                    if install_path and os.path.exists(install_path):
                        chrome_paths.insert(0, install_path)
                except:
                    pass
            except:
                pass
            
            # Chromeのパスを確認
            if not chrome_installed:
                for path in chrome_paths:
                    if os.path.exists(path):
                        chrome_installed = True
                        chrome_binary_path = path
                        break
            else:
                for path in chrome_paths:
                    if os.path.exists(path):
                        chrome_binary_path = path
                        break
            
            # Chromeのインストールを検証
            use_registry_version = self.error_config.get('selenium_use_registry_version', True)
            if chrome_binary_path:
                is_valid, validation_msg = self._validate_chrome_installation(chrome_binary_path, use_registry_version)
                if not is_valid:
                    self.logger.log(f"[Selenium安全弁] Chromeの検証に失敗: {validation_msg}", "warning")
                    if os.path.exists(chrome_binary_path):
                        self.logger.log(f"[Selenium安全弁] Chrome実行ファイルは存在します。検証エラーを無視して続行します", "warning")
                    else:
                        chrome_binary_path = None
                else:
                    self.logger.log(f"[Selenium安全弁] {validation_msg}", "debug")
            
            if not chrome_binary_path:
                self.logger.log("[Selenium安全弁] Chromeがインストールされていません。リトライ上限達成時オプションに移行します", "warning")
                return None
            
            if chrome_binary_path:
                self.logger.log(f"[Selenium安全弁] Chromeブラウザパス: {chrome_binary_path}", "debug")
            
            # ドライバー取得を試行
            for attempt in range(max_retries):
                try:
                    # Chromeオプションの設定
                    chrome_options = Options()
                    
                    if chrome_binary_path:
                        chrome_options.binary_location = chrome_binary_path
                    
                    import tempfile
                    import shutil
                    
                    minimal_options = self.error_config.get('selenium_minimal_options', False)
                    test_minimal = self.error_config.get('selenium_test_minimal_options', False)
                    test_no_headless = self.error_config.get('selenium_test_no_headless', False)
                    cleanup_temp = self.error_config.get('selenium_cleanup_temp', False)
                    
                    if not minimal_options and not test_minimal:
                        user_data_dir = os.path.join(tempfile.gettempdir(), f"selenium_chrome_{os.getpid()}_{int(time.time() * 1000)}_{attempt}")
                        
                        if cleanup_temp:
                            temp_dir = tempfile.gettempdir()
                            cleanup_count = 0
                            try:
                                for item in os.listdir(temp_dir):
                                    item_path = os.path.join(temp_dir, item)
                                    if os.path.isdir(item_path) and item.startswith('selenium_chrome_'):
                                        try:
                                            shutil.rmtree(item_path, ignore_errors=True)
                                            cleanup_count += 1
                                        except:
                                            pass
                            except:
                                pass
                        
                        os.makedirs(user_data_dir, exist_ok=True)
                        chrome_options.add_argument(f"--user-data-dir={user_data_dir}")
                        
                        # リモートデバッグポートを指定
                        import random
                        import socket
                        import re
                        
                        used_ports = set()
                        try:
                            import psutil
                            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                                try:
                                    if 'chrome' in proc.info['name'].lower():
                                        cmdline = proc.info.get('cmdline', [])
                                        if cmdline:
                                            cmdline_str = ' '.join(cmdline)
                                            match = re.search(r'--remote-debugging-port=(\d+)', cmdline_str)
                                            if match:
                                                used_ports.add(int(match.group(1)))
                                except:
                                    pass
                        except:
                            pass
                        
                        remote_debugging_port = None
                        for _ in range(30):
                            port = random.randint(9000, 9999)
                            if port in used_ports:
                                continue
                            
                            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                            try:
                                sock.bind(('127.0.0.1', port))
                                sock.close()
                                remote_debugging_port = port
                                break
                            except:
                                sock.close()
                                continue
                        
                        if remote_debugging_port is None:
                            remote_debugging_port = 9222
                        
                        chrome_options.add_argument(f"--remote-debugging-port={remote_debugging_port}")
                    
                    # Chromeオプション
                    if minimal_options or test_minimal:
                        if not test_no_headless:
                            chrome_options.add_argument("--headless")
                        chrome_options.add_argument("--no-sandbox")
                        chrome_options.add_argument("--disable-dev-shm-usage")
                        chrome_options.add_argument("--disable-gpu")
                        chrome_options.add_argument("--window-size=1920,1080")
                    else:
                        if not test_no_headless:
                            chrome_options.add_argument("--headless")
                        chrome_options.add_argument("--no-sandbox")
                        chrome_options.add_argument("--disable-dev-shm-usage")
                        chrome_options.add_argument("--disable-gpu")
                        chrome_options.add_argument("--window-size=1920,1080")
                        chrome_options.add_argument("--disable-extensions")
                        chrome_options.add_argument("--disable-logging")
                    
                    # ドライバーの取得
                    use_selenium_manager = self.error_config.get('selenium_manager_enabled', False)
                    driver_path = None
                    
                    # カスタムドライバパスが指定されている場合はそれを使用
                    if hasattr(self.state_manager, 'parent'):
                        parent = self.state_manager.parent
                        if parent:
                            custom_driver_path = getattr(parent, 'selenium_driver_path', None)
                            if custom_driver_path and hasattr(custom_driver_path, 'get'):
                                custom_path = custom_driver_path.get().strip()
                                if custom_path and os.path.exists(custom_path):
                                    driver_path = os.path.normpath(custom_path)
                    
                    if not driver_path:
                        import threading
                        
                        # Chromeのバージョンを取得
                        chrome_version_str = None
                        try:
                            import winreg
                            try:
                                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Google\Chrome\BLBeacon")
                                chrome_version_str, _ = winreg.QueryValueEx(key, "version")
                                winreg.CloseKey(key)
                            except:
                                try:
                                    key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Google\Chrome\BLBeacon")
                                    chrome_version_str, _ = winreg.QueryValueEx(key, "version")
                                    winreg.CloseKey(key)
                                except:
                                    pass
                        except:
                            pass
                        
                        # 既存のChromeDriverを検索
                        existing_driver_path = None
                        try:
                            cache_path = os.path.join(os.path.expanduser("~"), ".wdm", "drivers", "chromedriver")
                            if os.path.exists(cache_path):
                                for root, dirs, files in os.walk(cache_path):
                                    for file in files:
                                        if file == "chromedriver.exe" or file == "chromedriver":
                                            candidate_path = os.path.join(root, file)
                                            if os.path.exists(candidate_path) and os.access(candidate_path, os.X_OK):
                                                existing_driver_path = candidate_path
                                                break
                                    if existing_driver_path:
                                        break
                        except:
                            pass
                        
                        if existing_driver_path:
                            driver_path = existing_driver_path
                        else:
                            install_error = None
                            
                            def install_driver():
                                nonlocal driver_path, install_error
                                try:
                                    if use_selenium_manager:
                                        driver_path = None
                                    else:
                                        driver_path = ChromeDriverManager().install()
                                except Exception as e:
                                    install_error = e
                            
                            install_thread = threading.Thread(target=install_driver, daemon=True)
                            install_thread.start()
                            install_thread.join(timeout=30)
                        
                            if install_thread.is_alive():
                                self.logger.log("[Selenium安全弁] ドライバ取得がタイムアウトしました（30秒）", "warning")
                                continue
                            
                            if install_error:
                                self.logger.log(f"[Selenium安全弁] ドライバ取得エラー: {install_error}", "error")
                                continue
                            
                            if not use_selenium_manager and not driver_path:
                                self.logger.log("[Selenium安全弁] ドライバ取得に失敗しました", "warning")
                                continue
                        
                        if driver_path:
                            driver_path = os.path.normpath(driver_path)
                    
                    if not use_selenium_manager:
                        if driver_path and not os.path.exists(driver_path):
                            self.logger.log(f"[Selenium安全弁] ChromeDriverが見つかりません: {driver_path}", "error")
                            continue
                        service = Service(driver_path)
                    else:
                        service = Service()
                    
                    # Chromeのバックグラウンドプロセスを停止
                    stop_chrome_bg = self.error_config.get('selenium_stop_chrome_background', False)
                    if stop_chrome_bg:
                        try:
                            import psutil
                            chrome_processes = [p for p in psutil.process_iter(['pid', 'name', 'exe']) 
                                              if 'chrome' in p.info['name'].lower()]
                            if chrome_processes:
                                processes_to_stop = []
                                for proc in chrome_processes:
                                    try:
                                        exe_path = proc.info.get('exe', '')
                                        if exe_path and 'chrome.exe' in exe_path.lower():
                                            try:
                                                cmdline = proc.cmdline()
                                                cmdline_str = ' '.join(cmdline)
                                                bg_keywords = ['--type=crashpad-handler', '--type=utility', 
                                                              '--type=renderer', '--type=gpu-process',
                                                              '--type=zygote', '--type=service',
                                                              '--remote-debugging-port']
                                                if any(keyword in cmdline_str for keyword in bg_keywords):
                                                    processes_to_stop.append(proc)
                                            except:
                                                processes_to_stop.append(proc)
                                    except:
                                        pass
                                
                                if processes_to_stop:
                                    stopped_count = 0
                                    for proc in processes_to_stop:
                                        try:
                                            proc.terminate()
                                            stopped_count += 1
                                        except:
                                            try:
                                                proc.kill()
                                                stopped_count += 1
                                            except:
                                                pass
                                    time.sleep(2)
                        except:
                            pass
                    
                    # ブラウザ起動
                    driver = None
                    
                    if minimal_options or test_minimal:
                        try:
                            if chrome_binary_path and os.path.exists(chrome_binary_path):
                                chrome_options.binary_location = chrome_binary_path
                            driver = webdriver.Chrome(service=service, options=chrome_options)
                        except Exception as e:
                            self.logger.log(f"[Selenium安全弁] Chromeブラウザ起動エラー: {e}", "error")
                            continue
                    else:
                        driver_error = None
                        
                        def start_driver():
                            nonlocal driver, driver_error
                            try:
                                if chrome_binary_path and os.path.exists(chrome_binary_path):
                                    chrome_options.binary_location = chrome_binary_path
                                driver = webdriver.Chrome(service=service, options=chrome_options)
                            except Exception as e:
                                driver_error = e
                        
                        start_thread = threading.Thread(target=start_driver, daemon=True)
                        start_thread.start()
                        start_thread.join(timeout=30)
                        
                        if start_thread.is_alive():
                            self.logger.log("[Selenium安全弁] Chromeブラウザの起動がタイムアウトしました", "warning")
                            continue
                        
                        if driver_error:
                            self.logger.log(f"[Selenium安全弁] Chromeブラウザ起動エラー: {driver_error}", "error")
                            continue
                    
                    if not driver:
                        continue
                    
                    # タイムアウト設定
                    driver.set_page_load_timeout(config.get('timeout', 30))
                    driver.implicitly_wait(10)
                    
                    return driver
                    
                except Exception as e:
                    self.logger.log(f"[Selenium安全弁] ドライバー取得試行 {attempt + 1}/{max_retries} 失敗: {e}", "error")
                    if attempt < max_retries - 1:
                        time.sleep(5)
                    continue
            
            return None
            
        except Exception as e:
            self.logger.log(f"[Selenium安全弁] ドライバー取得エラー: {e}", "error")
            return None
    
    def _navigate_to_image_with_selenium(self, driver, url: str, config: Dict[str, Any]) -> bool:
        """Seleniumを使用した画像ページへのナビゲーション"""
        try:
            try:
                window_handles = driver.window_handles
                if not window_handles:
                    self.logger.log("[Selenium安全弁] Chromeウィンドウが閉じられています", "error")
                    return False
            except Exception as e:
                self.logger.log(f"[Selenium安全弁] ドライバーの状態確認エラー: {e}", "error")
                return False
            
            wait_strategy = config.get('wait_strategy', 'normal')
            
            if wait_strategy == 'eager':
                driver.execute_script("window.stop();")
            
            driver.get(url)
            
            try:
                current_url = driver.current_url
                if not current_url or current_url == "data:,":
                    self.logger.log("[Selenium安全弁] ナビゲーション後のURLが無効です", "error")
                    return False
            except Exception as e:
                self.logger.log(f"[Selenium安全弁] ナビゲーション後の状態確認エラー: {e}", "error")
                return False
            
            if wait_strategy == 'normal':
                time.sleep(2)
            elif wait_strategy == 'eager':
                time.sleep(1)
            
            return True
            
        except Exception as e:
            self.logger.log(f"[Selenium安全弁] Seleniumナビゲーションエラー: {e}", "error")
            return False
    
    def _extract_image_data_with_selenium(self, driver, url: str):
        """Seleniumを使用した画像データの抽出"""
        try:
            methods = [
                self._extract_via_canvas,
                self._extract_via_direct_download,
                self._extract_via_blob_url
            ]
            
            for method in methods:
                try:
                    image_data = method(driver, url)
                    if image_data:
                        if method.__name__ == '_extract_via_direct_download':
                            self.logger.log("[Selenium安全弁] Canvas抽出が失敗しましたが、直接ダウンロードで成功しました", "info")
                        return image_data
                except Exception as e:
                    if method.__name__ == '_extract_via_canvas' and 'Tainted canvases' in str(e):
                        self.logger.log(f"[Selenium安全弁] Canvas抽出エラー（CORS制限）: {e}。直接ダウンロードにフォールバックします", "debug")
                    else:
                        self.logger.log(f"画像抽出方法失敗: {method.__name__} - {e}", "debug")
                    continue
            
            return None
            
        except Exception as e:
            self.logger.log(f"Selenium画像抽出エラー: {e}", "error")
            return None
    
    def _extract_via_canvas(self, driver, url: str):
        """Canvasを使用した画像データの抽出"""
        try:
            script = """
            var img = document.querySelector('img');
            if (img) {
                var canvas = document.createElement('canvas');
                canvas.width = img.naturalWidth;
                canvas.height = img.naturalHeight;
                var ctx = canvas.getContext('2d');
                ctx.drawImage(img, 0, 0);
                return canvas.toDataURL('image/png').split(',')[1];
            }
            return null;
            """
            image_data_b64 = driver.execute_script(script)
            
            if image_data_b64:
                return base64.b64decode(image_data_b64)
            
            return None
            
        except Exception as e:
            self.logger.log(f"Canvas画像抽出エラー: {e}", "debug")
            return None
    
    def _extract_via_direct_download(self, driver, url: str):
        """直接ダウンロードを使用した画像データの抽出"""
        try:
            script = """
            var img = document.querySelector('img');
            if (img) {
                return img.src;
            }
            return null;
            """
            image_url = driver.execute_script(script)
            
            if image_url:
                response = requests.get(image_url, timeout=30)
                response.raise_for_status()
                return response.content
            
            return None
            
        except Exception as e:
            self.logger.log(f"直接ダウンロード画像抽出エラー: {e}", "debug")
            return None
    
    def _extract_via_blob_url(self, driver, url: str):
        """Blob URLを使用した画像データの抽出"""
        try:
            script = """
            var img = document.querySelector('img');
            if (img) {
                var canvas = document.createElement('canvas');
                canvas.width = img.naturalWidth;
                canvas.height = img.naturalHeight;
                var ctx = canvas.getContext('2d');
                ctx.drawImage(img, 0, 0);
                
                return new Promise(function(resolve) {
                    canvas.toBlob(function(blob) {
                        var reader = new FileReader();
                        reader.onload = function() {
                            resolve(reader.result.split(',')[1]);
                        };
                        reader.readAsDataURL(blob);
                    });
                });
            }
            return null;
            """
            
            image_data_b64 = driver.execute_async_script(script)
            
            if image_data_b64:
                return base64.b64decode(image_data_b64)
            
            return None
            
        except Exception as e:
            self.logger.log(f"Blob URL画像抽出エラー: {e}", "debug")
            return None
    
    def _validate_chrome_installation(self, chrome_path: str, use_registry: bool = True) -> tuple:
        """Chromeのインストールを検証"""
        try:
            if not os.path.exists(chrome_path):
                return False, "Chrome実行ファイルが見つかりません"
            
            if not os.access(chrome_path, os.X_OK):
                return False, "Chrome実行ファイルに実行権限がありません"
            
            if use_registry:
                try:
                    import winreg
                    try:
                        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Google\Chrome\BLBeacon")
                        version, _ = winreg.QueryValueEx(key, "version")
                        winreg.CloseKey(key)
                        return True, f"Chromeバージョン: Google Chrome {version}（レジストリから取得）"
                    except:
                        try:
                            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Google\Chrome\BLBeacon")
                            version, _ = winreg.QueryValueEx(key, "version")
                            winreg.CloseKey(key)
                            return True, f"Chromeバージョン: Google Chrome {version}（レジストリから取得）"
                        except:
                            pass
                except:
                    pass
            
            return True, "Chrome実行ファイルが存在し、実行可能です（バージョン情報は取得できませんでした）"
            
        except Exception as e:
            return False, f"Chrome検証中にエラー: {e}"
