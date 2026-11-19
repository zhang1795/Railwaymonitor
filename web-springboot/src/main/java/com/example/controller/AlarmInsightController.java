package com.example.controller;
import com.example.common.Result;
import com.example.common.exception.BusinessException;
import lombok.RequiredArgsConstructor;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.bind.annotation.*;
import java.util.*;

@RestController @RequiredArgsConstructor
public class AlarmInsightController {
    private final JdbcTemplate jdbc;private final EvidenceController evidence;private final RecordingController recordings;private final com.example.detection.NotificationOutbox notifications;
    @GetMapping("/Abnormal-event/{alarm}/insight")
    public Result<Map<String,Object>> detail(@PathVariable long alarm)throws Exception{
        if(jdbc.queryForObject("SELECT COUNT(*) FROM abnormal_event WHERE id=? AND deleted=0",Integer.class,alarm)==0)throw new BusinessException(404,"事件不存在");
        var result=new LinkedHashMap<String,Object>();
        result.put("risk",jdbc.queryForList("SELECT r.kind,r.state,r.risk_level,r.risk_since,r.last_inside,r.last_observed,r.missing_since,r.association,r.policy,s.policy AS session_policy FROM risk_incident r LEFT JOIN session_risk_policy s ON s.session_id=r.session_id WHERE r.alarm_id=?",alarm));
        result.put("sources",jdbc.queryForList("SELECT l.source_key,l.first_sequence,l.last_sequence,t.session_id,t.state,t.sequence_no FROM alarm_source_link l LEFT JOIN risk_track t ON t.source_key=l.source_key WHERE l.alarm_id=? ORDER BY l.first_sequence,l.source_key",alarm));
        result.put("transitions",jdbc.queryForList("SELECT from_state,to_state,reason,observed_at FROM alarm_transition WHERE alarm_id=? ORDER BY id DESC LIMIT 100",alarm));
        result.put("handling",jdbc.queryForList("SELECT user_id,action,before_status,after_status,result,created_at FROM alarm_handling_audit WHERE alarm_id=? ORDER BY id DESC LIMIT 100",alarm));
        result.put("notices",jdbc.queryForList("SELECT kind,created_at FROM alarm_notice WHERE alarm_id=? ORDER BY id DESC LIMIT 100",alarm));
        result.put("evidence",evidence.assets(alarm));
        result.put("recordings",recordings.forAlarm(alarm));
        result.put("notificationConfiguration",notifications.state());result.put("deliveries",notifications.forAlarm(alarm));
        result.put("evidenceWorker",jdbc.queryForList("SELECT pending_events,skipped,error,reported_at FROM worker_evidence_status WHERE worker_id IN (SELECT worker_id FROM monitoring_session WHERE session_id IN (SELECT session_id FROM risk_track WHERE alarm_id=?))",alarm));
        result.replaceAll((key,value)->{
            if(value instanceof java.util.List<?> rows)for(Object row:rows)if(row instanceof Map<?,?> map)com.example.detection.UtcValues.map((Map<String,Object>)map);
            return value;
        });
        return Result.success(result);
    }
}
