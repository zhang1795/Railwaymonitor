package com.example.config;
import lombok.RequiredArgsConstructor;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

@Component @RequiredArgsConstructor
public class P0SchemaCheck implements ApplicationRunner {
    private final JdbcTemplate jdbc;
    @Override public void run(ApplicationArguments args){
        try{
            jdbc.queryForList("SELECT source_key,deleted FROM abnormal_event WHERE 1=0");
            jdbc.queryForList("SELECT deleted FROM camera WHERE 1=0");
            jdbc.queryForList("SELECT security_version FROM `user` WHERE 1=0");
            jdbc.queryForList("SELECT generation FROM monitoring_task WHERE 1=0");
            jdbc.queryForList("SELECT payload_hash FROM detection_receipt WHERE 1=0");
            jdbc.queryForList("SELECT token_hash FROM preview_grant WHERE 1=0");
        }catch(Exception e){throw new IllegalStateException("P0 schema missing. Back up and apply db/p0-migration.sql ONCE; never rerun completed ALTER statements.",e);}
        try{jdbc.queryForList("SELECT user_id,alarm_id FROM alarm_notice_read WHERE 1=0");}
        catch(Exception e){throw new IllegalStateException("Apply db/frontend-notices-migration.sql after backing up.",e);}
        try{
            for(String table:java.util.List.of("camera_risk_rule","risk_template_version","risk_template_default","camera_risk_revision","risk_track","session_risk_policy","alarm_source_link","alarm_transition","alarm_handling_audit","alarm_notice","alarm_notice_receipt","alarm_evidence","worker_evidence_status","evidence_storage_lock"))jdbc.queryForList("SELECT * FROM "+table+" WHERE 1=0");
            jdbc.queryForList("SELECT last_detection FROM risk_incident WHERE 1=0");
            jdbc.queryForList("SELECT version FROM alarm_edit_version WHERE 1=0");
            jdbc.queryForList("SELECT metrics FROM monitoring_metric WHERE 1=0");
            for(String table:java.util.List.of("monitoring_health_sample","monitoring_fault","monitoring_fault_receipt","recording_clip","notification_delivery"))jdbc.queryForList("SELECT * FROM "+table+" WHERE 1=0");
            jdbc.queryForList("SELECT sent_at FROM notification_delivery WHERE 1=0");
            jdbc.queryForList("SELECT manifest_json FROM recording_analysis WHERE 1=0");
            jdbc.queryForList("SELECT active_name FROM camera WHERE 1=0");
            Boolean unique=jdbc.execute((org.springframework.jdbc.core.ConnectionCallback<Boolean>)connection->{
                try(var indexes=connection.getMetaData().getIndexInfo(connection.getCatalog(),null,"camera",true,false)){
                    while(indexes.next())if("uq_camera_active_name".equalsIgnoreCase(indexes.getString("INDEX_NAME")))return true;
                }return false;
            });
            if(!Boolean.TRUE.equals(unique))throw new IllegalStateException("Camera uniqueness index missing; run deploy/apply_stability_indexes.py");
        }catch(Exception e){throw new IllegalStateException("Apply repeatable db/p1-alarm-migration.sql, db/p1-stability-migration.sql, db/p1-visualization-migration.sql and db/risk-template-migration.sql after backing up. Existing P0 ALTER migration must not be rerun.",e);}
    }
}
