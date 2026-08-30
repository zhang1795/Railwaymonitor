"""
Flask主程序
"""
from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_sock import Sock
import cv2
import base64
import json
import numpy as np
from algo.utils import VideoStream
from config import (
    HOST,
    PORT, 
    MAX_CONTENT_LENGTH,
    FRAME_INTERVAL,
    DETECTION_FRAME_SKIP,
    JPEG_QUALITY,
    FRAME_TIME
)
import time
import threading
from typing import Dict, Set
import traceback
from simple_websocket.errors import ConnectionClosed
from wsproto.frame_protocol import CloseReason
import os
import logging
import io

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 创建Flask应用
app = Flask(__name__)

# 配置
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH

# 允许跨域
CORS(app)

# 配置WebSocket
sock = Sock(app)


@app.get('/api/health')
def health():
    """部署健康检查，不触发视频流或模型加载。"""
    return jsonify({
        'status': 'ok',
        'activeStreams': len(stream_tasks),
    })

# 存储视频流任务
stream_tasks: Dict[int, dict] = {}
# 存储每个WebSocket连接的任务ID
ws_tasks: Dict[str, Set[int]] = {}
# WebSocket发送锁
ws_send_locks: Dict[str, threading.Lock] = {}

def get_ws_send_lock(ws_id: str) -> threading.Lock:
    """获取WebSocket发送锁"""
    if ws_id not in ws_send_locks:
        ws_send_locks[ws_id] = threading.Lock()
    return ws_send_locks[ws_id]

def safe_ws_send(ws, ws_id: str, message: dict):
    """安全地发送WebSocket消息"""
    try:
        # 检查WebSocket连接是否仍然打开
        if ws_id not in ws_tasks:
            print(f"尝试向已关闭的WebSocket连接发送消息: {ws_id}")
            return False
            
        with get_ws_send_lock(ws_id):
            ws.send(json.dumps(message))
        return True
    except Exception as e:
        print(f"发送WebSocket消息失败: {str(e)}")
        # 如果发送失败，可能是连接已关闭，尝试清理资源
        if "Connection closed" in str(e):
            print(f"WebSocket连接已关闭，清理资源: {ws_id}")
            cleanup_ws_tasks(ws_id)
        return False

def cleanup_ws_tasks(ws_id: str):
    """清理指定WebSocket连接的所有任务"""
    if ws_id in ws_tasks:
        # 获取该连接的所有任务ID
        task_ids = ws_tasks[ws_id].copy()
        # 清理每个任务
        for camera_id in task_ids:
            if camera_id in stream_tasks:
                task = stream_tasks[camera_id]
                if task['stream']:
                    task['stream'].stop()
                del stream_tasks[camera_id]
        # 删除该连接的记录
        del ws_tasks[ws_id]
        # 删除发送锁
        if ws_id in ws_send_locks:
            del ws_send_locks[ws_id]

