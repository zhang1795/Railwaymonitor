package com.example.detection;
import com.example.common.Result;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;
import lombok.RequiredArgsConstructor;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;
import java.util.*;

@RestController @RequestMapping("/monitoring") @RequiredArgsConstructor
public class MonitoringController {
    private final MonitoringService service;
    private final org.springframework.jdbc.core.JdbcTemplate jdbc;
    public record Desired(@NotNull Boolean enabled){}
    @GetMapping public Result<List<Map<String,Object>>> list(){return Result.success(service.list());}
    @GetMapping("/rejections") @PreAuthorize("hasRole('ADMIN')")
    public Result<List<Map<String,Object>>> rejections(){
        return Result.success(jdbc.queryForList("SELECT payload_hash,worker_id,event_id,reason,received_at FROM detection_rejection ORDER BY received_at DESC LIMIT 100"));
    }
    @GetMapping("/rejections/{hash}") @PreAuthorize("hasRole('ADMIN')")
    public Result<List<Map<String,Object>>> rejectedPayload(@PathVariable String hash){
        if(!hash.matches("[a-f0-9]{64}"))throw new com.example.common.exception.BusinessException(400,"无效记录标识");
        return Result.success(jdbc.queryForList("SELECT * FROM detection_rejection WHERE payload_hash=?",hash));
    }
    @PutMapping("/{cameraId}") @PreAuthorize("hasRole('ADMIN')")
    public Result<Map<String,Object>> set(@PathVariable long cameraId,@RequestBody @Valid Desired desired){return Result.success(service.setEnabled(cameraId,desired.enabled()));}
}
