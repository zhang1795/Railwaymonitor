package com.example.detection;

import com.fasterxml.jackson.databind.*;
import lombok.RequiredArgsConstructor;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.stereotype.Service;
import java.time.*;
import java.util.*;
import static com.example.detection.DetectionIngestService.*;

/** Invoked only inside ingestion's transaction and per-session row lock. */
@Service @RequiredArgsConstructor
public class RiskIncidentService {
    private final JdbcTemplate jdbc;private final ObjectMapper json;private final RiskPolicyService policies;private final NotificationOutbox notifications;
    private static LocalDateTime time(Object value){return value==null?null:value instanceof java.sql.Timestamp t?t.toLocalDateTime():(LocalDateTime)value;}
    private static Instant stamp(JsonNode e,String key){return OffsetDateTime.parse(e.path(key).asText()).toInstant();}
    private static boolean elapsed(LocalDateTime since,LocalDateTime now,int seconds){return since!=null && Duration.between(since,now).toMillis()>=seconds*1000L;}
    public Long apply(String worker,String key,JsonNode e,Map<String,Object> prior,boolean interrupted){
        long camera=Long.parseLong(e.path("cameraId").asText()),sequence=e.path("sequence").asLong();
        String session=e.path("sessionId").asText(),raw=e.path("state").asText();
        boolean v4=e.path("protocolVersion").asInt()>=4;
        var policy=policies.capture(session,camera);
        LocalDateTime seen=utc(stamp(e,"lastSeen")),observed=v4?utc(stamp(e,"observedThrough")):seen;
        Long alarm=prior==null || prior.get("alarm_id")==null?null:((Number)prior.get("alarm_id")).longValue();
        LocalDateTime qualifying=prior==null?null:time(prior.get("qualifying_since"));
        LocalDateTime outside=prior==null?null:time(prior.get("outside_since"));
        Map<String,Object> incident=alarm==null?null:incident(alarm);
        if(alarm!=null && incident==null){
            try{jdbc.update("INSERT INTO risk_incident VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",alarm,camera,session,"LEGACY","UNKNOWN",1,seen,seen,seen,null,json.writeValueAsString(policy.values()),"LEGACY_TRACK",e.path("classId").asInt(),e.path("bbox").toString(),e.path("frameWidth").asInt(),e.path("frameHeight").asInt(),seen);}
            catch(java.io.IOException ex){throw new IllegalStateException(ex);}
            jdbc.update("INSERT IGNORE INTO alarm_source_link VALUES(?,?,?,NULL)",alarm,key,sequence);
            incident=incident(alarm);
        }
        boolean validInside=raw.equals("ACTIVE") && (!policy.enabled() || policy.qualifies(e));
        if(validInside){
            // A gap, missing frame or class change interrupts the dwell proof.
            boolean continued=prior!=null && "ACTIVE".equals(prior.get("state"));
            if(continued){
                JsonNode old=read((String)prior.get("snapshot"));
                continued=(!policy.enabled() || policy.qualifies(old)) && old.path("classId").asInt()==e.path("classId").asInt()
                    && Duration.between(stamp(old,"lastSeen"),stamp(e,"lastSeen")).toMillis()<=policy.graceSeconds()*1000L;
            }
            if(!continued || qualifying==null)qualifying=seen;
            outside=null;
        }else{
            qualifying=null;
            if(outside==null)outside=observed;
        }
        boolean qualified=validInside && (!policy.enabled() || elapsed(qualifying,seen,policy.dwellSeconds()));
        boolean closed=incident!=null && Set.of("CLEARED","INTERRUPTED").contains(incident.get("state"));
        if(qualified && (alarm==null || closed)){
            if(alarm!=null)jdbc.update("UPDATE alarm_source_link SET last_sequence=? WHERE source_key=? AND last_sequence IS NULL",sequence-1,key);
            var candidates=candidates(camera,session,e,policy,seen);
            String association=candidates.size()==1?"RELINKED":candidates.size()>1?"AMBIGUOUS_NEW":"NEW";
            if(candidates.size()==1){alarm=((Number)candidates.get(0).get("alarm_id")).longValue();jdbc.update("UPDATE risk_incident SET association='RELINKED' WHERE alarm_id=?",alarm);}
            else alarm=create(worker,key,e,policy,seen,association);
            jdbc.update("INSERT INTO alarm_source_link VALUES(?,?,?,NULL)",alarm,key,sequence);
            incident=incident(alarm);
        }
        // A terminal/missing snapshot may arrive first. Preserve the confirmed
        // observation for review instead of inventing the lost dwell/ROI history.
        if(v4 && prior==null && alarm==null && !raw.equals("ACTIVE")){
            alarm=create(worker,key,e,RiskPolicy.observation(),seen,"LATE_SNAPSHOT_REVIEW");
            jdbc.update("INSERT INTO alarm_source_link VALUES(?,?,?,NULL)",alarm,key,1);incident=incident(alarm);
        }
        // Preserve legacy v3 behavior, including a terminal snapshot arriving first.
        if(!v4 && !policy.enabled() && alarm==null){
            alarm=create(worker,key,e,policy,seen,"LEGACY_TRACK");
            jdbc.update("INSERT INTO alarm_source_link VALUES(?,?,?,NULL)",alarm,key,sequence);incident=incident(alarm);
        }
        if(alarm!=null && incident!=null){
            String previous=(String)incident.get("state");
            String next=previous,reason="observation";
            if(interrupted || raw.equals("INTERRUPTED") || (raw.equals("ENDED") && !"confirmed_absence".equals(e.path("reason").asText()) && v4)){
                next="INTERRUPTED";reason="monitoring_interrupted";
            }else if(raw.equals("MISSING")){
                next="MISSING";reason="temporary_loss";
            }else if(raw.equals("ENDED")){
                next=v4?"CLEARED":"UNKNOWN";reason=v4?"confirmed_absence":"legacy_track_ended_unverified";
            }else if(qualified){next="PRESENT";reason="qualified_observation";}
            else if(policy.enabled() && raw.equals("ACTIVE")){
                next=elapsed(outside,observed,policy.graceSeconds())?"CLEARED":"MISSING";reason="outside_rule_region";
            }
            // Another linked, currently visible source keeps the incident present.
            if(Set.of("MISSING","CLEARED","INTERRUPTED").contains(next) && otherPresent(alarm,key,observed,policy)){
                next="PRESENT";reason="other_linked_source_present";
            }
            // A late snapshot must not reopen an ended incident without qualification.
            if(closed && !qualified)next=previous;
            LocalDateTime riskSince=time(incident.get("risk_since"));
            if(qualified && policy.enabled() && !"RISK".equals(incident.get("kind"))){
                riskSince=seen;
                try{jdbc.update("UPDATE risk_incident SET kind='RISK',risk_since=?,policy=? WHERE alarm_id=?",seen,json.writeValueAsString(policy.values()),alarm);}
                catch(java.io.IOException ex){throw new IllegalStateException(ex);}
            }
            int oldLevel=((Number)incident.get("risk_level")).intValue();
            boolean confirmedRisk=policy.enabled() && (qualified || "RISK".equals(incident.get("kind")));
            int newLevel=confirmedRisk?policy.level():1;
            if(confirmedRisk && policy.escalateSeconds()>0 && elapsed(riskSince,seen,policy.escalateSeconds()))newLevel=Math.min(5,newLevel+1);
            newLevel=Math.max(oldLevel,newLevel);
            String detected=next.equals("PRESENT")?"ACTIVE":next.equals("MISSING")?"MISSING":next.equals("CLEARED")?"ENDED":"INTERRUPTED";
            if(!v4)detected=interrupted && raw.equals("ACTIVE")?"INTERRUPTED":raw;
            String label=LABELS.get(e.path("classId").asInt());
            double maximum=e.path("classEvidence").path(e.path("classId").asText()).path("maxScore").asDouble();
            var oldAutomatic=jdbc.queryForMap("SELECT detected_type,confidence FROM abnormal_event WHERE id=?",alarm);
            if(label.equals(oldAutomatic.get("detected_type")) && oldAutomatic.get("confidence") instanceof Number n)maximum=Math.max(maximum,n.doubleValue());
            String description="待核验观察："+label+"；该类别最高置信度 "+String.format(Locale.ROOT,"%.1f%%",maximum*100);
            jdbc.update("UPDATE abnormal_event SET first_seen=CASE WHEN first_seen>? THEN ? ELSE first_seen END,last_seen=CASE WHEN last_seen<? THEN ? ELSE last_seen END,detection_state=?,update_time=? WHERE id=?",
                utc(stamp(e,"firstSeen")),utc(stamp(e,"firstSeen")),seen,seen,detected,utc(Instant.now()),alarm);
            if(!seen.isBefore(time(incident.get("last_detection")))){
                jdbc.update("UPDATE abnormal_event SET confidence=CASE WHEN detected_type=? THEN GREATEST(confidence,?) ELSE ? END,detected_type=?,type=CASE WHEN manual_override=FALSE THEN ? ELSE type END,description=CASE WHEN manual_override=FALSE THEN ? ELSE description END WHERE id=?",label,maximum,maximum,label,label,description,alarm);
                jdbc.update("UPDATE risk_incident SET last_detection=?,class_id=?,bbox=?,frame_width=?,frame_height=? WHERE alarm_id=?",seen,e.path("classId").asInt(),e.path("bbox").toString(),e.path("frameWidth").asInt(),e.path("frameHeight").asInt(),alarm);
            }
            jdbc.update("UPDATE risk_incident SET state=?,risk_level=?,last_inside=CASE WHEN ? AND (last_inside IS NULL OR last_inside<?) THEN ? ELSE last_inside END,last_observed=CASE WHEN last_observed<? THEN ? ELSE last_observed END,missing_since=? WHERE alarm_id=?",
                next,newLevel,qualified,seen,seen,observed,observed,next.equals("MISSING")?(outside==null?observed:outside):null,alarm);
            if(!previous.equals(next))transition(alarm,previous,next,reason,observed);
            // Reminders require a NEW, fresh, valid live observation, never a wall-clock timer.
            boolean fresh=Duration.between(stamp(e,"processedAt"),Instant.now()).abs().toSeconds()<=15
                && Duration.between(stamp(e,"lastSeen"),stamp(e,"processedAt")).abs().toSeconds()<=15;
            if(v4 && policy.enabled() && qualified && !interrupted && fresh && e.path("timeSource").asText().equals("received_at") && !isDeleted(alarm)){
                long bucket=Math.max(0,Duration.between(riskSince,seen).getSeconds()/policy.reminderSeconds());
                if(newLevel>oldLevel)notice(alarm,"ESCALATION",newLevel,observed);
                else if(bucket>0)notice(alarm,"ONGOING",bucket,observed);
            }
        }
        if(prior==null)jdbc.update("INSERT INTO risk_track VALUES(?,?,?,?,?,?,?,?)",key,session,sequence,raw,e.toString(),alarm,qualifying,outside);
        else jdbc.update("UPDATE risk_track SET sequence_no=?,state=?,snapshot=?,alarm_id=?,qualifying_since=?,outside_since=? WHERE source_key=?",sequence,raw,e.toString(),alarm,qualifying,outside,key);
        if(alarm!=null){
            if(jdbc.queryForObject("SELECT COUNT(*) FROM detection_track WHERE source_key=?",Integer.class,key)==0)jdbc.update("INSERT INTO detection_track VALUES(?,?,?,?,?,?)",key,session,sequence,raw,e.toString(),alarm);
            else jdbc.update("UPDATE detection_track SET sequence_no=?,state=?,snapshot=?,alarm_id=? WHERE source_key=?",sequence,raw,e.toString(),alarm,key);
        }
        return alarm;
    }
    private Map<String,Object> incident(long id){var rows=jdbc.queryForList("SELECT * FROM risk_incident WHERE alarm_id=? FOR UPDATE",id);return rows.isEmpty()?null:rows.get(0);}
    private boolean isDeleted(long alarm){return jdbc.queryForObject("SELECT deleted FROM abnormal_event WHERE id=?",Integer.class,alarm)!=0;}
    private JsonNode read(String payload){try{return json.readTree(payload);}catch(Exception e){throw new IllegalStateException("Stored track unreadable",e);}}
    private List<Map<String,Object>> candidates(long camera,String session,JsonNode e,RiskPolicy p,LocalDateTime seen){
        var result=new ArrayList<Map<String,Object>>();
        for(var row:jdbc.queryForList("SELECT i.* FROM risk_incident i JOIN abnormal_event a ON a.id=i.alarm_id WHERE i.camera_id=? AND i.session_id=? AND i.state='MISSING' AND i.class_id=? AND a.deleted=0 FOR UPDATE",camera,session,e.path("classId").asInt())){
            boolean visible=false;
            for(var source:jdbc.queryForList("SELECT snapshot FROM risk_track WHERE alarm_id=? AND state='ACTIVE'",row.get("alarm_id"))){
                if(Math.abs(Duration.between(stamp(read((String)source.get("snapshot")),"lastSeen"),seen.toInstant(ZoneOffset.UTC)).toMillis())<=p.graceSeconds()*1000L){visible=true;break;}
            }
            if(visible)continue; // A still-visible object is positive evidence against merging another target.
            LocalDateTime last=time(row.get("last_inside"));
            if(last==null || seen.isBefore(last) || Duration.between(last,seen).toMillis()>p.graceSeconds()*1000L)continue;
            if(iou(read((String)row.get("bbox")),((Number)row.get("frame_width")).doubleValue(),((Number)row.get("frame_height")).doubleValue(),e)>=.3)result.add(row);
        }
        return result;
    }
    private static double iou(JsonNode old,double width,double height,JsonNode e){
        var b=e.path("bbox");double[] a={old.get(0).asDouble()/width,old.get(1).asDouble()/height,old.get(2).asDouble()/width,old.get(3).asDouble()/height};
        double w=e.path("frameWidth").asDouble(),h=e.path("frameHeight").asDouble();double[] c={b.get(0).asDouble()/w,b.get(1).asDouble()/h,b.get(2).asDouble()/w,b.get(3).asDouble()/h};
        double intersection=Math.max(0,Math.min(a[2],c[2])-Math.max(a[0],c[0]))*Math.max(0,Math.min(a[3],c[3])-Math.max(a[1],c[1]));
        double union=(a[2]-a[0])*(a[3]-a[1])+(c[2]-c[0])*(c[3]-c[1])-intersection;return union>0?intersection/union:0;
    }
    private boolean otherPresent(long alarm,String source,LocalDateTime seen,RiskPolicy p){
        for(var row:jdbc.queryForList("SELECT snapshot FROM risk_track WHERE alarm_id=? AND source_key<>? AND state='ACTIVE'",alarm,source)){
            var event=read((String)row.get("snapshot"));
            if(!p.enabled() || p.qualifies(event)){
                var last=utc(stamp(event,"lastSeen"));if(Math.abs(Duration.between(last,seen).toMillis())<=p.graceSeconds()*1000L)return true;
            }
        }return false;
    }
    private long create(String worker,String source,JsonNode e,RiskPolicy p,LocalDateTime at,String association){
        String key=source;
        if(jdbc.queryForObject("SELECT COUNT(*) FROM abnormal_event WHERE source_key=?",Integer.class,key)>0)key=hash(source+"\n"+e.path("sequence").asLong());
        String identity=key,label=LABELS.get(e.path("classId").asInt());
        double score=e.path("classEvidence").path(e.path("classId").asText()).path("maxScore").asDouble();
        var holder=new GeneratedKeyHolder();
        jdbc.update(c->{var statement=c.prepareStatement("INSERT INTO abnormal_event(camera_id,event_time,location,level,type,status,description,source_key,first_seen,last_seen,detection_state,detected_type,confidence,create_time,update_time) VALUES(?,?,(SELECT location FROM camera WHERE id=?),?,?,0,?,?,?,?,?,?,?,?,?)",new String[]{"id"});
            Object[] values={Long.parseLong(e.path("cameraId").asText()),LocalDateTime.ofInstant(stamp(e,"firstSeen"),ZoneId.of("Asia/Shanghai")),Long.parseLong(e.path("cameraId").asText()),p.enabled()?p.level():1,label,"待核验观察："+label,identity,utc(stamp(e,"firstSeen")),at,"ACTIVE",label,score,utc(Instant.now()),utc(Instant.now())};
            for(int index=0;index<values.length;index++)statement.setObject(index+1,values[index]);return statement;},holder);
        long id=Objects.requireNonNull(holder.getKey()).longValue();
        try{jdbc.update("INSERT INTO risk_incident VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",id,Long.parseLong(e.path("cameraId").asText()),e.path("sessionId").asText(),p.enabled()?"RISK":"OBSERVATION","PRESENT",p.enabled()?p.level():1,at,at,at,null,json.writeValueAsString(p.values()),association,e.path("classId").asInt(),e.path("bbox").toString(),e.path("frameWidth").asInt(),e.path("frameHeight").asInt(),at);}
        catch(java.io.IOException ex){throw new IllegalStateException(ex);}
        transition(id,null,"PRESENT","first_observation",at);notice(id,"FIRST",0,at);return id;
    }
    private void transition(long alarm,String from,String to,String reason,LocalDateTime at){jdbc.update("INSERT INTO alarm_transition(alarm_id,from_state,to_state,reason,observed_at) VALUES(?,?,?,?,?)",alarm,from,to,reason,at);}
    private void notice(long alarm,String kind,long bucket,LocalDateTime at){
        if(jdbc.update("INSERT IGNORE INTO alarm_notice(alarm_id,kind,bucket,created_at) VALUES(?,?,?,?)",alarm,kind,bucket,at)>0)
            notifications.notice(jdbc.queryForObject("SELECT id FROM alarm_notice WHERE alarm_id=? AND kind=? AND bucket=?",Long.class,alarm,kind,bucket),alarm);
    }
}