def process_stream(ws, ws_id: str, camera_id: int, stream: VideoStream):
    """处理视频流"""
    frame_count = 0
    last_detection_time = time.time()
    error_count = 0  # 添加错误计数，防止连续错误导致程序崩溃
    first_frame_sent = False  # 标记第一帧是否已成功发送
    
    try:
        while camera_id in stream_tasks and stream_tasks[camera_id]['status'] == 'running':
            try:
                # 记录开始处理时间
                start_time = time.time()
                
                ret, frame = stream.read_frame()
                if not ret:
                    print(f"读取视频帧失败: {camera_id}")
                    error_count += 1
                    # 如果连续5次读取失败，结束循环
                    if error_count >= 5:
                        print(f"连续读取视频帧失败，停止视频流: {camera_id}")
                        break
                    time.sleep(0.5)  # 短暂延迟后重试
                    continue
                
                # 读取成功，重置错误计数
                error_count = 0
                frame_count += 1
                current_time = time.time()
                
                # 创建原始帧的副本，用于绘制检测框
                display_frame = frame.copy()
                frame_processed = False  # 标记是否已处理并发送当前帧
                
                # 检测逻辑：使用配置的检测间隔
                if frame_count % DETECTION_FRAME_SKIP == 0 or (current_time - last_detection_time) >= FRAME_INTERVAL:
                    result = {}
                    last_detection_time = current_time
                                                
                    # 编码图片为Base64
                    encode_params = [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY]
                    _, buffer = cv2.imencode('.jpg', display_frame, encode_params)
                    base64_frame = "data:image/jpeg;base64," + base64.b64encode(buffer).decode('utf-8')
                        
                    # 将图像添加到结果中
                    result['encoded_frame'] = base64_frame
                        
                    # 发送检测结果，包含带检测框的图像
                    if not send_detection_result(ws, ws_id, camera_id, result):
                        # 如果发送失败，可能是WebSocket已关闭，退出循环
                        print(f"发送检测结果失败，停止视频流: {camera_id}")
                        break
                        
                    # 标记当前帧已发送
                    frame_processed = True
                        
                    # 如果这是第一帧，发送流准备就绪消息
                    if not first_frame_sent:
                        first_frame_sent = True
                        if not safe_ws_send(ws, ws_id, {
                            'type': 'stream_ready',
                            'data': {
                                'cameraId': camera_id,
                                'status': 1
                            }
                        }):
                            print(f"发送流准备就绪通知失败，停止视频流: {camera_id}")
                            break
                        print(f"视频流{camera_id}的第一帧已成功发送，通知前端准备就绪")                        
                
                # 如果是第一帧但没有进行检测，发送一次图像确保前端有初始画面
                if not first_frame_sent and not frame_processed:
                    # 编码图片为Base64
                    encode_params = [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY]
                    _, buffer = cv2.imencode('.jpg', display_frame, encode_params)
                    base64_frame = "data:image/jpeg;base64," + base64.b64encode(buffer).decode('utf-8')
                    
                    # 创建一个无检测结果的帧
                    empty_result = {
                        'encoded_frame': base64_frame
                    }
                    
                    # 发送初始帧
                    if not send_detection_result(ws, ws_id, camera_id, empty_result):
                        print(f"发送初始帧失败，停止视频流: {camera_id}")
                        break
                    
                    # 发送流准备就绪消息
                    first_frame_sent = True
                    if not safe_ws_send(ws, ws_id, {
                        'type': 'stream_ready',
                        'data': {
                            'cameraId': camera_id,
                            'status': 1
                        }
                    }):
                        print(f"发送流准备就绪通知失败，停止视频流: {camera_id}")
                        break
                    print(f"视频流{camera_id}的初始帧已成功发送，通知前端准备就绪")
                
                # 计算实际处理时间
                process_time = time.time() - start_time
                
                # 计算需要的延迟时间
                delay = FRAME_TIME - process_time
                if delay > 0:
                    time.sleep(delay)
                else:
                    # 如果处理时间超过了帧间隔，记录警告
                    print(f"警告：处理时间({process_time:.3f}s)超过了目标帧时间({FRAME_TIME:.3f}s)")
                
            except Exception as e:
                print(f"处理视频帧出错: {str(e)}")
                error_count += 1
                # 如果连续5次出错，结束循环
                if error_count >= 5:
                    print(f"连续处理视频帧出错，停止视频流: {camera_id}")
                    break
                time.sleep(0.5)  # 短暂延迟后重试
                continue
        
        print(f"视频流正常结束: {camera_id}")
    except Exception as outer_e:
        print(f"视频流处理出现严重错误: {camera_id}, 错误: {str(outer_e)}")
    finally:
        print(f"视频流结束: {camera_id}")
        # 确保无论如何都会清理资源
        try:
            stop_stream_and_cleanup(ws, ws_id, camera_id)
        except Exception as cleanup_error:
            print(f"清理视频流资源出错: {camera_id}, 错误: {str(cleanup_error)}")

