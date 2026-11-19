package com.example.detection;

import jakarta.annotation.PreDestroy;
import lombok.RequiredArgsConstructor;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;

/** Persist lost-inference faults even while the MQTT reconnect call is blocked. */
@Service @RequiredArgsConstructor
public class MonitoringHealthSampler {
    private final JdbcTemplate jdbc;private final MonitoringHealthService health;private final TransactionTemplate tx;
    @Value("${railway.health-sampling:true}") private boolean enabled;
    private final AtomicBoolean running=new AtomicBoolean();
    private final ExecutorService executor=Executors.newSingleThreadExecutor(r->{var thread=new Thread(r,"detection-health-samples");thread.setDaemon(true);return thread;});
    public void sampleOnce(){tx.executeWithoutResult(status->{
        for(var row:jdbc.queryForList("SELECT camera_id,session_id,enabled,state FROM monitoring_task ORDER BY camera_id FOR UPDATE"))
            health.sample(((Number)row.get("camera_id")).longValue(),(String)row.get("session_id"),Boolean.TRUE.equals(row.get("enabled")) || row.get("enabled") instanceof Number number && number.intValue()!=0,(String)row.get("state"));
    });}
    @Scheduled(fixedDelay=5000) public void schedule(){
        if(!enabled || !running.compareAndSet(false,true))return;
        executor.execute(()->{try{sampleOnce();}catch(org.springframework.dao.DataAccessException | org.springframework.transaction.TransactionException ignored){}finally{running.set(false);}});
    }
    @PreDestroy public void close(){executor.shutdownNow();}
}
