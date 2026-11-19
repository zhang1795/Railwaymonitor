package com.example.detection;

import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.annotation.PreDestroy;
import lombok.RequiredArgsConstructor;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.*;
import org.springframework.transaction.support.TransactionTemplate;
import java.time.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;

/** Jobs are committed with notices. Provider IO is always outside that transaction. */
@Service @RequiredArgsConstructor
public class NotificationOutbox {
    private final JdbcTemplate jdbc;private final ObjectMapper json;private final NotificationTransport transport;private final TransactionTemplate tx;
    @Value("${railway.notify.scheduled:true}") private boolean scheduled;
    @Value("${railway.notify.sms-min-level:3}") private int minLevel;
    private final ExecutorService sender=Executors.newSingleThreadExecutor(r->{var thread=new Thread(r,"notification-delivery");thread.setDaemon(true);return thread;});
    private final AtomicBoolean running=new AtomicBoolean();
    private volatile String dispatcherError="";
    private static LocalDateTime utc(){return DetectionIngestService.utc(Instant.now());}
    private static Instant instant(Object value){return (value instanceof java.sql.Timestamp t?t.toLocalDateTime():(LocalDateTime)value).toInstant(ZoneOffset.UTC);}
    @Transactional(propagation=Propagation.MANDATORY)
    public void notice(long notice,long alarm){
        if(!transport.webhookConfigured() && !transport.smsConfigured())return;
        var rows=jdbc.queryForList("SELECT n.kind,a.camera_id,a.detected_type,i.risk_level,n.created_at FROM alarm_notice n JOIN abnormal_event a ON a.id=n.alarm_id JOIN risk_incident i ON i.alarm_id=a.id WHERE n.id=? AND a.id=? AND a.deleted=0 AND i.kind='RISK'",notice,alarm);
        if(rows.isEmpty())return;var row=rows.get(0);
        enqueue("NOTICE",notice,alarm,((Number)row.get("camera_id")).longValue(),(String)row.get("kind"),((Number)row.get("risk_level")).intValue(),String.valueOf(row.get("detected_type")),instant(row.get("created_at")));
    }
    @Transactional(propagation=Propagation.MANDATORY)
    public void fault(long fault,long camera,String reason){enqueue("FAULT",fault,0,camera,"FIRST",3,reason.equals("WORKER_FAILED")?"检测任务失败":"近期有效推理中断",Instant.now());}
    private void enqueue(String entity,long id,long alarm,long camera,String kind,int level,String type,Instant time){
        var payload=new LinkedHashMap<String,Object>();payload.put("entityType",entity);payload.put("entityId",id);payload.put("alarmId",alarm);payload.put("cameraId",camera);payload.put("kind",kind);payload.put("level",level);payload.put("type",type);payload.put("time",time.atZone(ZoneId.of("Asia/Shanghai")).format(java.time.format.DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm")));
        if(transport.webhookConfigured())insert(entity,id,"WEBHOOK","webhook",payload);
        if(transport.smsConfigured() && level>=minLevel && !kind.equals("ONGOING"))for(String phone:transport.phones())insert(entity,id,"SMS",phone,payload);
    }
    private void insert(String entity,long id,String channel,String target,Map<String,Object> payload){
        try{jdbc.update("INSERT IGNORE INTO notification_delivery(id,entity_type,entity_id,channel,target,payload,status,next_at,created_at,updated_at) VALUES(?,?,?,?,?,?,'PENDING',?,?,?)",UUID.randomUUID().toString().replace("-",""),entity,id,channel,target,json.writeValueAsString(payload),utc(),utc(),utc());}
        catch(java.io.IOException e){throw new IllegalStateException(e);}
    }
    private Map<String,Object> claim(){
        return tx.execute(status->{
            var rows=jdbc.queryForList("SELECT * FROM notification_delivery WHERE ((status IN ('PENDING','RETRY','ACCEPTED') AND next_at<=?) OR (status='SENDING' AND lease_until<?)) ORDER BY created_at,id LIMIT 1 FOR UPDATE",utc(),utc());
            if(rows.isEmpty())return null;var row=rows.get(0);String id=(String)row.get("id");
            boolean sms=row.get("channel").equals("SMS"),poll=row.get("status").equals("ACCEPTED") || row.get("status").equals("SENDING") && row.get("phase").equals("POLL");
            if(row.get("status").equals("SENDING") && sms && !poll){jdbc.update("UPDATE notification_delivery SET status='UNKNOWN',error='process_stopped_with_send_result_unconfirmed',updated_at=? WHERE id=?",utc(),id);return null;}
            if(poll && Duration.between(instant(row.get("sent_at")==null?row.get("created_at"):row.get("sent_at")),Instant.now()).toHours()>=24){jdbc.update("UPDATE notification_delivery SET status='RECEIPT_TIMEOUT',updated_at=? WHERE id=?",utc(),id);return null;}
            int attempts=((Number)row.get("attempts")).intValue();
            if(!poll && attempts>=5){jdbc.update("UPDATE notification_delivery SET status='FAILED',error='retry_limit_reached',updated_at=? WHERE id=?",utc(),id);return null;}
            String token=UUID.randomUUID().toString().replace("-","");String phase=poll?"POLL":"SEND";
            jdbc.update("UPDATE notification_delivery SET status='SENDING',phase=?,attempts=attempts+?,lease_token=?,lease_until=?,sent_at=COALESCE(?,sent_at),updated_at=? WHERE id=?",phase,poll?0:1,token,DetectionIngestService.utc(Instant.now().plusSeconds(60)),poll?null:utc(),utc(),id);
            row.put("phase",phase);row.put("lease_token",token);row.put("attempts",attempts+(poll?0:1));return row;
        });
    }
    public boolean dispatchOnce(){
        var delivery=claim();if(delivery==null)return false;
        var result=transport.deliver(delivery);
        int attempts=((Number)delivery.get("attempts")).intValue();
        Instant next=Instant.now().plusSeconds(result.status().equals("ACCEPTED")?60:Math.min(900,30L<<Math.min(attempts,5)));
        tx.executeWithoutResult(status->jdbc.update("UPDATE notification_delivery SET status=?,provider_id=?,error=?,next_at=?,lease_token=NULL,lease_until=NULL,updated_at=? WHERE id=? AND lease_token=?",result.status(),result.providerId(),result.error(),DetectionIngestService.utc(next),utc(),delivery.get("id"),delivery.get("lease_token")));
        return true;
    }
    @Scheduled(fixedDelayString="${railway.notify.schedule-ms:1000}") public void schedule(){
        if(!scheduled || !running.compareAndSet(false,true))return;
        sender.execute(()->{try{for(int i=0;i<10;i++)if(!dispatchOnce())break;dispatcherError="";}catch(Exception error){dispatcherError=error.getClass().getSimpleName();}finally{running.set(false);}});
    }
    @PreDestroy public void close(){sender.shutdownNow();}
    public Map<String,Object> state(){return Map.of("webhookConfigured",transport.webhookConfigured(),"smsConfigured",transport.smsConfigured(),"smsMinLevel",minLevel,"inAppEnabled",true,"dispatcherError",dispatcherError);}
    public List<Map<String,Object>> forAlarm(long alarm){
        var rows=jdbc.queryForList("SELECT id,channel,status,attempts,error,created_at,updated_at FROM notification_delivery WHERE entity_type='NOTICE' AND entity_id IN (SELECT id FROM alarm_notice WHERE alarm_id=?) ORDER BY created_at DESC LIMIT 100",alarm);
        for(var row:rows)UtcValues.map(row);return rows;
    }
}
