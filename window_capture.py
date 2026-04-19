import ctypes
import logging
import threading
import time

import numpy as np
import pywintypes
import win32api
import win32con
import win32gui
import win32ui

logger = logging.getLogger(__name__)

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    logger.debug("DPI awareness is already configured or unavailable")


class WindowCaptureError(RuntimeError):
    pass


class WindowNotAvailableError(WindowCaptureError):
    pass


class WindowCapture:
    def __init__(self, window_title, target_width=800, target_height=600):
        self.window_title = window_title
        self.hwnd = None
        self.target_width = target_width
        self.target_height = target_height
        self._lock = threading.RLock()
        try:
            self.ensure_window(resize=True)
        except WindowNotAvailableError as exc:
            logger.warning("%s", exc)

    def _find_window_handle(self):
        hwnd = win32gui.FindWindow(None, self.window_title)
        if hwnd and win32gui.IsWindow(hwnd):
            return hwnd
        return None

    def _invalidate_window(self):
        self.hwnd = None

    def _translate_win32_error(self, exc, action):
        winerror = exc.args[0] if exc.args else None
        if winerror == 1400:
            self._invalidate_window()
            return WindowNotAvailableError(
                f"Window '{self.window_title}' is no longer available during {action}"
            )
        return WindowCaptureError(f"{action} failed for window '{self.window_title}': {exc}")

    def _resize_bound_window(self):
        if not self.hwnd or not win32gui.IsWindow(self.hwnd):
            return

        rect = win32gui.GetWindowRect(self.hwnd)
        x, y = rect[0], rect[1]

        ctypes.windll.user32.SetWindowPos(
            self.hwnd,
            0,
            int(x),
            int(y),
            int(self.target_width),
            int(self.target_height),
            win32con.SWP_NOZORDER | win32con.SWP_SHOWWINDOW,
        )
        logger.info("Window resized to %sx%s", self.target_width, self.target_height)

    def find_window(self):
        with self._lock:
            hwnd = self._find_window_handle()
            if not hwnd:
                self._invalidate_window()
                raise WindowNotAvailableError(f"Window '{self.window_title}' not found")
            if hwnd != self.hwnd:
                logger.info("Window found: %s (HWND: %s)", self.window_title, hwnd)
            self.hwnd = hwnd
            return self.hwnd

    def ensure_window(self, resize=False):
        with self._lock:
            if self.hwnd and win32gui.IsWindow(self.hwnd):
                if resize:
                    self._resize_bound_window()
                return self.hwnd

            previous_hwnd = self.hwnd
            hwnd = self._find_window_handle()
            if not hwnd:
                self._invalidate_window()
                if previous_hwnd:
                    logger.warning("Window handle %s is no longer valid", previous_hwnd)
                raise WindowNotAvailableError(f"Window '{self.window_title}' not found")

            handle_changed = hwnd != previous_hwnd
            self.hwnd = hwnd
            if handle_changed:
                logger.info("Window found: %s (HWND: %s)", self.window_title, hwnd)
            if resize or handle_changed:
                self._resize_bound_window()
            return self.hwnd

    def get_hwnd(self):
        return self.ensure_window()

    def resize_window(self):
        with self._lock:
            self.ensure_window()
            self._resize_bound_window()

    def get_window_rect(self):
        hwnd = self.ensure_window()

        try:
            rect = win32gui.GetClientRect(hwnd)
            x, y = win32gui.ClientToScreen(hwnd, (rect[0], rect[1]))
        except pywintypes.error as exc:
            raise self._translate_win32_error(exc, "reading the window bounds") from exc

        width = rect[2] - rect[0]
        height = rect[3] - rect[1]
        if width <= 0 or height <= 0:
            raise WindowCaptureError(
                f"Window '{self.window_title}' has an invalid client size: {width}x{height}"
            )
        return x, y, width, height

    def capture(self, max_y=None):
        hwnd = self.ensure_window()
        _, _, width, height = self.get_window_rect()

        if max_y is not None:
            height = min(height, int(max_y))
        if width <= 0 or height <= 0:
            raise WindowCaptureError(
                f"Window '{self.window_title}' cannot be captured with size {width}x{height}"
            )

        hwnd_dc = None
        mfc_dc = None
        save_dc = None
        save_bitmap = None
        try:
            hwnd_dc = win32gui.GetWindowDC(hwnd)
            mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
            save_dc = mfc_dc.CreateCompatibleDC()

            save_bitmap = win32ui.CreateBitmap()
            save_bitmap.CreateCompatibleBitmap(mfc_dc, width, height)
            save_dc.SelectObject(save_bitmap)

            result = ctypes.windll.user32.PrintWindow(hwnd, save_dc.GetSafeHdc(), 3)
            if result != 1:
                raise WindowCaptureError(f"PrintWindow failed for '{self.window_title}'")

            bitmap_bytes = save_bitmap.GetBitmapBits(True)
            img = np.frombuffer(bitmap_bytes, dtype=np.uint8)
            img.shape = (height, width, 4)
            img = np.ascontiguousarray(img[:, :, :3])
            return img
        except pywintypes.error as exc:
            raise self._translate_win32_error(exc, "capturing the window") from exc
        finally:
            if save_bitmap is not None:
                win32gui.DeleteObject(save_bitmap.GetHandle())
            if save_dc is not None:
                save_dc.DeleteDC()
            if mfc_dc is not None:
                mfc_dc.DeleteDC()
            if hwnd_dc is not None and hwnd:
                win32gui.ReleaseDC(hwnd, hwnd_dc)

    def is_window_active(self):
        with self._lock:
            if self.hwnd and win32gui.IsWindow(self.hwnd):
                return True
            self.hwnd = self._find_window_handle()
            return bool(self.hwnd)


