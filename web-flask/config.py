"""
配置文件
"""
import os

# 服务配置
HOST = os.getenv('FLASK_HOST', '0.0.0.0')
PORT = int(os.getenv('FLASK_PORT', '5000'))

# 视频流配置
MAX_TASKS = 10  # 最大同时处理的视频流任务数
FRAME_INTERVAL = 1  # 视频流检测间隔(秒)
DETECTION_FRAME_SKIP = 25  # 每隔多少帧进行一次检测
JPEG_QUALITY = 80  # JPEG压缩质量
MAX_FRAME_SIZE = (640, 480)  # 最小帧大小
MAX_SCALE_FACTOR = 2  # 最大缩放因子，用于限制图像最大尺寸
ENABLE_GPU = os.getenv('ENABLE_GPU', 'false').lower() == 'true'  # 是否启用GPU
TARGET_FPS = 25  # 目标帧率
FRAME_TIME = 1.0 / TARGET_FPS  # 每帧的理想时间

# 文件存储配置
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}
MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 最大上传文件大小(16MB)

# 临时文件配置
TEMP_DIR = os.path.join(os.path.dirname(__file__), 'temp')
os.makedirs(TEMP_DIR, exist_ok=True)  # 创建临时文件目录

# 创建必要的目录
os.makedirs(UPLOAD_FOLDER, exist_ok=True) 
