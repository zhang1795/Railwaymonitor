package com.example.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.example.dto.statistics.*;
import com.example.entity.Camera;
import com.example.entity.AbnormalEvent;
import com.example.service.*;

import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;

import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.time.temporal.ChronoUnit;
import java.util.*;
import java.util.stream.Collectors;

/**
 * 统计分析服务实现类
 */
@Service
@RequiredArgsConstructor
public class StatisticsServiceImpl implements StatisticsService {
    private final AbnormalEventService AbnormalEventService;
    private final CameraService cameraService;
 

    @Override
    public AbnormalEventStatisticsVO getAbnormalEventStatistics(String startTime, String endTime) {
        AbnormalEventStatisticsVO vo = new AbnormalEventStatisticsVO();
        
        // 查询时间范围内的异常事件
        LambdaQueryWrapper<AbnormalEvent> wrapper = new LambdaQueryWrapper<>();
        if (startTime != null && endTime != null) {
            wrapper.between(AbnormalEvent::getCreateTime, startTime, endTime);
        }
        List<AbnormalEvent> AbnormalEvents = AbnormalEventService.list(wrapper);
        
        // 统计总数
        vo.setTotalCount(AbnormalEvents.size());
        
        // 统计各状态数量
        Map<Integer, Long> statusCount = AbnormalEvents.stream()
                .collect(Collectors.groupingBy(AbnormalEvent::getStatus, Collectors.counting()));
        vo.setHandledCount(statusCount.getOrDefault(2, 0L).intValue());
        vo.setProcessingCount(statusCount.getOrDefault(1, 0L).intValue());
        vo.setPendingCount(statusCount.getOrDefault(0, 0L).intValue());
        
        // 事件趋势数据
        vo.setTrendData(getAbnormalEventTrend(AbnormalEvents));
        
        // 事件类型分布
        vo.setTypeDistribution(getAbnormalEventTypeDistribution(AbnormalEvents));
        
        // 事件位置热力图数据
        vo.setLocationHeatmap(getAbnormalEventLocationHeatmap(AbnormalEvents));

        // 类型统计
        vo.setTypeNameDistribution(getAbnormalEventTypeNameDistribution(AbnormalEvents));
        
        return vo;
    }

    @Override
    public DeviceStatusStatisticsVO getDeviceStatusStatistics() {
        DeviceStatusStatisticsVO vo = new DeviceStatusStatisticsVO();
        
        // 查询所有摄像头设备
        List<Camera> cameras = cameraService.list();
        
        // 统计总数
        vo.setTotalCount(cameras.size());
        
        // 统计各状态数量
        Map<Integer, Long> statusCount = cameras.stream()
                .collect(Collectors.groupingBy(Camera::getStatus, Collectors.counting()));
        vo.setOnlineCount(statusCount.getOrDefault(1, 0L).intValue());
        vo.setOfflineCount(statusCount.getOrDefault(0, 0L).intValue());
        vo.setFaultCount(statusCount.getOrDefault(2, 0L).intValue());
        
        // 设备状态分布
        vo.setStatusDistribution(getDeviceStatusDistribution(cameras));
        
        // 设备在线率趋势
        vo.setOnlineRateTrend(getDeviceOnlineRateTrend());
        
        // 设备故障类型分布
        vo.setFaultTypeDistribution(getDeviceFaultTypeDistribution());
        
        return vo;
    }

   



    @Override
    public SystemOverviewVO getSystemOverview() {
        LocalDateTime today = LocalDateTime.now().withHour(0).withMinute(0).withSecond(0).withNano(0);
        
        SystemOverviewVO vo = new SystemOverviewVO();
        vo.setTodayAbnormalEvents(countTodayAbnormalEvents(today));
        vo.setOnlineDevices(countOnlineDevices());
        vo.setRunningDays(calculateRunningDays());
        vo.setWeeklyTrend(getWeeklyTrend());
        vo.setDeviceStatus(getDeviceStatusDistribution());
        vo.setRecentAlarms(getRecentAlarms());
        vo.setPendingItems(getPendingItems());
        return vo;
    }

