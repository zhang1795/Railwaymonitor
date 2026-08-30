package com.example.service;

import com.example.dto.statistics.*;

/**
 * 统计分析服务接口
 */
public interface StatisticsService {

    /**
     * 获取异常事件统计数据
     *
     * @param startTime 开始时间
     * @param endTime   结束时间
     * @return 异常事件统计数据
     */
    AbnormalEventStatisticsVO getAbnormalEventStatistics(String startTime, String endTime);

    /**
     * 获取设备状态统计数据
     *
     * @return 设备状态统计数据
     */
    DeviceStatusStatisticsVO getDeviceStatusStatistics();
    

    /**
     * 获取系统概览统计数据
     *
     * @return 系统概览统计数据
     */
    SystemOverviewVO getSystemOverview();
} 