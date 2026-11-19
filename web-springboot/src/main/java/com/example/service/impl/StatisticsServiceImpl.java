package com.example.service.impl;

import com.example.common.exception.BusinessException;
import com.example.detection.MonitoringHealthService;
import com.example.dto.statistics.*;
import com.example.service.StatisticsService;
import lombok.RequiredArgsConstructor;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import java.lang.management.ManagementFactory;
import java.time.*;
import java.util.*;

/** SQL aggregates only; event creation dates use the Shanghai business calendar. */
@Service @RequiredArgsConstructor
public class StatisticsServiceImpl implements StatisticsService {
    private final JdbcTemplate jdbc;
    private final MonitoringHealthService health;
    private static final ZoneId BUSINESS=ZoneId.of("Asia/Shanghai");
    // Legacy/manual create_time is local; service-generated create_time is UTC.
    private static final String CREATED="CASE WHEN a.source_key IS NULL THEN COALESCE(a.create_time,a.event_time) ELSE TIMESTAMPADD(HOUR,8,a.create_time) END";
    private static int integer(Object value){return value==null?0:Math.toIntExact(((Number)value).longValue());}
    private LocalDateTime boundary(String value,boolean end){
        if(value==null || value.isBlank())return null;
        try{
            if(value.length()==10)return LocalDate.parse(value).plusDays(end?1:0).atStartOfDay();
            return LocalDateTime.parse(value.replace(' ','T'));
        }catch(Exception e){throw new BusinessException(400,"统计时间格式无效");}
    }
    @Override public AbnormalEventStatisticsVO getAbnormalEventStatistics(String startTime,String endTime){
        var start=boundary(startTime,false);var end=boundary(endTime,true);
        if(start!=null && end!=null && (end.isBefore(start) || Duration.between(start,end).toDays()>3660))throw new BusinessException(400,"统计时间范围无效或超过十年");
        var args=new ArrayList<Object>();String where=" WHERE a.deleted=0";
        if(start!=null){where+=" AND ("+CREATED+")>=?";args.add(start);}
        if(end!=null){where+=" AND ("+CREATED+")"+(endTime.length()==10?"<?":"<=?");args.add(end);}
        var totals=jdbc.queryForMap("SELECT COUNT(*) AS total,SUM(CASE WHEN a.status=0 THEN 1 ELSE 0 END) AS pending,SUM(CASE WHEN a.status=1 THEN 1 ELSE 0 END) AS processing,SUM(CASE WHEN a.status=2 THEN 1 ELSE 0 END) AS handled FROM abnormal_event a"+where,args.toArray());
        var vo=new AbnormalEventStatisticsVO();
        vo.setTotalCount(integer(totals.get("total")));vo.setPendingCount(integer(totals.get("pending")));
        vo.setProcessingCount(integer(totals.get("processing")));vo.setHandledCount(integer(totals.get("handled")));
        vo.setTrendData(trend(where,args));
        vo.setTypeDistribution(jdbc.queryForList("SELECT a.level,COUNT(*) AS count FROM abnormal_event a"+where+" GROUP BY a.level ORDER BY a.level",args.toArray()));
        vo.setLocationHeatmap(jdbc.queryForList("SELECT COALESCE(a.location,'未知') AS location,COUNT(*) AS count FROM abnormal_event a"+where+" GROUP BY COALESCE(a.location,'未知') ORDER BY count DESC,location",args.toArray()));
        vo.setTypeNameDistribution(jdbc.queryForList("SELECT COALESCE(a.type,'待核验') AS type,COUNT(*) AS count FROM abnormal_event a"+where+" GROUP BY COALESCE(a.type,'待核验') ORDER BY count DESC,type",args.toArray()));
        return vo;
    }
    private List<Map<String,Object>> trend(String where,List<Object> args){
        var rows=jdbc.queryForList("SELECT CAST(("+CREATED+") AS DATE) AS date,COUNT(*) AS count FROM abnormal_event a"+where+" GROUP BY CAST(("+CREATED+") AS DATE) ORDER BY date",args.toArray());
        for(var row:rows)if(row.get("date")!=null)row.put("date",row.get("date").toString());
        return rows;
    }
    private List<Map<String,Object>> deviceDistribution(){return jdbc.queryForList("SELECT status,COUNT(*) AS count FROM camera WHERE deleted=0 GROUP BY status ORDER BY status");}
    @Override public DeviceStatusStatisticsVO getDeviceStatusStatistics(){
        var vo=new DeviceStatusStatisticsVO();int online=0,offline=0,fault=0,total=0;
        var states=deviceDistribution();
        for(var row:states){int count=integer(row.get("count"));total+=count;
            switch(integer(row.get("status"))){case 1->online+=count;case 0->offline+=count;case 2->fault+=count;}
        }
        vo.setTotalCount(total);vo.setOnlineCount(online);vo.setOfflineCount(offline);vo.setFaultCount(fault);vo.setUnknownCount(total-online-offline-fault);vo.setStatusDistribution(states);
        vo.setOnlineRateTrend(healthHistory());
        var faults=jdbc.queryForList("SELECT COALESCE(fault_type,'other') AS type,COUNT(*) AS count FROM camera WHERE deleted=0 AND status=2 GROUP BY COALESCE(fault_type,'other') ORDER BY type");
        var labels=Map.of("network","网络故障","hardware","硬件故障","software","软件故障","power","电源故障","other","其他故障");
        for(var row:faults)row.put("type",labels.getOrDefault(row.get("type"),"其他故障"));
        vo.setFaultTypeDistribution(faults);return vo;
    }
    private List<Map<String,Object>> healthHistory(){
        LocalDate today=LocalDate.now(BUSINESS);LocalDate first=today.minusDays(6);
        var rows=jdbc.queryForList("SELECT CAST(TIMESTAMPADD(HOUR,8,observed_at) AS DATE) AS date,COUNT(*) AS samples,SUM(CASE WHEN state='HEALTHY' THEN 1 ELSE 0 END) AS healthy,SUM(CASE WHEN state='UNVERIFIED' THEN 1 ELSE 0 END) AS unknown_count FROM monitoring_health_sample WHERE enabled=TRUE AND observed_at>=? GROUP BY CAST(TIMESTAMPADD(HOUR,8,observed_at) AS DATE) ORDER BY date",first.atStartOfDay(BUSINESS).withZoneSameInstant(ZoneOffset.UTC).toLocalDateTime());
        var counts=new HashMap<String,Map<String,Object>>();for(var row:rows)counts.put(row.get("date").toString(),row);
        var result=new ArrayList<Map<String,Object>>();
        for(int i=0;i<7;i++){
            String date=first.plusDays(i).toString();var sample=counts.get(date);
            int total=sample==null?0:integer(sample.get("samples")),unknown=sample==null?0:integer(sample.get("unknown_count"));int known=total-unknown;
            var point=new LinkedHashMap<String,Object>();point.put("date",date);point.put("sampleCount",total);point.put("knownSamples",known);point.put("unknownSamples",unknown);
            point.put("rate",known==0?null:Math.round(integer(sample.get("healthy"))*10000./known)/100.);
            result.add(point);
        }
        return result;
    }
    @Override public SystemOverviewVO getSystemOverview(){
        var vo=new SystemOverviewVO();LocalDate today=LocalDate.now(BUSINESS);
        vo.setTodayAbnormalEvents(jdbc.queryForObject("SELECT COUNT(*) FROM abnormal_event a WHERE a.deleted=0 AND ("+CREATED+")>=? AND ("+CREATED+")<?",Integer.class,today.atStartOfDay(),today.plusDays(1).atStartOfDay()));
        vo.setOnlineDevices(health.healthyCount());vo.setRunningDays((int)(ManagementFactory.getRuntimeMXBean().getUptime()/86400000L));
        var grouped=trend(" WHERE a.deleted=0 AND ("+CREATED+")>=? AND ("+CREATED+")<?",new ArrayList<>(List.of(today.minusDays(6).atStartOfDay(),today.plusDays(1).atStartOfDay())));
        var counts=new HashMap<String,Object>();for(var row:grouped)counts.put((String)row.get("date"),row.get("count"));
        var days=new ArrayList<Map<String,Object>>();for(int i=6;i>=0;i--){String date=today.minusDays(i).toString();days.add(Map.of("date",date,"AbnormalEvents",counts.getOrDefault(date,0L)));}
        vo.setWeeklyTrend(days);vo.setDeviceStatus(deviceDistribution());
        var recent=jdbc.queryForList("SELECT id,type,location,event_time AS time,status,level FROM abnormal_event WHERE deleted=0 ORDER BY event_time DESC,id DESC LIMIT 5");
        for(var row:recent)if(row.get("time") instanceof java.sql.Timestamp value)row.put("time",value.toLocalDateTime());
        vo.setRecentAlarms(recent);
        vo.setPendingItems(Map.of("AbnormalEvents",jdbc.queryForObject("SELECT COUNT(*) FROM abnormal_event WHERE deleted=0 AND status=0",Integer.class)));
        return vo;
    }
}
