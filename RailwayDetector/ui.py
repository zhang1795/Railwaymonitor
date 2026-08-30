import paho.mqtt.client as mqtt
import datetime
import time
import threading
import cv2
import json
import os
import sys
from json import dumps
from datetime import date
from model_init import predict, detect_bounding_box
from minio import Minio
from tracker import Sort
from queue import Queue
import numpy as np
from sendMsg import send, connect
import imageio.v2 as iio
import tkinter as tk
from io import StringIO
import base64  # 添加base64模块用于图像编码

'''
class StdoutRedirector:
    def __init__(self, text_widget):
        self.text_space = text_widget
        self.stdout = sys.stdout
        sys.stdout = self

    def write(self, s):
        self.text_space.insert(tk.END, s)
        self.text_space.see(tk.END)

    def flush(self):
        pass

    def __del__(self):
        sys.stdout = self.stdout

root = tk.Tk()
output_text = tk.Text(root)
output_text.pack()

redirector = StdoutRedirector(output_text)
'''

image_queue = Queue()
Message_queue = Queue()
# flag = False
mot_tracker = Sort(max_age=1, min_hits=5, iou_threshold=0.3)
HOST = os.getenv("MQTT_HOST", "127.0.0.1")
PORT = int(os.getenv("MQTT_PORT", "1883"))
DETECTOR_OUTPUT_DIR = os.path.abspath(os.getenv(
    "DETECTOR_OUTPUT_DIR",
    os.path.join(os.path.dirname(__file__), "..", "workspace", "runtime", "detector-output")
))
os.makedirs(DETECTOR_OUTPUT_DIR, exist_ok=True)
colours = np.random.rand(32, 3) * 255
minio_endpoint = os.getenv("MINIO_ENDPOINT")
minio_access_key = os.getenv("MINIO_ACCESS_KEY")
minio_secret_key = os.getenv("MINIO_SECRET_KEY")
minio_client = None
if minio_endpoint and minio_access_key and minio_secret_key:
    minio_client = Minio(
        minio_endpoint.replace('https://', '').replace('http://', ''),
        access_key=minio_access_key,
        secret_key=minio_secret_key,
        secure=os.getenv("MINIO_SECURE", "false").lower() == "true"
    )


##上面代码实例化Minio客户端并与服务端建立连接


def upload_video(video_name):
    if minio_client is None:
        raise RuntimeError("MinIO 未配置；初步部署阶段已禁用视频上传")
    video_path = video_name  ##上传文件的本地路径
    found = minio_client.bucket_exists("video")  # 在minio中寻找是否有这样的文件桶 该例子文件桶名为video 如果没有则创建
    if not found:
        minio_client.make_bucket("video")
    else:
        print("bucket {} already exists".format("video"))
    # mp4_files = "xnjdxnjd.mp4"
    # print(mp4_files)
    # video_path = mp4_files
    current_date = date.today()
    path = str(current_date)
    object_prefix = f"{path}/"
    object_name = f"{object_prefix}{video_name}"
    with open(video_path, "rb") as file_data:
        result = minio_client.put_object(
            "video",
            object_name,
            file_data,
            os.path.getsize(video_path)
        )
        ##上传本地文件至文件桶
        if result:
            print("视频上传成功！")

    url = minio_client.presigned_get_object("video", video_path)
    print(url)
    return object_name


thread_completed = threading.Event()
thread_result = None


def run_thread(video_name):
    global thread_result
    thread_result = upload_video(video_name)
    thread_completed.set()



def generateName(cls):
    if (cls == 'Railway collision avoidance facilities'):
        name = '防撞设备'
    elif (cls == 'balloon'):
        name = '气球'
    elif (cls == 'cow'):
        name = '牛'
    elif (cls == 'flood'):
        name = '水害'
    elif (cls == 'huapo'):
        name = '滑坡'
    elif (cls == 'illegal construction'):
        name = '违规建筑'
    elif (cls == 'kite'):
        name = '风筝'
    elif (cls == 'luoshi'):
        name = '落石'
    elif (cls == 'nest'):
        name = '鸟巢'
    elif (cls == 'placard'):
        name = '广告牌'
    elif (cls == 'pothole'):
        name = '坑洞'
    elif (cls == 'trash'):
        name = '垃圾'
    else:
        name = '工人'
    return name