class ForbiddenAreaOverlay:
    def __init__(self, target_hwnd, forbidden_zones):
        self.target_hwnd = target_hwnd
        self.forbidden_zones = forbidden_zones
        self.overlay_hwnd = None
        self.running = False
        self.thread = None
        
    def start(self):
        if not self.running:
            self.running = True
            self.thread = threading.Thread(target=self._create_overlay, daemon=True)
            self.thread.start()
            logger.info("Forbidden area overlay started")
    
    def stop(self):
        self.running = False
        if self.overlay_hwnd:
            try:
                win32gui.DestroyWindow(self.overlay_hwnd)
            except:
                pass
            self.overlay_hwnd = None
        logger.info("Forbidden area overlay stopped")
    
    def _create_overlay(self):
        try:
            wc = win32gui.WNDCLASS()
            wc.lpfnWndProc = self._wnd_proc
            wc.lpszClassName = "ForbiddenAreaOverlay"
            wc.hCursor = win32gui.LoadCursor(0, win32con.IDC_ARROW)
            wc.hbrBackground = win32gui.GetStockObject(win32con.NULL_BRUSH)
            
            try:
                class_atom = win32gui.RegisterClass(wc)
            except Exception as e:
                pass
            
            target_rect = win32gui.GetClientRect(self.target_hwnd)
            target_pos = win32gui.ClientToScreen(self.target_hwnd, (0, 0))
            width = target_rect[2] - target_rect[0]
            height = target_rect[3] - target_rect[1]
            
            self.overlay_hwnd = win32gui.CreateWindowEx(
                win32con.WS_EX_LAYERED | win32con.WS_EX_TRANSPARENT | win32con.WS_EX_TOPMOST | win32con.WS_EX_TOOLWINDOW,
                "ForbiddenAreaOverlay",
                "Forbidden Area Overlay",
                win32con.WS_POPUP,
                target_pos[0], target_pos[1],
                width, height,
                0, 0, 0, None
            )
            
            # Set transparency (255 = opaque, 128 = 50% transparent, 0 = fully transparent)
            win32gui.SetLayeredWindowAttributes(
                self.overlay_hwnd,
                0,
                128,  # 50% transparency
                win32con.LWA_ALPHA
            )
            win32gui.SetLayeredWindowAttributes(
                self.overlay_hwnd,
                0,
                128,
                win32con.LWA_ALPHA
            )
            
            win32gui.ShowWindow(self.overlay_hwnd, win32con.SW_SHOW)
            win32gui.UpdateWindow(self.overlay_hwnd)
            
            self._draw_zones()
            
            last_pos = target_pos
            while self.running:
                try:
                    new_pos = win32gui.ClientToScreen(self.target_hwnd, (0, 0))
                    if new_pos != last_pos:
                        last_pos = new_pos
                        win32gui.SetWindowPos(
                            self.overlay_hwnd,
                            win32con.HWND_TOPMOST,
                            new_pos[0], new_pos[1],
                            width, height,
                            win32con.SWP_SHOWWINDOW
                        )
                        self._draw_zones()
                    
                except Exception as e:
                    logger.error(f"Error in overlay update loop: {e}")
                    break
                
                time.sleep(0.1)
                
        except Exception as e:
            logger.error(f"Failed to create overlay window: {e}")
        finally:
            self.running = False
    
    def _draw_zones(self):
        if not self.overlay_hwnd:
            return
            
        try:
            hdc = win32gui.GetDC(self.overlay_hwnd)
            
            red_brush = win32gui.CreateSolidBrush(win32api.RGB(255, 0, 0))
            
            for x_min, x_max, y_min, y_max in self.forbidden_zones:
                old_brush = win32gui.SelectObject(hdc, red_brush)
                
                win32gui.Rectangle(hdc, int(x_min), int(y_min), int(x_max), int(y_max))
                
                win32gui.SelectObject(hdc, old_brush)
            
            win32gui.DeleteObject(red_brush)
            win32gui.ReleaseDC(self.overlay_hwnd, hdc)
            
        except Exception as e:
            logger.error(f"Error drawing zones: {e}")
    
    def _wnd_proc(self, hwnd, msg, wparam, lparam):
        if msg == win32con.WM_PAINT:
            hdc, ps = win32gui.BeginPaint(hwnd)
            
            red_brush = win32gui.CreateSolidBrush(win32api.RGB(255, 0, 0))
            
            for x_min, x_max, y_min, y_max in self.forbidden_zones:
                old_brush = win32gui.SelectObject(hdc, red_brush)
                win32gui.Rectangle(hdc, int(x_min), int(y_min), int(x_max), int(y_max))
                win32gui.SelectObject(hdc, old_brush)
            
            win32gui.DeleteObject(red_brush)
            win32gui.EndPaint(hwnd, ps)
            return 0
        elif msg == win32con.WM_DESTROY:
            win32gui.PostQuitMessage(0)
            return 0
        return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)

