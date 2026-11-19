import mqtt from 'mqtt'
import type { MqttClient as MqttClientType, IClientOptions, OnMessageCallback } from 'mqtt'

// 定义MQTT消息类型
export interface DetectionResult {
  objectID: string;          // 对应后端的 'objectID'（字段名完全一致）
  time: string;              // 对应后端的 'time'（检测时间，字符串格式）
  objectDetect: string;      // 对应后端的 'objectDetect'（物体类型，替代原 objectType）
  score: number;             // 对应后端的 'score'（置信度，替代原 confidence）
  position: {                // 对应后端的 'position'（位置信息，替代原 bbox）
    x1: number;              // 假设位置包含 x1 坐标（根据实际数据补充）
    y1: number;
    x2: number;
    y2: number;
  };
}

export interface MqttMessage {
  videoId: string;           // 必选，视频ID
  videoFileUrl: string;      // 必选，视频文件URL（后端 thread_result）
  deviceName: string;        // 必选，设备名
  startTime: string;         // 必选，开始时间（字符串格式）
  endTime: string;           // 必选，结束时间（字符串格式）
  result: DetectionResult[]; // 必选，检测结果数组（可能为空数组）
  videoInfo?: string;        // 可选，base64视频帧（仅当后端有frame_base64时存在）
}

class MqttClient {
  private client: MqttClientType | null = null
  private messageHandlers = new Map<string, (message: unknown) => void>()
  private subscriptions = new Map<string, 0 | 1 | 2>()

  /**
   * 连接MQTT服务器
   * @param host MQTT服务器地址
   * @param port MQTT服务器端口
   * @param options 额外的连接选项
   */
  connect(
    host: string = window.location.hostname,
    port: number = Number(import.meta.env.VITE_MQTT_WS_PORT || 8083),
    options?: IClientOptions
  ) {
    if (this.client) return // An existing client also owns its reconnect loop.

    // 合并默认选项和用户选项
    const clientOptions: IClientOptions = {
      keepalive: 60,
      reconnectPeriod: 3000,
      connectTimeout: 45000,
      ...options
    }

    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
    this.client = mqtt.connect(`${protocol}://${host}:${port}/mqtt`, clientOptions)

    this.client.on('connect', () => {
      console.log('MQTT连接成功')
      for (const [topic, qos] of this.subscriptions) this.client?.subscribe(topic, { qos })
    })

    this.client.on('message', this.handleMessage.bind(this))

    this.client.on('error', (error) => {
      console.error('MQTT连接错误:', error)
    })

    this.client.on('reconnect', () => {
      console.log('MQTT正在重连...')
    })

    this.client.on('close', () => {
      console.log('MQTT连接已关闭')
    })
  }

  /**
   * 断开MQTT连接
   */
  disconnect() {
    if (this.client) {
      this.client.end()
      this.client = null
    }
  }

  /**
   * 发布消息到指定主题
   * @param topic 主题名称
   * @param message 消息内容（对象会自动转换为JSON字符串）
   * @param qos QoS等级，默认0
   */
  publish(topic: string, message: any, qos: 0 | 1 | 2 = 2) {
    if (!this.client || !this.client.connected) {
      console.warn('MQTT未连接，无法发布消息')
      return
    }

    try {
      // 关键修复：确保消息被正确序列化为JSON字符串
      const payload = typeof message === 'object' 
        ? JSON.stringify(message) 
        : message.toString()
      
      console.log(`发布MQTT消息到主题 ${topic}:`, payload)
      
      this.client.publish(topic, payload, { qos }, (error) => {
        if (error) {
          console.error('MQTT发布失败:', error)
        } else {
          console.log('MQTT消息发布成功')
        }
      })
    } catch (error) {
      console.error('MQTT消息序列化失败:', error)
    }
  }

  /**
   * 订阅主题
   * @param topic 主题名称
   * @param qos QoS等级，默认0
   */
  subscribe(topic: string, qos: 0 | 1 | 2 = 0) {
    this.subscriptions.set(topic, qos)
    if (!this.client || !this.client.connected) {
      console.warn('MQTT未连接，无法订阅主题')
      return
    }

    this.client.subscribe(topic, { qos }, (error) => {
      if (error) {
        console.error(`订阅主题 ${topic} 失败:`, error)
      } else {
        console.log(`已订阅主题 ${topic}`)
      }
    })
  }

  /**
   * 取消订阅主题
   * @param topic 主题名称
   */
  unsubscribe(topic: string) {
    this.subscriptions.delete(topic)
    if (!this.client || !this.client.connected) {
      console.warn('MQTT未连接，无法取消订阅主题')
      return
    }

    this.client.unsubscribe(topic, (error) => {
      if (error) {
        console.error(`取消订阅主题 ${topic} 失败:`, error)
      } else {
        console.log(`已取消订阅主题 ${topic}`)
      }
    })
  }

  /**
   * 注册消息处理器
   * @param topic 主题名称
   * @param handler 消息处理函数
   */
  registerHandler<T = MqttMessage>(topic: string, handler: (message: T) => void) {
    this.messageHandlers.set(topic, handler as (message: unknown) => void)
  }

  /**
   * 移除消息处理器
   * @param topic 主题名称
   */
  removeHandler(topic: string) {
    this.messageHandlers.delete(topic)
  }

  /**
   * 处理接收到的MQTT消息
   * @param topic 主题名称
   * @param message 消息内容
   * @param packet 消息包
   */
  private handleMessage(topic: string, message: Buffer, packet: mqtt.Packet) {
    try {
      console.log(`收到MQTT消息，主题: ${topic}，长度: ${message.length} bytes`)
      
      // 尝试解析JSON消息
      const messageStr = message.toString()
      const messageObj: MqttMessage = JSON.parse(messageStr)
      
      // 调用对应的消息处理器
      const handler = this.messageHandlers.get(topic)
      if (handler) {
        handler(messageObj)
      } else {
        console.warn(`未找到主题 ${topic} 的消息处理器`)
      }
    } catch (error) {
      console.error('MQTT消息解析错误:', error, '原始消息:', message.toString())
    }
  }

  /**
   * 检查MQTT连接状态
   * @returns 是否连接
   */
  isConnected(): boolean {
    return !!this.client?.connected
  }
}

// 创建单例实例
const mqttClient = new MqttClient()

export default mqttClient
