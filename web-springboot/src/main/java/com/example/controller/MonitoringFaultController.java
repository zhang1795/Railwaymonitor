package com.example.controller;
import com.example.common.Result;
import com.example.security.CurrentUser;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import lombok.RequiredArgsConstructor;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.*;
import java.time.*;
import java.util.*;

@RestController @RequestMapping("/monitoring/faults") @RequiredArgsConstructor
public class MonitoringFaultController {
    private final JdbcTemplate jdbc;
    public record Read(@NotEmpty @Size(max=100) List<@NotNull @Positive Long> ids){}
    @GetMapping public Result<Map<String,Object>> faults(){
        long user=CurrentUser.principal().id();
        var rows=jdbc.queryForList("SELECT f.*,c.name AS camera_name,CASE WHEN r.user_id IS NULL THEN FALSE ELSE TRUE END AS is_read FROM monitoring_fault f LEFT JOIN camera c ON c.id=f.camera_id LEFT JOIN monitoring_fault_receipt r ON r.fault_id=f.id AND r.user_id=? WHERE f.recovered_at IS NULL OR r.user_id IS NULL ORDER BY f.id DESC LIMIT 100",user);
        for(var row:rows)com.example.detection.UtcValues.map(row);
        return Result.success(Map.of("items",rows,"openCount",jdbc.queryForObject("SELECT COUNT(*) FROM monitoring_fault WHERE recovered_at IS NULL",Long.class),
            "unreadCount",jdbc.queryForObject("SELECT COUNT(*) FROM monitoring_fault f WHERE NOT EXISTS (SELECT 1 FROM monitoring_fault_receipt r WHERE r.user_id=? AND r.fault_id=f.id)",Long.class,user)));
    }
    @PostMapping("/read") @Transactional public Result<Void> read(@RequestBody @Valid Read body){
        for(Long id:new LinkedHashSet<>(body.ids()))jdbc.update("INSERT IGNORE INTO monitoring_fault_receipt(user_id,fault_id,read_at) SELECT ?,id,? FROM monitoring_fault WHERE id=?",CurrentUser.principal().id(),LocalDateTime.now(ZoneOffset.UTC),id);
        return Result.success();
    }
}
