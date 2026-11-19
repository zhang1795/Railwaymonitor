package com.example.detection;

import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.eclipse.paho.client.mqttv3.*;
import org.eclipse.paho.client.mqttv3.persist.MqttDefaultFilePersistence;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import javax.net.ssl.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.net.URI;
import java.security.KeyStore;
import java.security.cert.CertificateFactory;
import java.util.concurrent.*;

@Component @Slf4j @RequiredArgsConstructor
public class MqttBridge {
    private final DetectionIngestService ingest;
    private final MonitoringService monitoring;
    private final ObjectMapper mapper;
    @Value("${railway.mqtt.enabled:false}") private boolean enabled;
    @Value("${railway.mqtt.uri:tcp://127.0.0.1:1883}") private String uri;
    @Value("${railway.mqtt.username:}") private String username;
    @Value("${railway.mqtt.password:}") private String password;
    @Value("${railway.mqtt.ca-file:}") private String caFile;
    @Value("${railway.mqtt.allow-local-plaintext:false}") private boolean allowLocal;
    @Value("${railway.mqtt.persistence:workspace/runtime/backend-mqtt}") private String persistence;
    private MqttClient client;
    private volatile boolean subscribed;
    public boolean ready(){return !enabled || client!=null && client.isConnected() && subscribed;}
    public String readinessState(){return !enabled?"DISABLED":ready()?"UP":"DOWN";}
    private final ThreadPoolExecutor executor=new ThreadPoolExecutor(2,2,0,TimeUnit.SECONDS,new ArrayBlockingQueue<>(64),r->{var t=new Thread(r,"mqtt-ingest");t.setDaemon(true);return t;});

    @PostConstruct public void initialize() throws Exception {
        if(!enabled)return;
        URI address=URI.create(uri);
        if(username.isBlank() || password.isBlank())throw new IllegalStateException("MQTT credentials required");
        if(!"railway-backend".equals(username))throw new IllegalStateException("Use the dedicated railway-backend identity");
        if(!"ssl".equals(address.getScheme()) && !(allowLocal && "tcp".equals(address.getScheme()) &&
            java.util.Set.of("127.0.0.1","localhost","::1").contains(address.getHost())))throw new IllegalStateException("MQTT requires TLS or explicit loopback development");
        Files.createDirectories(Path.of(persistence));
        client=new MqttClient(uri,"railway-backend",new MqttDefaultFilePersistence(persistence));
        client.setTimeToWait(2000);
        var options=new MqttConnectOptions();options.setUserName(username);options.setPassword(password.toCharArray());
        options.setCleanSession(false);options.setAutomaticReconnect(true);options.setConnectionTimeout(3);options.setMaxInflight(16);
        if("ssl".equals(address.getScheme()))options.setHttpsHostnameVerificationEnabled(true);
        if("ssl".equals(address.getScheme()) && !caFile.isBlank()) {
            var store=KeyStore.getInstance(KeyStore.getDefaultType());store.load(null);
            try(var stream=Files.newInputStream(Path.of(caFile))) {int i=0;for(var cert:CertificateFactory.getInstance("X.509").generateCertificates(stream))store.setCertificateEntry("ca"+i++,cert);}
            var trust=TrustManagerFactory.getInstance(TrustManagerFactory.getDefaultAlgorithm());trust.init(store);
            var ssl=SSLContext.getInstance("TLS");ssl.init(null,trust.getTrustManagers(),null);options.setSocketFactory(ssl.getSocketFactory());
            options.setHttpsHostnameVerificationEnabled(true);
        }
        client.setCallback(new MqttCallbackExtended(){
            public void connectComplete(boolean reconnect,String server) {subscribed=false;}
            public void connectionLost(Throwable cause){subscribed=false;log.warn("MQTT disconnected; detector outboxes retain pending events");}
            public void deliveryComplete(IMqttDeliveryToken token){}
            public void messageArrived(String topic,MqttMessage message) {
                if(message.getPayload().length>16384){log.warn("Oversized MQTT service message rejected");return;}
                byte[] payload=message.getPayload().clone();
                try{executor.execute(()->consume(topic,new String(payload,StandardCharsets.UTF_8)));}
                catch(RejectedExecutionException e){log.warn("Ingest capacity reached; no application ACK issued");}
            }
        });
        // Initial broker outage must not disable HTTP management. Scheduled
        // reconnect also covers the initial connect-failure case in Paho.
        try{client.connect(options);}catch(MqttException e){log.warn("Initial MQTT connection deferred");}
        connectOptions=options;
    }
    private MqttConnectOptions connectOptions;
    private void consume(String topic,String payload) {
        try {
            String[] parts=topic.split("/");if(parts.length!=4 || !parts[2].matches("[A-Za-z0-9_-]{1,64}"))return;
            if("events".equals(parts[3])) {
                var ack=ingest.receive(parts[2],payload);
                // receive returns only after its transaction has committed.
                publish("railway/v3/"+parts[2]+"/ack",mapper.writeValueAsBytes(ack));
            } else monitoring.status(parts[2],mapper.readTree(payload));
        }catch(Exception e){log.error("Service event deferred; no success acknowledgement",e);}
    }
    private void publish(String topic,byte[] body) throws MqttException {client.publish(topic,body,1,false);}
    @Scheduled(fixedDelayString="${railway.reconcile-ms:5000}") public void reconcile() {
        if(!enabled || client==null)return;
        try {
            if(!client.isConnected()){client.connect(connectOptions);return;}
            // Subscribe outside Paho's callback thread. A timed-out SUBACK is
            // retried by the scheduler instead of leaving a connected backend
            // permanently unable to receive events after broker/session loss.
            if(!subscribed){
                client.subscribe(new String[]{"railway/v3/+/events","railway/v3/+/status"},new int[]{1,1});
                subscribed=client.isConnected();
            }
            for(var command:monitoring.commands())publish("railway/v3/"+command.get("workerId")+"/control",mapper.writeValueAsBytes(command));
        }catch(Exception e){log.warn("Monitoring reconcile deferred: {}",e.toString());}
    }
    @PreDestroy public void close() {
        executor.shutdown();
        try {if(!executor.awaitTermination(5,TimeUnit.SECONDS))executor.shutdownNow();if(client!=null){if(client.isConnected())client.disconnect(1000);client.close();}}
        catch(Exception e){log.warn("MQTT shutdown incomplete",e);}
    }
}
