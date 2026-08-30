package com.example.controller;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

import com.example.common.Result;
import com.example.dto.statistics.*;
import com.example.service.StatisticsService;

/**
 * 统计分析控制器
 */
@Tag(name = "统计分析", description = "数据统计分析相关接口")
@RestController
@RequestMapping("/statistics")
@RequiredArgsConstructor
public class StatisticsController {

    private final StatisticsService statisticsService;

    /**
     * 获取异常事件统计数据
     */
    @Operation(summary = "异常事件统计", description = "获取异常事件相关的统计数据")
    @GetMapping("/Abnormal-event")
    public Result<AbnormalEventStatisticsVO> getAbnormalEventStatistics(
            @Parameter(description = "开始时间") @RequestParam(required = false) String startTime,
            @Parameter(description = "结束时间") @RequestParam(required = false) String endTime) {
        return Result.success(statisticsService.getAbnormalEventStatistics(startTime, endTime));
    }

    /**
     * 获取设备状态统计数据
     */
    @Operation(summary = "设备状态统计", description = "获取摄像头设备状态相关的统计数据")
    @GetMapping("/device-status")
    public Result<DeviceStatusStatisticsVO> getDeviceStatusStatistics() {
        return Result.success(statisticsService.getDeviceStatusStatistics());
    }


   

    /**
     * 获取系统概览数据
     */
    @Operation(summary = "系统概览统计", description = "获取系统整体概览统计数据")
    @GetMapping("/overview")
    public Result<SystemOverviewVO> getSystemOverview() {
        return Result.success(statisticsService.getSystemOverview());
    }
} 