    // 辅助方法
    private List<Map<String, Object>> getAbnormalEventTrend(List<AbnormalEvent> events) {
        return events.stream()
                .collect(Collectors.groupingBy(
                        e -> e.getCreateTime().format(DateTimeFormatter.ISO_DATE),
                        Collectors.counting()))
                .entrySet().stream()
                .map(e -> {
                    Map<String, Object> map = new HashMap<>();
                    map.put("date", e.getKey());
                    map.put("count", e.getValue());
                    return map;
                })
                .collect(Collectors.toList());
    }

    private List<Map<String, Object>> getAbnormalEventTypeDistribution(List<AbnormalEvent> events) {
        return events.stream()
                .collect(Collectors.groupingBy(AbnormalEvent::getLevel, Collectors.counting()))
                .entrySet().stream()
                .map(e -> {
                    Map<String, Object> map = new HashMap<>();
                    map.put("level", e.getKey());
                    map.put("count", e.getValue());
                    return map;
                })
                .collect(Collectors.toList());
    }

    private List<Map<String, Object>> getAbnormalEventLocationHeatmap(List<AbnormalEvent> events) {
        return events.stream()
                .collect(Collectors.groupingBy(AbnormalEvent::getLocation, Collectors.counting()))
                .entrySet().stream()
                .map(e -> {
                    Map<String, Object> map = new HashMap<>();
                    map.put("location", e.getKey());
                    map.put("count", e.getValue());
                    return map;
                })
                .collect(Collectors.toList());
    }

    private List<Map<String, Object>> getAbnormalEventTypeNameDistribution(List<AbnormalEvent> events) {
    // 逻辑与位置统计完全一致：分组 → 统计数量 → 格式转换
    return events.stream()
            // 按异常类型（中文 type 字段）分组，统计每组数量
            .collect(Collectors.groupingBy(AbnormalEvent::getType, Collectors.counting()))
            // 转换为前端需要的 Map 格式（key: type(中文), value: count）
            .entrySet().stream()
            .map(entry -> {
                Map<String, Object> map = new HashMap<>();
                map.put("type", entry.getKey()); // 中文类型名称（如“牛”“防撞设备”“水害”）
                map.put("count", entry.getValue()); // 该类型的异常事件数
                return map;
            })
            .collect(Collectors.toList());
    }

    private List<Map<String, Object>> getDeviceStatusDistribution(List<Camera> cameras) {
        return cameras.stream()
                .collect(Collectors.groupingBy(Camera::getStatus, Collectors.counting()))
                .entrySet().stream()
                .map(e -> {
                    Map<String, Object> map = new HashMap<>();
                    map.put("status", e.getKey());
                    map.put("count", e.getValue());
                    return map;
                })
                .collect(Collectors.toList());
    }

    private List<Map<String, Object>> getDeviceOnlineRateTrend() {
        List<Map<String, Object>> result = new ArrayList<>();
        LocalDateTime now = LocalDateTime.now();
        
        // 获取最近7天的在线率数据
        for (int i = 6; i >= 0; i--) {
            LocalDateTime date = now.minusDays(i).withHour(0).withMinute(0).withSecond(0);
            String dateStr = date.format(DateTimeFormatter.ISO_DATE);
            
            // 统计当天的设备总数和在线数
            List<Camera> cameras = cameraService.list(new LambdaQueryWrapper<Camera>()
                    .le(Camera::getCreateTime, date));
            long total = cameras.size();
            long online = cameras.stream()
                    .filter(c -> c.getStatus() == 1)
                    .count();
            
            // 计算在线率
            double rate = total == 0 ? 0 : (double) online / total * 100;
            
            Map<String, Object> data = new HashMap<>();
            data.put("date", dateStr);
            data.put("rate", String.format("%.2f", rate));
            result.add(data);
        }
        
        return result;
    }

    private List<Map<String, Object>> getDeviceFaultTypeDistribution() {
        List<Map<String, Object>> result = new ArrayList<>();
        
        // 查询所有故障状态的设备
        List<Camera> faultDevices = cameraService.list(new LambdaQueryWrapper<Camera>()
                .eq(Camera::getStatus, 2));
        
        // 统计各故障类型数量，处理 null 值的情况
        Map<String, Long> faultTypeCounts = faultDevices.stream()
                .collect(Collectors.groupingBy(
                    camera -> camera.getFaultType() == null ? "other" : camera.getFaultType(),
                    Collectors.counting()
                ));
        
        // 转换为前端需要的格式
        faultTypeCounts.forEach((type, count) -> {
            Map<String, Object> data = new HashMap<>();
            data.put("type", getFaultTypeText(type));
            data.put("count", count);
            result.add(data);
        });
        
        return result;
    }