@sock.route('/ws')
def handle_websocket(ws):
    """处理WebSocket连接"""
    # 为每个WebSocket连接生成唯一ID
    ws_id = str(id(ws))
    ws_tasks[ws_id] = set()
    
    # 最近处理的命令防抖动缓存，记录命令类型和时间
    recent_commands = {}
    # 防抖动时间窗口(秒)
    debounce_window = 1
    
    print(f"新的WebSocket连接: {ws_id}")
    try:
        while True:
            # 接收消息
            data = ws.receive()
            print(f"收到WebSocket消息: {data}")
            message = json.loads(data)
            
            # 获取命令类型和相关ID
            cmd_type = message['type']
            
            # 针对不同类型的命令提取ID
            entity_id = None
            if cmd_type == 'check_camera' and 'data' in message and 'cameraId' in message['data']:
                entity_id = message['data']['cameraId']
            elif cmd_type == 'start_stream' and 'data' in message and 'cameraId' in message['data']:
                entity_id = message['data']['cameraId']
            elif cmd_type == 'stop_stream' and 'data' in message and 'cameraId' in message['data']:
                entity_id = message['data']['cameraId']
                
            # 防抖动检查
            if entity_id is not None:
                cmd_key = f"{cmd_type}_{entity_id}"
                current_time = time.time()
                
                # 检查是否在防抖动时间窗口内
                if cmd_key in recent_commands and (current_time - recent_commands[cmd_key]) < debounce_window:
                    print(f"防抖动: 忽略重复的命令 {cmd_type} 用于ID {entity_id}")
                    continue
                
                # 更新最近命令时间
                recent_commands[cmd_key] = current_time
            
            if message['type'] == 'check_camera':
                # 检查摄像头状态
                camera_id = message['data']['cameraId']
                rtsp_url = message['data']['rtspUrl']
                
                # 创建临时视频流对象检查状态
                stream = VideoStream(rtsp_url)
                is_online = stream.start()
                # 立即停止视频流
                stream.stop()
                
                # 发送状态
                send_camera_status(ws, ws_id, camera_id, 1 if is_online else 0)
                
            elif message['type'] == 'start_stream':
                print(f"开始视频流: {message['data']}")
                camera_id = message['data']['cameraId']
                rtsp_url = message['data']['rtspUrl']
                
                # 如果已经有该摄像头的任务在运行，先停止它并等待资源完全释放
                if camera_id in stream_tasks:
                    print(f"摄像头 {camera_id} 已有视频流在运行，先停止它")
                    old_task = stream_tasks[camera_id]
                    if old_task['stream']:
                        old_task['status'] = 'stopped'
                        old_task['stream'].stop()
                    # 从任务列表中移除，确保资源被完全释放
                    stream_tasks.pop(camera_id, None)
                    # 保证有足够的时间完全释放资源
                    time.sleep(0.5)
                
                # 创建视频流对象
                stream = VideoStream(rtsp_url)
                # 尝试多次启动，有些RTSP流需要多次尝试
                start_attempts = 0
                max_attempts = 3
                is_started = False
                
                while start_attempts < max_attempts and not is_started:
                    is_started = stream.start()
                    if not is_started:
                        start_attempts += 1
                        print(f"视频流启动失败，尝试第 {start_attempts}/{max_attempts} 次")
                        time.sleep(1)  # 等待一秒再试
                
                if not is_started:
                    print(f"视频流启动失败: {rtsp_url}")
                    # 发送离线状态
                    send_camera_status(ws, ws_id, camera_id, 0)
                    continue
                
                print(f"视频流启动成功: {rtsp_url}")
                # 确保在添加新任务前，任何旧的相同ID任务已被清理
                if camera_id in stream_tasks:
                    stream_tasks.pop(camera_id, None)
                    
                stream_tasks[camera_id] = {
                    'status': 'running',
                    'stream': stream,
                    'ws_id': ws_id,
                    'start_time': time.time()  # 记录启动时间
                }
                # 记录该任务属于当前WebSocket连接
                ws_tasks[ws_id].add(camera_id)
                
                # 发送在线状态
                send_camera_status(ws, ws_id, camera_id, 1)
                
                # 启动视频流处理线程
                stream_thread = threading.Thread(
                    target=process_stream,
                    args=(ws, ws_id, camera_id, stream),
                    daemon=True
                )
                stream_thread.start()
                
            elif message['type'] == 'stop_stream':
                print(f"停止视频流: {message['data']}")
                camera_id = message['data']['cameraId']
                if camera_id in stream_tasks:
                    # 停止视频流并发送清理消息
                    stop_stream_and_cleanup(ws, ws_id, camera_id)
                    # 从当前WebSocket连接的任务列表中移除
                    if ws_id in ws_tasks:
                        ws_tasks[ws_id].discard(camera_id)
                    
    except ConnectionClosed as e:
        if e.reason == CloseReason.NORMAL_CLOSURE:
            print(f"WebSocket正常关闭（信息性）: {ws_id}, 原因: 客户端正常断开连接")
        else:
            print(f"WebSocket异常关闭（错误）: {ws_id}, 原因: {e}")
            traceback.print_exc()  # 只对非正常关闭打印堆栈
    except json.JSONDecodeError as e:
        print(f"WebSocket消息JSON解析错误: {ws_id}, 错误: {str(e)}")
    except Exception as e:
        print(f"WebSocket处理发生未知错误: {ws_id}, 错误: {str(e)}")
        traceback.print_exc()  # 打印完整异常堆栈
    finally:
        print(f"WebSocket连接清理: {ws_id}")
        # 清理该连接的所有资源
        cleanup_ws_tasks(ws_id)

