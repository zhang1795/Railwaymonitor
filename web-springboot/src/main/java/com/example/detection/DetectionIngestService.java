package com.example.detection;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.sql.Statement;
import java.time.*;
import java.util.*;

@Service
@RequiredArgsConstructor
public class DetectionIngestService {
    private final JdbcTemplate jdbc;
    private final ObjectMapper mapper;
    private final TransactionTemplate tx;
    private final RiskIncidentService incidents;
    private final RiskPolicyService policies;
    public static final List<String> NAMES = List.of("Railway collision avoidance facilities","balloon","cow","flood",
        "huapo","illegal construction","kite","luoshi","nest","placard","pothole","trash","worker");
    public static final List<String> LABELS = List.of("防撞设备","气球","牛","水害","滑坡","违规建筑","风筝",
        "落石","鸟巢","广告牌","坑洞","垃圾","工人");
    private static final Instant MIN_TIME=Instant.parse("1000-01-01T00:00:00Z");
    private static final Instant MAX_TIME=Instant.parse("9999-12-31T23:59:59.999Z");

    public static String hash(String value) {
        try { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(value.getBytes(StandardCharsets.UTF_8))); }
        catch (Exception e) { throw new IllegalStateException(e); }
    }
    public static LocalDateTime utc(Instant value) { return LocalDateTime.ofInstant(value.truncatedTo(java.time.temporal.ChronoUnit.MILLIS), ZoneOffset.UTC); }
    private static String text(JsonNode n,String key,String pattern) {
        JsonNode v=n.get(key);
        if(v==null || !v.isTextual() || !v.textValue().matches(pattern)) throw new IllegalArgumentException("invalid "+key);
        return v.textValue();
    }
    private static long number(JsonNode n,String key,long min,long max) {
        JsonNode v=n.get(key);
        if(v==null || !v.isIntegralNumber() || !v.canConvertToLong() || v.longValue()<min || v.longValue()>max)
            throw new IllegalArgumentException("invalid "+key);
        return v.longValue();
    }
    private static double score(JsonNode v) {
        if(v==null || !v.isNumber() || !Double.isFinite(v.doubleValue()) || v.doubleValue()<0 || v.doubleValue()>1)
            throw new IllegalArgumentException("invalid confidence");
        return v.doubleValue();
    }
    private static Instant instant(JsonNode n,String key) {
        try {
            Instant value=OffsetDateTime.parse(n.path(key).textValue()).toInstant();
            if(value.isBefore(MIN_TIME) || value.isAfter(MAX_TIME))throw new IllegalArgumentException("outside supported range");
            return value;
        }
        catch(Exception e) { throw new IllegalArgumentException("invalid timezone timestamp: "+key); }
    }
    private static Instant storedInstant(Object value){
        LocalDateTime local=value instanceof java.sql.Timestamp timestamp ? timestamp.toLocalDateTime() : (LocalDateTime)value;
        return local.toInstant(ZoneOffset.UTC);
    }
    private void validate(JsonNode n,String worker) {
        if(!n.isObject() || number(n,"protocolVersion",3,4)<3 || !worker.equals(text(n,"workerId","[A-Za-z0-9_-]{1,64}")))
            throw new IllegalArgumentException("wrong protocol/worker");
        text(n,"eventId","[a-f0-9]{32}"); text(n,"sessionId","[a-f0-9]{32}");
        text(n,"cameraId","[1-9][0-9]{0,17}"); text(n,"trackId","[1-9][0-9]{0,17}");
        number(n,"generation",1,Long.MAX_VALUE); number(n,"sequence",1,Long.MAX_VALUE);
        int cls=(int)number(n,"classId",0,12);
        if(!NAMES.get(cls).equals(n.path("className").textValue())) throw new IllegalArgumentException("class ID/name mismatch");
        double confidence=score(n.get("confidence"));
        if(!Set.of("ACTIVE","MISSING","ENDED","INTERRUPTED").contains(n.path("state").asText()) || (n.path("protocolVersion").asInt()==3 && n.path("state").asText().equals("MISSING"))) throw new IllegalArgumentException("invalid state");
        if(!Set.of("received_at","media_time").contains(n.path("timeSource").asText())) throw new IllegalArgumentException("invalid time source");
        Instant first=instant(n,"firstSeen"),last=instant(n,"lastSeen"),processed=instant(n,"processedAt");
        if(first.isAfter(last) || last.isAfter(processed.plusSeconds(60)) || processed.isAfter(Instant.now().plusSeconds(60)))
            throw new IllegalArgumentException("invalid time order");
        if(n.path("protocolVersion").asInt()==4){
            Instant through=instant(n,"observedThrough");
            if(through.isBefore(last) || through.isAfter(processed.plusSeconds(60)))throw new IllegalArgumentException("invalid observation watermark");
            if(n.path("state").asText().equals("MISSING") || n.path("reason").asText().equals("confirmed_absence")){
                Instant missing=instant(n,"missingSince");
                if(missing.isBefore(last) || missing.isAfter(through))throw new IllegalArgumentException("invalid absence interval");
            }
        }
        int width=(int)number(n,"frameWidth",1,16384),height=(int)number(n,"frameHeight",1,16384);
        JsonNode box=n.path("bbox");
        if(!box.isArray() || box.size()!=4) throw new IllegalArgumentException("invalid bbox");
        for(JsonNode v:box) if(!v.isNumber() || !Double.isFinite(v.doubleValue())) throw new IllegalArgumentException("invalid bbox");
        if(box.get(0).asDouble()<0 || box.get(1).asDouble()<0 || box.get(2).asDouble()>width || box.get(3).asDouble()>height ||
           box.get(2).asDouble()<=box.get(0).asDouble() || box.get(3).asDouble()<=box.get(1).asDouble()) throw new IllegalArgumentException("bbox outside frame");
        JsonNode evidence=n.path("classEvidence");
        if(!evidence.isObject() || evidence.size()>13 || !evidence.has(String.valueOf(cls))) throw new IllegalArgumentException("invalid class evidence");
        evidence.fields().forEachRemaining(e->{
            if(!e.getKey().matches("[0-9]|1[0-2]")) throw new IllegalArgumentException("unknown evidence class");
            number(e.getValue(),"count",1,Long.MAX_VALUE); score(e.getValue().get("maxScore"));
        });
        if(score(evidence.get(String.valueOf(cls)).get("maxScore"))<confidence) throw new IllegalArgumentException("inconsistent class confidence");
    }
    private Map<String,Object> ack(String worker,String event,String hash,String status,String reason) {
        return Map.of("workerId",worker,"eventId",event,"payloadHash",hash,"status",status,"reason",reason==null?"":reason);
    }
    private Map<String,Object> reject(String worker,String event,String payload,String digest,String reason) {
        if(reason.length()>500)reason=reason.substring(0,500);
        final String rejectionReason=reason;
        tx.executeWithoutResult(s->{
            if(jdbc.queryForObject("SELECT COUNT(*) FROM detection_rejection WHERE payload_hash=?",Integer.class,digest)==0)
                jdbc.update("INSERT INTO detection_rejection VALUES(?,?,?,?,?,?)",digest,worker,event,rejectionReason,
                    payload.length()>16384?payload.substring(0,16384):payload,utc(Instant.now()));
        });
        return ack(worker,event,digest,"REJECTED",reason);
    }
    public Map<String,Object> receive(String worker,String payload) {
        String digest=hash(payload),id="";
        JsonNode event;
        try {
            if(payload.getBytes(StandardCharsets.UTF_8).length>16384) throw new IllegalArgumentException("payload exceeds 16 KiB");
            event=mapper.readTree(payload);
            id=text(event,"eventId","[a-f0-9]{32}");
            validate(event,worker);
        } catch(Exception e) {
            return reject(worker,id,payload,digest,"invalid event: "+e.getMessage());
        }
        final String eventId=id;
        return tx.execute(s->{
            // A per-session row serializes concurrent first snapshots, avoiding
            // check-then-insert races across event IDs of the same track.
            var sessions=jdbc.queryForList("SELECT * FROM monitoring_session WHERE session_id=? FOR UPDATE",event.path("sessionId").asText());
            if(sessions.isEmpty() || !worker.equals(sessions.get(0).get("worker_id")) ||
               ((Number)sessions.get(0).get("camera_id")).longValue()!=Long.parseLong(event.path("cameraId").asText()) ||
               ((Number)sessions.get(0).get("generation")).longValue()!=event.path("generation").asLong())
                return reject(worker,eventId,payload,digest,"unknown or mismatched monitoring session");
            if("received_at".equals(event.path("timeSource").asText())){
                var session=sessions.get(0);
                if(instant(event,"firstSeen").isBefore(storedInstant(session.get("created_at")).minusSeconds(60)) ||
                   (session.get("ended_at")!=null && instant(event,"lastSeen").isAfter(storedInstant(session.get("ended_at")).plusSeconds(60))))
                    return reject(worker,eventId,payload,digest,"observation outside monitoring session time window");
            }
            var receipts=jdbc.queryForList("SELECT * FROM detection_receipt WHERE worker_id=? AND event_id=?",worker,eventId);
            if(!receipts.isEmpty()) {
                var prior=receipts.get(0);
                if(!digest.equals(prior.get("payload_hash"))) return reject(worker,eventId,payload,digest,"event ID content conflict");
                return ack(worker,eventId,digest,(String)prior.get("status"),(String)prior.get("reason"));
            }
            String key=hash(worker+"\n"+event.path("cameraId").asText()+"\n"+event.path("sessionId").asText()+"\n"+event.path("trackId").asText());
            var tracks=jdbc.queryForList("SELECT * FROM risk_track WHERE source_key=?",key);
            if(!tracks.isEmpty()) {
                var prior=tracks.get(0);
                if(event.path("sequence").asLong()<((Number)prior.get("sequence_no")).longValue()) {
                    jdbc.update("INSERT INTO detection_receipt VALUES(?,?,?,?,?,?,?)",worker,eventId,digest,payload,"APPLIED","stale snapshot ignored",utc(Instant.now()));
                    return ack(worker,eventId,digest,"APPLIED","stale snapshot ignored");
                }
                if(event.path("sequence").asLong()==((Number)prior.get("sequence_no")).longValue())
                    return reject(worker,eventId,payload,digest,"track sequence reused by a different event");
                try {
                    JsonNode previous=mapper.readTree((String)prior.get("snapshot"));
                    if(!previous.path("firstSeen").equals(event.path("firstSeen")) || instant(event,"lastSeen").isBefore(instant(previous,"lastSeen")))
                        return reject(worker,eventId,payload,digest,"track timeline regressed");
                    var entries=previous.path("classEvidence").fields();
                    while(entries.hasNext()) {
                        var entry=entries.next();JsonNode next=event.path("classEvidence").path(entry.getKey());
                        if(next.path("count").asLong()<entry.getValue().path("count").asLong() ||
                           next.path("maxScore").asDouble()<entry.getValue().path("maxScore").asDouble())
                            return reject(worker,eventId,payload,digest,"cumulative evidence regressed");
                    }
                } catch(java.io.IOException e){throw new IllegalStateException("stored snapshot unreadable",e);}
                if(Set.of("ENDED","INTERRUPTED").contains(prior.get("state")) && Set.of("ACTIVE","MISSING").contains(event.path("state").asText()))
                    return reject(worker,eventId,payload,digest,"terminal track cannot reactivate");
            }
            var policy=policies.capture(event.path("sessionId").asText(),Long.parseLong(event.path("cameraId").asText()));
            if(event.path("protocolVersion").asInt()==4 && "confirmed_absence".equals(event.path("reason").asText()) &&
               Duration.between(instant(event,"missingSince"),instant(event,"observedThrough")).toMillis()<policy.graceSeconds()*1000L)
                return reject(worker,eventId,payload,digest,"absence interval shorter than configured grace");
            incidents.apply(worker,key,event,tracks.isEmpty()?null:tracks.get(0),sessions.get(0).get("ended_at")!=null);
            jdbc.update("INSERT INTO detection_receipt VALUES(?,?,?,?,?,?,?)",worker,eventId,digest,payload,"APPLIED","",utc(Instant.now()));
            return ack(worker,eventId,digest,"APPLIED","");
        });
    }
}