    private String getFaultTypeText(String type) {
        if (type == null) {
            return "其他故障";
        }
        switch (type) {
            case "network":
                return "网络故障";
            case "hardware":
                return "硬件故障";
            case "software":
                return "软件故障";
            case "power":
                return "电源故障";
            case "other":
            default:
                return "其他故障";
        }
    }

   

   
    


    private Integer countTodayAbnormalEvents(LocalDateTime today) {
        return (int) AbnormalEventService.list(new LambdaQueryWrapper<AbnormalEvent>()
                .ge(AbnormalEvent::getCreateTime, today))
                .size();
    }

   

    

    private Integer countOnlineDevices() {
        return (int) cameraService.list(new LambdaQueryWrapper<Camera>()
                .eq(Camera::getStatus, 1))
                .size();
    }

    private Integer calculateRunningDays() {
        // 直接返回模拟的系统运行天数：7天
        return 7;
    }

    private List<Map<String, Object>> getWeeklyTrend() {
        LocalDateTime startOfWeek = LocalDateTime.now().minusDays(6).withHour(0).withMinute(0).withSecond(0);
        
        // 获取异常事件数据
        List<AbnormalEvent> AbnormalEvents = AbnormalEventService.list(new LambdaQueryWrapper<AbnormalEvent>()
                .ge(AbnormalEvent::getCreateTime, startOfWeek));
        
      
        
        
        
        // 创建日期列表（最近7天）
        List<String> dates = new ArrayList<>();
        for (int i = 6; i >= 0; i--) {
            dates.add(LocalDateTime.now().minusDays(i).format(DateTimeFormatter.ISO_DATE));
        }
        
        // 统计每天的事件数量
        Map<String, Long> AbnormalEventCounts = AbnormalEvents.stream()
                .collect(Collectors.groupingBy(
                        e -> e.getCreateTime().format(DateTimeFormatter.ISO_DATE),
                        Collectors.counting()));
        
        
       
        
        // 组装结果
        return dates.stream().map(date -> {
            Map<String, Object> map = new HashMap<>();
            map.put("date", date);
            map.put("AbnormalEvents", AbnormalEventCounts.getOrDefault(date, 0L));
            return map;
        }).collect(Collectors.toList());
    }

    private List<Map<String, Object>> getDeviceStatusDistribution() {
        List<Camera> cameras = cameraService.list();
        return cameras.stream()
                .collect(Collectors.groupingBy(Camera::getStatus, Collectors.counting()))
                .entrySet().stream()
                .map(e -> {
                    Map<String, Object> map = new HashMap<>();
                    map.put("status", e.getKey());
                    map.put("count", e.getValue());
                    return map;
                })
                .collect(Collectors.toList());
    }

    private List<Map<String, Object>> getRecentAlarms() {
        // 获取所有异常事件
        return AbnormalEventService.list(new LambdaQueryWrapper<AbnormalEvent>()
                .orderByDesc(AbnormalEvent::getEventTime))
                .stream()
                .map(event -> {
                    Map<String, Object> map = new HashMap<>();
                    map.put("id", event.getId());
                    map.put("type", event.getType());
                    map.put("location", event.getLocation());
                    map.put("time", event.getEventTime());
                    map.put("status", event.getStatus());
                    map.put("level", event.getLevel());  // 确保包含level字段
                    return map;
                })
                .collect(Collectors.toList());
    }

    private Map<String, Integer> getPendingItems() {
        Map<String, Integer> result = new HashMap<>();
        
        // 待处理异常事件
        result.put("AbnormalEvents", (int) AbnormalEventService.count(new LambdaQueryWrapper<AbnormalEvent>()
                .eq(AbnormalEvent::getStatus, 0)));
        
        
        
        return result;
    }

   
} 