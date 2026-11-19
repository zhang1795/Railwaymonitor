package com.example.detection;

import com.fasterxml.jackson.databind.*;
import lombok.RequiredArgsConstructor;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import java.time.*;
import java.util.*;

/** Health of the detection chain, never a reconstruction of camera uptime. */
@Service @RequiredArgsConstructor
public class MonitoringHealthService {
    private final JdbcTemplate jdbc;private final ObjectMapper json;private final NotificationOutbox notifications;
    private static LocalDateTime time(Object value){return value instanceof java.sql.Timestamp t?t.toLocalDateTime():(LocalDateTime)value;}
    private static Instant instant(Object value){return time(value).toInstant(ZoneOffset.UTC);}
    private Map<String,Object> parsed(String text){try{return json.readValue(text,new com.fasterxml.jackson.core.type.TypeReference<>(){});}catch(Exception e){return Map.of();}}
    public void metric(long camera,String session,JsonNode value){
        if(!value.isObject())return;
        var safe=new LinkedHashMap<String,Object>();Instant now=Instant.now();
        for(String key:List.of("sourceFps","effectiveFps","processedFrames","decodedFrames","skippedFrames","frameAgeMs","processingP95Ms","inferenceWaitMs","inferenceMs","recordingPending","recordingFailed","decodeErrors","decoderRelativeLagMs","liveResultDropped","analysisDroppedSamples")){
            var number=value.path(key);
            if(number.isNumber() && Double.isFinite(number.asDouble()) && number.asDouble()>=0 && number.asDouble()<=1e15)safe.put(key,number.numberValue());
        }
        for(String key:List.of("lastFrameAt","lastInferenceAt"))try{
            Instant stamp=OffsetDateTime.parse(value.path(key).asText()).toInstant();
            if(!stamp.isAfter(now.plusSeconds(5)))safe.put(key,stamp.toString());
        }catch(Exception ignored){}
        safe.put("sourceTimestampVerified",false);
        if(Set.of("DECODE_CHECKED","CORRUPT","UNAVAILABLE","UNVERIFIED").contains(value.path("sourceQuality").asText()))safe.put("sourceQuality",value.path("sourceQuality").asText());
        if(Set.of("READY","ACTIVE","ERROR","BUDGET_EXHAUSTED").contains(value.path("recordingState").asText()))safe.put("recordingState",value.path("recordingState").asText());
        if(Set.of("STARTING","RECORDING","STOPPED","ERROR","BUDGET_EXHAUSTED","NOT_CONFIGURED","DISABLED").contains(value.path("sourceRecordingState").asText()))safe.put("sourceRecordingState",value.path("sourceRecordingState").asText());
        if(Set.of("ACTIVE","ERROR").contains(value.path("liveResultState").asText()))safe.put("liveResultState",value.path("liveResultState").asText());
        if(Set.of("WAITING","RECORDING","ERROR","BUDGET_EXHAUSTED").contains(value.path("analysisRecordingState").asText()))safe.put("analysisRecordingState",value.path("analysisRecordingState").asText());
        try{jdbc.update("INSERT INTO monitoring_metric(camera_id,session_id,reported_at,metrics) VALUES(?,?,?,?) ON DUPLICATE KEY UPDATE session_id=VALUES(session_id),reported_at=VALUES(reported_at),metrics=VALUES(metrics)",camera,session,DetectionIngestService.utc(now),json.writeValueAsString(safe));}
        catch(java.io.IOException e){throw new IllegalStateException(e);}
    }
    private boolean fresh(Map<String,Object> metric,String key,Instant now){
        try{return Math.abs(Duration.between(Instant.parse((String)metric.get(key)),now).toMillis())<=35_000;}
        catch(Exception e){return false;}
    }
    public int healthyCount(){
        int count=0;Instant now=Instant.now();
        for(var row:jdbc.queryForList("SELECT m.metrics,m.reported_at FROM monitoring_metric m JOIN monitoring_task t ON t.camera_id=m.camera_id AND t.session_id=m.session_id WHERE t.enabled=TRUE AND t.state='RUNNING'")){
            var value=parsed((String)row.get("metrics"));
            if(Duration.between(instant(row.get("reported_at")),now).abs().getSeconds()<=35 && fresh(value,"lastFrameAt",now) && fresh(value,"lastInferenceAt",now))count++;
        }
        return count;
    }
    public void sample(long camera,String session,boolean enabled,String taskState){
        Instant now=Instant.now();String state="UNVERIFIED";
        var rows=jdbc.queryForList("SELECT metrics,reported_at FROM monitoring_metric WHERE camera_id=? AND session_id=?",camera,session);
        if(!enabled)state="DISABLED";
        else if(!rows.isEmpty() && Duration.between(instant(rows.get(0).get("reported_at")),now).abs().getSeconds()<=35){
            var metric=parsed((String)rows.get(0).get("metrics"));
            state=!metric.containsKey("lastInferenceAt") || !metric.containsKey("lastFrameAt")?"UNVERIFIED":fresh(metric,"lastInferenceAt",now) && fresh(metric,"lastFrameAt",now)?"HEALTHY":"UNAVAILABLE";
        }
        if(enabled && Set.of("FAILED","STOPPED","STOPPING").contains(taskState))state="UNAVAILABLE";
        var prior=jdbc.queryForList("SELECT state,observed_at FROM monitoring_health_sample WHERE camera_id=? ORDER BY id DESC LIMIT 1",camera);
        if(prior.isEmpty() || !state.equals(prior.get(0).get("state")) || Duration.between(instant(prior.get(0).get("observed_at")),now).getSeconds()>=30)
            jdbc.update("INSERT INTO monitoring_health_sample(camera_id,session_id,enabled,state,observed_at) VALUES(?,?,?,?,?)",camera,session,enabled,state,DetectionIngestService.utc(now));
        var fault=jdbc.queryForList("SELECT id FROM monitoring_fault WHERE camera_id=? AND recovered_at IS NULL",camera);
        var sessionRows=jdbc.queryForList("SELECT created_at FROM monitoring_session WHERE session_id=?",session);
        boolean overdue=!sessionRows.isEmpty() && Duration.between(instant(sessionRows.get(0).get("created_at")),now).getSeconds()>40;
        boolean bad=enabled && !state.equals("HEALTHY") && (overdue || taskState.equals("FAILED"));
        if(bad){
            String reason=taskState.equals("FAILED")?"WORKER_FAILED":"NO_RECENT_INFERENCE";
            if(fault.isEmpty()){
                jdbc.update("INSERT INTO monitoring_fault(camera_id,opened_at,last_seen,reason) VALUES(?,?,?,?)",camera,DetectionIngestService.utc(now),DetectionIngestService.utc(now),reason);
                notifications.fault(jdbc.queryForObject("SELECT id FROM monitoring_fault WHERE camera_id=? AND recovered_at IS NULL",Long.class,camera),camera,reason);
            }
            else jdbc.update("UPDATE monitoring_fault SET last_seen=?,reason=? WHERE id=?",DetectionIngestService.utc(now),reason,fault.get(0).get("id"));
        }else if(!fault.isEmpty() && (!enabled || state.equals("HEALTHY")))
            jdbc.update("UPDATE monitoring_fault SET recovered_at=?,closed_reason=? WHERE id=?",DetectionIngestService.utc(now),enabled?"INFERENCE_RECOVERED":"MONITORING_DISABLED",fault.get(0).get("id"));
    }
    public List<Map<String,Object>> decorate(List<Map<String,Object>> tasks){
        var metrics=new HashMap<Long,Map<String,Object>>();
        for(var row:jdbc.queryForList("SELECT * FROM monitoring_metric"))metrics.put(((Number)row.get("camera_id")).longValue(),row);
        for(var task:tasks){
            var metric=metrics.get(((Number)task.get("camera_id")).longValue());
            if(metric!=null && metric.get("session_id").equals(task.get("session_id"))){
                task.put("metrics",parsed((String)metric.get("metrics")));
                task.put("metricsReportedAt",com.example.detection.UtcValues.value(metric.get("reported_at")));
            }
        }
        return tasks;
    }
}