def on_connect(client, userdata, flags, rc, properties):
    print("Connected with result code: " + str(rc))
    client.subscribe('/UAV/videoTopic/post', qos=0)


executed_payloads = set()


def on_message(client, userdata, msg):
    payload1 = msg.payload.decode("utf-8")
    print(type(payload1))
    print(payload1)
    if payload1 not in executed_payloads:
        executed_payloads.add(payload1)
        print("加入后", executed_payloads)
        worker = threading.Thread(target=make_result, args=(payload1,), daemon=True)
        worker.start()


def make_result(payload):
    video_index = 1
    # 每个检测任务使用独立队列和跟踪器，避免多摄像头并发时帧、消息和
    # objectID 相互污染。
    image_queue = Queue()
    Message_queue = Queue()
    mot_tracker = Sort(max_age=1, min_hits=5, iou_threshold=0.3)
    raw_data = json.loads(payload)
    print(raw_data['videoUrl'])
    output_prefix = ''.join(
        char if char.isalnum() or char in ('-', '_') else '_'
        for char in str(raw_data['videoId'])
    )
    True_starttime = raw_data['startTime']
    my_True_starttime = datetime.datetime.strptime(True_starttime, "%Y-%m-%d %H:%M:%S")
    cap = cv2.VideoCapture(raw_data['videoUrl'])
    if not cap.isOpened():
        print(f"无法打开待检测视频: {raw_data['videoUrl']}")
        executed_payloads.discard(payload)
        return
    # cap = [cv2.VideoCapture(file) for file in video_files]
    fps = int(cap.get(cv2.CAP_PROP_FPS)) or 25  # 帧数，无法读取时使用安全默认值
    save_num = 2 * fps
    print("save_num:", save_num)
    width, height = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))  # 宽高
    size = (int(width), int(height))
    print(size)
    # video_name = f'{output_prefix}_{video_index}.mp4v'
    video_name = os.path.join(DETECTOR_OUTPUT_DIR, f'{output_prefix}_{video_index}.mp4')
    # 使用OpenCV的VideoWriter，更稳定的视频写入方式
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    videowriter = cv2.VideoWriter(video_name, fourcc, fps, size)
    startTime = datetime.datetime.now()  # .strftime("%Y-%m-%d %H:%M:%S.%f")
    flag = 0
    while cap.isOpened():
        ret, frame = cap.read()  # 读帧
        if not ret or frame is None:
            if flag != 0:
                connect()
                for i in range(image_queue.qsize()):
                    frame2 = image_queue.queue[i]
                    videowriter.write(frame2)
                while not Message_queue.empty():
                    element = Message_queue.get()
                    obj = json.loads(element)
                    obj['videoFileUrl'] = thread_result
                    if obj['result']:
                        msg = dumps(obj, ensure_ascii=False)
                        send(msg)
            while not image_queue.empty():
                image_queue.get()
            while not Message_queue.empty():
                Message_queue.get()
            if videowriter is not None:
                videowriter.release()
            executed_payloads.discard(payload)
            print(executed_payloads)
            break

        img_return, score = predict(frame)
        if image_queue.qsize() >= save_num:
            image_queue.get()
            image_queue.put(frame)
        else:
            image_queue.put(frame)
        print(image_queue.qsize())
        if (image_queue.qsize() == save_num and flag != 0):
            connect()
            flag = 0
            for i in range(image_queue.qsize()):
                frame2 = image_queue.queue[i]
                videowriter.write(frame2)
            for i in range(image_queue.qsize()):
                image_queue.get()
            if videowriter is not None:
                videowriter.release()
            # timer_thread = threading.Timer(1, run_thread, args=(video_name,)).start()
            # timer_thread = threading.Timer(1, run_thread)
            # timer_thread.start()
            # thread_completed.wait()
            print(video_name)
            # thread_result = upload_video(video_name)
            video_index += 1
            # 重新初始化VideoWriter，使用相同的稳定设置
            video_name = os.path.join(DETECTOR_OUTPUT_DIR, f'{output_prefix}_{video_index}.mp4')
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            videowriter = cv2.VideoWriter(video_name, fourcc, fps, size)
            while not Message_queue.empty():
                element = Message_queue.get()
                obj = json.loads(element)
                obj['videoFileUrl'] = thread_result
                if obj['result']:
                    msg = dumps(obj, ensure_ascii=False)
                    send(msg)

        if img_return:
            my_endtime = datetime.datetime.now()
            duration = my_endtime - startTime
            detect_boxes, detect_classes = detect_bounding_box(frame)
            frametime = my_True_starttime + duration
            return_frametime = str(frametime)
            # video_frametime = time.time()
            tracker = mot_tracker.update(detect_boxes, detect_classes)
            endTime = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
            i = 0
            result = []

            # 先复制原始帧，然后缩放用于传输（不在原始帧上绘制）
            frame_copy = frame.copy()

            # 获取原始图像尺寸
            orig_height, orig_width = frame_copy.shape[:2]

            # 缩小图像尺寸以减少base64编码长度
            max_width, max_height = 640, 480
            scale = 1.0  # 默认不缩放
            if orig_width > max_width or orig_height > max_height:
                scale = min(max_width / orig_width, max_height / orig_height)
                new_width = int(orig_width * scale)
                new_height = int(orig_height * scale)
                frame_copy = cv2.resize(frame_copy, (new_width, new_height))

            # 现在在缩放后的图像上绘制清晰的检测框
            for d in tracker:
                # 获取原始坐标
                orig_x1 = int(float(d[0]))
                orig_y1 = int(float(d[1]))
                orig_x2 = int(float(d[2]))
                orig_y2 = int(float(d[3]))

                # 按缩放比例调整坐标
                x1 = int(orig_x1 * scale)
                y1 = int(orig_y1 * scale)
                x2 = int(orig_x2 * scale)
                y2 = int(orig_y2 * scale)

                pred_id = str(int(d[4]))
                rgb = colours[int(d[4]) % 32]
                pred_cls = d[5]
                confidence = score[i]
                i += 1
                imscore = str(confidence)
                name = generateName(pred_cls)
                text = pred_id + ':' + pred_cls + imscore

                # 在缩放后的图像上绘制清晰的检测框
                cv2.rectangle(frame_copy, (x1, y1), (x2, y2), (0, 0, 255), 2)  # 减小线宽适应小图

                # 计算文字位置和大小，适应缩放后的图像
                font = cv2.FONT_HERSHEY_SIMPLEX
                font_scale = 0.5  # 适应小图的字体大小
                thickness = 1

                # 将文字放在检测框上方
                text_x = x1
                text_y = y1 - 5 if y1 > 20 else y1 + 15
                cv2.putText(frame_copy, text, (text_x, text_y), font, font_scale, (0, 0, 255), thickness)

            # 在缩放后的图像左下角添加清晰的红色时间信息
            frame_height, frame_width = frame_copy.shape[:2]
            time_text = return_frametime  # 使用完整的时间字符串

            # 设置适应小图的时间显示样式
            font = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = 0.5  # 适应小图的字体大小
            color = (0, 0, 255)  # 红色 (BGR格式)
            thickness = 1

            # 获取文本尺寸以便定位
            (text_width, text_height), baseline = cv2.getTextSize(time_text, font, font_scale, thickness)

            # 计算左下角位置（留一些边距）
            x_pos = 5
            y_pos = frame_height - 5

            # 先绘制一个半透明的黑色背景矩形，增加文字可读性
            overlay = frame_copy.copy()
            cv2.rectangle(overlay, (x_pos - 3, y_pos - text_height - 3),
                          (x_pos + text_width + 3, y_pos + baseline + 3), (0, 0, 0), -1)
            cv2.addWeighted(overlay, 0.7, frame_copy, 0.3, 0, frame_copy)

            # 绘制红色时间文字
            cv2.putText(frame_copy, time_text, (x_pos, y_pos), font, font_scale, color, thickness)

            # 使用较低的JPEG质量以减少文件大小
            encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 50]  # 质量设为50%
            _, buffer = cv2.imencode('.jpg', frame_copy, encode_param)
            frame_base64 = base64.b64encode(buffer).decode('utf-8')

            # 检查base64编码长度，如果过长则进一步压缩
            max_base64_length = 50000  # 限制base64最大长度为50KB

            if len(frame_base64) > max_base64_length:
                encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 30]  # 进一步降低质量
                _, buffer = cv2.imencode('.jpg', frame_copy, encode_param)
                frame_base64 = base64.b64encode(buffer).decode('utf-8')
                print(f"Frame base64 length after first compression: {len(frame_base64)}")

                # 如果还是太大，再次压缩
                if len(frame_base64) > max_base64_length:
                    encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 15]  # 极低质量
                    _, buffer = cv2.imencode('.jpg', frame_copy, encode_param)
                    frame_base64 = base64.b64encode(buffer).decode('utf-8')
                    print(f"Frame base64 length after second compression: {len(frame_base64)}")

                    # 如果还是太大，就不发送视频帧
                    if len(frame_base64) > max_base64_length:
                        print(f"Frame too large ({len(frame_base64)}), skipping videoInfo")
                        frame_base64 = ""  # 不发送视频帧
            else:
                print(f"Frame base64 length: {len(frame_base64)}")

            # 同时在原始帧上绘制检测框（用于视频录制）
            temp_i = 0
            for d in tracker:
                orig_x1 = int(float(d[0]))
                orig_y1 = int(float(d[1]))
                orig_x2 = int(float(d[2]))
                orig_y2 = int(float(d[3]))
                pred_id = str(int(d[4]))
                pred_cls = d[5]
                confidence = score[temp_i]
                temp_i += 1
                name = generateName(pred_cls)
                text = pred_id + ':' + pred_cls + str(confidence)

                # 在原始帧上绘制（用于视频录制）
                cv2.rectangle(frame, (orig_x1, orig_y1), (orig_x2, orig_y2), (0, 0, 255), 3)
                cv2.putText(frame, text, (int((orig_x1 + orig_x2) / 2), int((orig_y1 + orig_y2) / 2)), 2, 1,
                            (0, 0, 255), 3)

            # 重新构建检测结果数据
            i = 0
            for d in tracker:
                x1 = int(float(d[0]))
                y1 = int(float(d[1]))
                x2 = int(float(d[2]))
                y2 = int(float(d[3]))
                pred_id = str(int(d[4]))
                pred_cls = d[5]
                confidence = score[i]
                i += 1
                name = generateName(pred_cls)
                position = {'x1': x1, 'y1': y1, 'x2': x2, 'y2': y2}
                # 构建检测结果，不再包含videoInfo（移到消息顶层）
                result_i = {
                    'objectID': pred_id,
                    'time': return_frametime,
                    'objectDetect': name,
                    'score': confidence,
                    'position': position
                }
                result.append(result_i)

            if result:
                print(result)
                flag = 1
                for i in range(image_queue.qsize()):
                    frame1 = image_queue.queue[i]
                    videowriter.write(frame1)
                for i in range(image_queue.qsize()):
                    image_queue.get()

            # 构建返回消息，将videoInfo放在顶层
            return_msg = {
                "videoId": raw_data['videoId'],
                'videoFileUrl': thread_result,
                'deviceName': raw_data['deviceName'],
                "startTime": str(startTime),
                "endTime": str(endTime),
                'result': result
            }

            # 只有在有有效视频帧数据时才添加videoInfo
            if frame_base64:
                return_msg['videoInfo'] = frame_base64
            return_msg_body = dumps(return_msg, ensure_ascii=False)

            # 添加调试信息
            print(f"Return message body length: {len(return_msg_body)}")
            print(f"Number of results: {len(result)}")
            has_video_info = 'videoInfo' in return_msg
            video_info_len = len(return_msg['videoInfo']) if has_video_info else 0
            print(f"Message has top-level videoInfo: {has_video_info}, length: {video_info_len}")

            Message_queue.put(return_msg_body)

    cap.release()
    # executed_payloads.remove(payload)
    # print(executed_payloads)
    # threading.Timer(1, upload_video, args=(video_name,)).start()
    # upload_video(video_name,video_name)


client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.connect(HOST, PORT, 60)  # 60为keepalive的时间间隔
# client.subscribe('/UAV/videoTopic/post', qos=0) 不必要
client.on_connect = on_connect
client.on_message = on_message
client.loop_forever()  # 保持连接
# root.mainloop() 
