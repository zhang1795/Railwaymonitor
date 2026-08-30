"""
工具函数模块
"""
import os
import cv2
import numpy as np
from typing import Optional, Tuple
import uuid
from datetime import datetime
from config import ALLOWED_EXTENSIONS, UPLOAD_FOLDER
from werkzeug.utils import secure_filename
import threading

def allowed_file(filename: str) -> bool:
    """
    检查文件扩展名是否允许
    Args:
        filename: 文件名
    Returns:
        bool: 是否允许
    """
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def save_upload_file(file) -> Optional[str]:
    """
    保存上传的文件
    Args:
        file: 文件对象
    Returns:
        Optional[str]: 保存的文件路径，失败返回None
    """
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)
        return filepath
    return None

def read_image_file(filepath: str) -> Optional[np.ndarray]:
    """
    读取图片文件
    Args:
        filepath: 图片文件路径
    Returns:
        Optional[np.ndarray]: OpenCV格式的图片，失败返回None
    """
    if not os.path.exists(filepath):
        return None
    return cv2.imread(filepath)

class VideoStream:
    """视频流处理类"""
    
    def __init__(self, rtsp_url: str):
        """
        初始化视频流
        Args:
            rtsp_url: 视频流地址
        """
        self.rtsp_url = rtsp_url
        self.cap = None
        self.running = False
        # VideoCapture 不是线程安全的。WebSocket 线程会执行 stop()，而后台
        # 推帧线程同时执行 read_frame()；加锁可避免 release/read 并发导致
        # OpenCV 原生层直接终止整个 Flask 进程。
        self.capture_lock = threading.RLock()
        print(f"初始化视频流: {rtsp_url}")
        
    def check_rtsp_connection(self) -> bool:
        """
        检查RTSP地址是否可达
        Returns:
            bool: 是否可达
        """
        import socket
        import re
        
        try:
            # 解析RTSP URL
            match = re.match(r'rtsp://([^:/]+)(?::(\d+))?', self.rtsp_url)
            if not match:
                print(f"无效的RTSP地址: {self.rtsp_url}")
                return False
                
            host = match.group(1)
            port = int(match.group(2)) if match.group(2) else 554
            
            # 创建socket连接测试
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2.0)  # 2秒超时
            
            result = sock.connect_ex((host, port))
            sock.close()
            
            if result == 0:
                print(f"RTSP地址可达: {self.rtsp_url}")
                return True
            else:
                print(f"RTSP地址不可达: {self.rtsp_url}")
                return False
                
        except Exception as e:
            print(f"检查RTSP连接失败: {self.rtsp_url}, 错误: {str(e)}")
            return False
        
    def start(self) -> bool:
        """
        启动视频流
        Returns:
            bool: 是否成功启动
        """
        # 第一步：检查RTSP地址可达性
        if not self.check_rtsp_connection():
            return False
            
        # 第二步：尝试打开视频流
        try:
            with self.capture_lock:
                # 此时的self.rtsp_url一定是可达的，所以这里不会使用默认的30秒连接超时，直接会赋值给self.cap
                self.cap = cv2.VideoCapture(self.rtsp_url)
                # 如果这个可达的rtsp_url不能打开视频流，则返回False
                if not self.cap.isOpened():
                    print(f"无法打开视频流: {self.rtsp_url}")
                    if self.cap:
                        self.cap.release()
                    self.cap = None
                    return False

                # 读取一帧测试连接
                ret, frame = self.cap.read()
                if not ret or frame is None:
                    print(f"无法读取视频帧: {self.rtsp_url}")
                    self.stop()
                    return False

                self.running = True
                print(f"视频流连接成功: {self.rtsp_url}")
                return True
            
        except Exception as e:
            print(f"视频流连接失败: {self.rtsp_url}, 错误: {str(e)}")
            if self.cap:
                self.stop()
            return False
        
    def read_frame(self) -> tuple[bool, np.ndarray]:
        """
        读取一帧
        Returns:
            tuple[bool, np.ndarray]: (是否成功, 帧数据)
        """
        try:
            with self.capture_lock:
                if not self.running or not self.cap:
                    return False, None

                ret, frame = self.cap.read()
                if not ret or frame is None:
                    print(f"读取视频帧失败: {self.rtsp_url}")
                    return False, None

                return True, frame
        except Exception as e:
            print(f"读取视频帧出错: {self.rtsp_url}, 错误: {str(e)}")
            return False, None
        
    def stop(self) -> None:
        """停止视频流"""
        with self.capture_lock:
            print(f"停止视频流: {self.rtsp_url}, self.cap: {self.cap}")
            self.running = False
            if self.cap:
                try:
                    self.cap.release()
                    print(f"视频流已停止: {self.rtsp_url}")
                except Exception as e:
                    print(f"停止视频流出错: {self.rtsp_url}, 错误: {str(e)}")
            self.cap = None
