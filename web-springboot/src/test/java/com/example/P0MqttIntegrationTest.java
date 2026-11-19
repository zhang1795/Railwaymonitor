package com.example;

import com.example.detection.MonitoringService;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import java.nio.file.*;
import java.time.*;
import java.util.function.BooleanSupplier;
import static org.junit.jupiter.api.Assertions.*;

@EnabledIfEnvironmentVariable(named="P0_MQTT_URI",matches=".+")
@ActiveProfiles("test")
@SpringBootTest(properties={"spring.datasource.url=jdbc:h2:mem:p0mqtt;MODE=MySQL;DATABASE_TO_LOWER=TRUE;NON_KEYWORDS=USER;DB_CLOSE_DELAY=-1",
    "railway.mqtt.enabled=true","railway.mqtt.uri=${P0_MQTT_URI}","railway.mqtt.username=${MQTT_BACKEND_USERNAME}",
    "railway.mqtt.password=${MQTT_BACKEND_PASSWORD}","railway.mqtt.ca-file=${MQTT_CA_FILE}",
    "railway.mqtt.persistence=${P0_MQTT_PERSISTENCE}","railway.reconcile-ms=1000"})
class P0MqttIntegrationTest {
    @Autowired JdbcTemplate jdbc;
    @Autowired MonitoringService monitoring;
    @Autowired ObjectMapper json;
    private void await(BooleanSupplier condition,int seconds)throws Exception{
        Instant deadline=Instant.now().plusSeconds(seconds);
        while(Instant.now().isBefore(deadline)){if(condition.getAsBoolean())return;Thread.sleep(100);}
        assertTrue(condition.getAsBoolean(),"integration condition timed out");
    }
    @Test void zeroBrowsersTlsOutboxBrokerRestartAndBackgroundStop()throws Exception{
        jdbc.update("INSERT INTO camera(id,name,location,rtsp_url,status) VALUES(1,'synthetic','integration','rtsp://127.0.0.1:8554/synthetic',1)");
        Path root=Path.of("..").toAbsolutePath().normalize();
        Path folder=Files.createTempDirectory("railway-p0-driver-");
        Files.writeString(folder.resolve("drop-acks"),"test-only: ignore committed business ACKs");
        var builder=new ProcessBuilder(root.resolve("workspace/runtime/detector-env/bin/python").toString(),
            root.resolve("RailwayDetector/tests/mqtt_integration_driver.py").toString(),folder.toString());
        builder.environment().put("PYTHONDONTWRITEBYTECODE","1");
        builder.redirectErrorStream(true).redirectOutput(folder.resolve("driver.log").toFile());
        Process driver=builder.start();
        try {
            monitoring.setEnabled(1,true);
            await(()->jdbc.queryForObject("SELECT COUNT(*) FROM abnormal_event",Integer.class)==1,15);
            Instant firstVisible=Instant.now();
            String firstPayload=jdbc.queryForObject("SELECT payload FROM detection_receipt ORDER BY received_at LIMIT 1",String.class);
            long firstLatency=Duration.between(Instant.parse(json.readTree(firstPayload).path("processedAt").asText()),firstVisible).toMillis();
            assertTrue(firstLatency>=0 && firstLatency<=1000,"first persisted event exceeds 1s target: "+firstLatency);
            await(()->pending(folder)>0 && attempts(folder)>=2,10);
            assertEquals(1,jdbc.queryForObject("SELECT COUNT(*) FROM abnormal_event",Integer.class));
            Files.delete(folder.resolve("drop-acks"));
            await(()->pending(folder)==0,15);
            await(()->jdbc.queryForObject("SELECT COUNT(*) FROM abnormal_event WHERE type='牛'",Integer.class)==1,15);
            assertEquals(1,jdbc.queryForObject("SELECT COUNT(*) FROM abnormal_event",Integer.class));
            if("true".equals(System.getenv("P0_MANAGE_TEST_BROKER"))){
                assertEquals(0,new ProcessBuilder("docker","stop","--time","1","railway-p0-test").redirectOutput(folder.resolve("stop.log").toFile()).start().waitFor());
                await(()->pending(folder)>0,8);
                assertEquals(0,new ProcessBuilder("docker","start","railway-p0-test").redirectOutput(folder.resolve("start.log").toFile()).start().waitFor());
                await(()->pending(folder)==0,25);
                assertEquals(1,jdbc.queryForObject("SELECT COUNT(*) FROM abnormal_event",Integer.class));
                Instant recovered=Instant.now();
                await(()->controlAfter(folder,recovered),8);
                assertEquals(0,new ProcessBuilder("docker","kill","railway-p0-test").redirectOutput(folder.resolve("kill.log").toFile()).start().waitFor());
                await(()->pending(folder)>0,8);
                assertEquals(0,new ProcessBuilder("docker","start","railway-p0-test").redirectOutput(folder.resolve("restart-after-kill.log").toFile()).start().waitFor());
                await(()->pending(folder)==0,25);
                assertEquals(1,jdbc.queryForObject("SELECT COUNT(*) FROM abnormal_event",Integer.class));
            }
            String oldSession=(String)monitoring.list().get(0).get("session_id");
            driver.destroyForcibly();driver.waitFor();
            driver=builder.start();
            await(()->jdbc.queryForObject("SELECT COUNT(*) FROM abnormal_event",Integer.class)==2,12);
            assertNotEquals(oldSession,monitoring.list().get(0).get("session_id"));
            assertEquals(1,jdbc.queryForObject("SELECT COUNT(*) FROM abnormal_event WHERE detection_state='INTERRUPTED'",Integer.class));
            monitoring.setEnabled(1,false);
            await(()->"STOPPED".equals(monitoring.list().get(0).get("state")),10);
            Instant stopped=Instant.now();
            await(()->pending(folder)==0 && fresh(folder,stopped),10);
            assertEquals(0,jdbc.queryForObject("SELECT COUNT(*) FROM abnormal_event WHERE detection_state='ACTIVE'",Integer.class));
            Files.writeString(folder.resolve("result.json"),json.writeValueAsString(java.util.Map.of("alarmsAfterBrokerReplay",1,"alarmsAfterWorkerRestart",2,"pending",pending(folder),"browserCount",0,"workerRestartTested",true,"applicationAckLossTested",true,"firstEventVisibleMs",firstLatency,"brokerRestartTested","true".equals(System.getenv("P0_MANAGE_TEST_BROKER")),"brokerHardKillTested","true".equals(System.getenv("P0_MANAGE_TEST_BROKER")))));
            System.out.println("P0 MQTT integration evidence: "+folder);
        } finally {
            driver.destroy();if(!driver.waitFor(7,java.util.concurrent.TimeUnit.SECONDS))driver.destroyForcibly();
        }
    }
    private int pending(Path folder){try{return json.readTree(Files.readString(folder.resolve("metrics.json"))).path("pending").asInt(-1);}catch(Exception e){return -1;}}
    private int attempts(Path folder){try{return json.readTree(Files.readString(folder.resolve("metrics.json"))).path("maxAttempts").asInt(-1);}catch(Exception e){return -1;}}
    private boolean controlAfter(Path folder,Instant since){try{return json.readTree(Files.readString(folder.resolve("metrics.json"))).path("lastControlAt").asDouble()*1000>=since.toEpochMilli();}catch(Exception e){return false;}}
    private boolean fresh(Path folder,Instant since){try{return json.readTree(Files.readString(folder.resolve("metrics.json"))).path("at").asDouble()*1000>=since.toEpochMilli();}catch(Exception e){return false;}}
}
