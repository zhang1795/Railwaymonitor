package com.example.detection;

import com.example.common.exception.BusinessException;
import lombok.RequiredArgsConstructor;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;
import java.time.*;
import java.util.*;
import static com.example.detection.DetectionIngestService.utc;

@Service
@RequiredArgsConstructor
public class MonitoringService {
    private final JdbcTemplate jdbc;
    private final TransactionTemplate tx;
    private final SourcePolicy sources;
    private final RiskPolicyService riskPolicies;
    private final MonitoringHealthService health;
    @Value("${railway.worker-id:detector-1}") private String workerId;
    @Value("${railway.max-tasks:9}") private int capacity;

    private static boolean enabled(Object value) {
        return Boolean.TRUE.equals(value) || value instanceof Number && ((Number)value).intValue()!=0;
    }
    private String uuid() { return UUID.randomUUID().toString().replace("-",""); }
    private static Instant instant(Object value) {
        if(value instanceof java.sql.Timestamp time)return time.toLocalDateTime().toInstant(ZoneOffset.UTC);
        return ((LocalDateTime)value).toInstant(ZoneOffset.UTC);
    }
    public List<Map<String,Object>> list() {
        return health.decorate(jdbc.queryForList("SELECT camera_id,worker_id,enabled,generation,session_id,state,error,last_status_at,pending_events FROM monitoring_task ORDER BY camera_id"));
    }
    public Map<String,Object> setEnabled(long camera,boolean on) {
        return tx.execute(s->{
            // Serialize capacity checks and enable/disable transitions on this
            // single assigned worker, including different cameras.
            jdbc.queryForList("SELECT id FROM camera ORDER BY id FOR UPDATE");
            var cams=jdbc.queryForList("SELECT * FROM camera WHERE id=? AND deleted=0",camera);
            if(cams.isEmpty()) throw new BusinessException(404,"摄像头不存在");
            if(on) sources.validate((String)cams.get(0).get("rtsp_url"));
            var rows=jdbc.queryForList("SELECT * FROM monitoring_task WHERE camera_id=?",camera);
            boolean wasOn=!rows.isEmpty() && enabled(rows.get(0).get("enabled"));
            if(on && !wasOn && jdbc.queryForObject("SELECT COUNT(*) FROM monitoring_task WHERE enabled=TRUE",Integer.class)>=capacity)
                throw new BusinessException(409,"检测任务数量达到配置上限");
            if(rows.isEmpty()) {
                String session=uuid();
                jdbc.update("INSERT INTO monitoring_task(camera_id,worker_id,enabled,generation,session_id,state,updated_at) VALUES(?,?,?,?,?,?,?)",camera,workerId,on,1,session,on?"STARTING":"STOPPED",utc(Instant.now()));
                jdbc.update("INSERT INTO monitoring_session(session_id,camera_id,worker_id,generation,created_at) VALUES(?,?,?,?,?)",session,camera,workerId,1,utc(Instant.now()));
                riskPolicies.capture(session,camera);
            } else if(wasOn!=on) {
                var row=rows.get(0); endSession((String)row.get("session_id"),on?"reconfigured":"disabled");
                long generation=((Number)row.get("generation")).longValue()+1;
                String session=on?uuid():(String)row.get("session_id");
                jdbc.update("UPDATE monitoring_task SET enabled=?,generation=?,session_id=?,state=?,revision=-1,error='',retry_count=0,next_retry_at=NULL,updated_at=? WHERE camera_id=?",on,generation,session,on?"STARTING":"STOPPING",utc(Instant.now()),camera);
                if(on){jdbc.update("INSERT INTO monitoring_session(session_id,camera_id,worker_id,generation,created_at) VALUES(?,?,?,?,?)",session,camera,workerId,generation,utc(Instant.now()));riskPolicies.capture(session,camera);}
            }
            return jdbc.queryForMap("SELECT * FROM monitoring_task WHERE camera_id=?",camera);
        });
    }
    private void endSession(String session,String reason) {
        jdbc.update("INSERT INTO alarm_transition(alarm_id,from_state,to_state,reason,observed_at) SELECT alarm_id,state,'INTERRUPTED',?,? FROM risk_incident WHERE session_id=? AND state IN ('PRESENT','MISSING')",reason,utc(Instant.now()),session);
        jdbc.update("UPDATE risk_incident SET state='INTERRUPTED' WHERE session_id=? AND state IN ('PRESENT','MISSING')",session);
        jdbc.update("UPDATE abnormal_event SET detection_state='INTERRUPTED' WHERE id IN (SELECT alarm_id FROM risk_incident WHERE session_id=? AND state='INTERRUPTED')",session);
        jdbc.update("UPDATE monitoring_session SET ended_at=COALESCE(ended_at,?),end_reason=COALESCE(end_reason,?) WHERE session_id=?",utc(Instant.now()),reason,session);
        jdbc.update("UPDATE abnormal_event SET detection_state='INTERRUPTED' WHERE detection_state IN ('ACTIVE','MISSING') AND source_key IN (SELECT source_key FROM detection_track WHERE session_id=?)",session);
    }
    public List<Map<String,Object>> commands() {
        return tx.execute(s->{
            var result=new ArrayList<Map<String,Object>>();
            var rows=jdbc.queryForList("SELECT * FROM monitoring_task ORDER BY camera_id FOR UPDATE");
            Instant now=Instant.now();
            for(var row:rows) {
                boolean on=enabled(row.get("enabled"));
                long camera=((Number)row.get("camera_id")).longValue();
                var cams=jdbc.queryForList("SELECT rtsp_url FROM camera WHERE id=? AND deleted=0",camera);
                if(cams.isEmpty()) { jdbc.update("UPDATE monitoring_task SET enabled=FALSE,error='camera deleted' WHERE camera_id=?",camera); on=false; }
                String state=(String)row.get("state"),session=(String)row.get("session_id");
                health.sample(camera,session,on,state);
                long generation=((Number)row.get("generation")).longValue();
                // A missing/terminal worker is restarted from durable intent,
                // never from a browser heartbeat. Backoff prevents hot loops.
                boolean expired=Duration.between(instant(row.get("updated_at")),now).getSeconds()>40;
                if(on && (Set.of("FAILED","STOPPED").contains(state) || expired)) {
                    Object retry=row.get("next_retry_at");
                    if(retry!=null && instant(retry).isAfter(now)) continue;
                    endSession(session,"worker_interrupted");
                    generation++;session=uuid();
                    int attempt=((Number)row.get("retry_count")).intValue()+1;
                    jdbc.update("UPDATE monitoring_task SET generation=?,session_id=?,state='STARTING',revision=-1,updated_at=?,retry_count=?,next_retry_at=? WHERE camera_id=?",generation,session,utc(now),attempt,utc(now.plusSeconds(Math.min(30,1L<<Math.min(attempt,5)))),camera);
                    jdbc.update("INSERT INTO monitoring_session(session_id,camera_id,worker_id,generation,created_at) VALUES(?,?,?,?,?)",session,camera,row.get("worker_id"),generation,utc(now));
                    riskPolicies.capture(session,camera);
                }
                String url="";
                try { if(on)url=sources.validate((String)cams.get(0).get("rtsp_url")); }
                catch(BusinessException e) {jdbc.update("UPDATE monitoring_task SET error=?,state='FAILED' WHERE camera_id=?",e.getMessage(),camera);continue;}
                var command=new LinkedHashMap<String,Object>();
                command.put("protocolVersion",3);command.put("workerId",row.get("worker_id"));
                command.put("cameraId",String.valueOf(camera));command.put("generation",generation);
                command.put("sessionId",session);command.put("enabled",on);command.put("videoUrl",url);
                command.put("trackGraceSeconds",riskPolicies.capture(session,camera).graceSeconds());
                command.put("commandId",uuid());command.put("expiresAt",now.plusSeconds(20).truncatedTo(java.time.temporal.ChronoUnit.MILLIS).toString());result.add(command);
            }
            return result;
        });
    }
    public void status(String worker,com.fasterxml.jackson.databind.JsonNode value) {
        String session=value.path("sessionId").asText(),state=value.path("state").asText();
        if(!Set.of("STARTING","RUNNING","STOPPING","STOPPED","FAILED").contains(state))return;
        if(!value.path("revision").isIntegralNumber())return;
        tx.executeWithoutResult(s->{
            var rows=jdbc.queryForList("SELECT * FROM monitoring_task WHERE worker_id=? AND session_id=? FOR UPDATE",worker,session);
            if(rows.isEmpty())return;
            if(value.has("evidencePending") && value.path("evidencePending").canConvertToLong()){
                jdbc.update("INSERT INTO worker_evidence_status(worker_id,pending_events,skipped,error,reported_at) VALUES(?,?,?,?,?) ON DUPLICATE KEY UPDATE pending_events=VALUES(pending_events),skipped=VALUES(skipped),error=VALUES(error),reported_at=VALUES(reported_at)",worker,Math.max(0,value.path("evidencePending").asLong()),Math.max(0,value.path("evidenceSkipped").asLong()),value.path("evidenceError").asText("").substring(0,Math.min(200,value.path("evidenceError").asText("").length())),utc(Instant.now()));
            }
            var row=rows.get(0);
            long revision=value.path("revision").asLong();
            boolean lostSession="FAILED".equals(state) && value.path("lostSession").isBoolean() && value.path("lostSession").asBoolean();
            if(!lostSession && revision<((Number)row.get("revision")).longValue())return;
            if(!enabled(row.get("enabled")) && Set.of("STARTING","RUNNING").contains(state))return;
            health.metric(((Number)row.get("camera_id")).longValue(),session,value.path("metrics"));
            health.sample(((Number)row.get("camera_id")).longValue(),session,enabled(row.get("enabled")),state);
            String error=value.path("error").asText("");if(error.length()>500)error=error.substring(0,500);
            jdbc.update("UPDATE monitoring_task SET state=?,revision=?,error=?,last_status_at=?,updated_at=?,pending_events=? WHERE camera_id=?",state,revision,error,utc(Instant.now()),utc(Instant.now()),Math.max(0,value.path("pendingEvents").asLong()),row.get("camera_id"));
            if(Set.of("FAILED","STOPPED").contains(state))endSession(session,"worker_"+state.toLowerCase(Locale.ROOT));
        });
    }
}
