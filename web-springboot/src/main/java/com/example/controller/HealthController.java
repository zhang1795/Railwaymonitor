package com.example.controller;
import com.example.detection.MqttBridge;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.bind.annotation.*;
import java.util.*;

@RestController @RequestMapping("/health") @RequiredArgsConstructor
public class HealthController {
    private final JdbcTemplate jdbc;private final MqttBridge mqtt;
    @GetMapping("/live") public Map<String,Object> live(){return Map.of("status","UP","uptimeSeconds",java.lang.management.ManagementFactory.getRuntimeMXBean().getUptime()/1000);}
    @GetMapping("/ready") public ResponseEntity<Map<String,Object>> ready(){
        boolean database;
        try{database=Integer.valueOf(1).equals(jdbc.queryForObject("SELECT 1",Integer.class));}catch(Exception e){database=false;}
        boolean messaging=mqtt.ready();
        return ResponseEntity.status(database && messaging?200:503).body(Map.of("status",database && messaging?"UP":"NOT_READY","database",database?"UP":"DOWN","messaging",mqtt.readinessState()));
    }
}
