package com.example.dto.statistics;

import lombok.Data;

import java.util.List;
import java.util.Map;

/**
 * 统计分析返回对象
 */
@Data
public class StatisticsVO {
    /**
     * 异常事件等级分布
     * key: 异常等级(1-5)
     * value: 数量
     */
    private Map<Integer, Long> AbnormalEventLevelCount;

    /**
     * 异常事件处理状态分布
     * key: 处理状态(0:未处理 1:处理中 2:已处理)
     * value: 数量
     */
    private Map<Integer, Long> AbnormalEventStatusCount;

    /**
     * 最近7天异常事件趋势
     * key: 日期
     * value: 数量
     */
    private Map<String, Long> AbnormalEventTrend;

    /**
     * 摄像头设备状态分布
     * key: 状态(0:离线 1:在线 2:故障)
     * value: 数量
     */
    private Map<Integer, Long> cameraStatusCount;

    
}

   