def send_camera_status(ws, ws_id: str, camera_id: int, status: int):
    """发送摄像头状态"""
    return safe_ws_send(ws, ws_id, {
        'type': 'camera_status',
        'data': {
            'cameraId': camera_id,
            'status': status
        }
    })

def send_detection_result(ws, ws_id: str, camera_id: int, result: dict):
    """发送检测结果，包含视频帧"""
    return safe_ws_send(ws, ws_id, {
        'type': 'video_frame',
        'data': {
            'cameraId': camera_id,
            'frame': result['encoded_frame']  # 添加编码后的帧数据
        }
    })

def stop_stream_and_cleanup(ws, ws_id: str, camera_id: int):
    """停止视频流并清理资源"""
    try:
        # 安全地获取stream_task
        stream_task = stream_tasks.get(camera_id)
        if stream_task:
            # 设置状态为stopped
            stream_task['status'] = 'stopped'
            # 等待视频流处理完成
            if 'stream' in stream_task:
                stream = stream_task['stream']
                if stream:
                    stream.stop()
            # 安全地删除任务
            stream_tasks.pop(camera_id, None)
        
        # 发送停止消息给客户端
        try:
            # 检查ws_id是否仍在活跃连接中
            if ws_id in ws_tasks:
                ws.send(json.dumps({
                    'type': 'stream_stopped',
                    'data': {
                        'wsId': ws_id,
                        'cameraId': camera_id
                    }
                }))
        except Exception as e:
            print(f"发送停止消息失败: {str(e)}")
            
    except Exception as e:
        print(f"停止视频流时发生错误: {str(e)}")
    finally:
        # 确保stream_tasks中的数据被清理
        if camera_id in stream_tasks:
            try:
                stream_tasks.pop(camera_id, None)
            except Exception as e:
                print(f"清理stream_tasks失败: {str(e)}")
        
        # 如果该摄像头在ws_tasks中，也需要移除
        if ws_id in ws_tasks and camera_id in ws_tasks[ws_id]:
            try:
                ws_tasks[ws_id].discard(camera_id)
            except Exception as e:
                print(f"从ws_tasks移除摄像头失败: {str(e)}")

if __name__ == '__main__':
    app.run(host=HOST, port=PORT)
