package com.example.controller;
import com.example.common.Result;
import com.example.common.exception.BusinessException;
import com.example.detection.NotificationOutbox;
import lombok.RequiredArgsConstructor;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.*;
import java.time.*;
import java.util.*;

@RestController @RequestMapping("/notifications") @PreAuthorize("hasRole('ADMIN')") @RequiredArgsConstructor
public class NotificationController {
    private final NotificationOutbox service;private final JdbcTemplate jdbc;
    @GetMapping public Result<Map<String,Object>> status(){
        var rows=jdbc.queryForList("SELECT id,entity_type,entity_id,channel,status,attempts,error,created_at,updated_at FROM notification_delivery ORDER BY created_at DESC,id DESC LIMIT 100");
        for(var row:rows)com.example.detection.UtcValues.map(row);
        return Result.success(Map.of("configuration",service.state(),"deliveries",rows));
    }
    public record Retry(boolean resultChecked){}
    @PostMapping("/{id}/retry") @Transactional public Result<Void> retry(@PathVariable String id,@RequestBody Retry request){
        if(!id.matches("[a-f0-9]{32}"))throw new BusinessException(400,"无效通知编号");
        var rows=jdbc.queryForList("SELECT status FROM notification_delivery WHERE id=? FOR UPDATE",id);
        if(rows.isEmpty())throw new BusinessException(404,"通知记录不存在");
        String state=(String)rows.get(0).get("status");
        if(!Set.of("FAILED","UNKNOWN","NOT_CONFIGURED").contains(state))throw new BusinessException(409,"当前状态不允许重新发送");
        if(!request.resultChecked())throw new BusinessException(400,"请先核查服务商记录；重新发送可能产生重复通知");
        jdbc.update("UPDATE notification_delivery SET status='PENDING',phase='SEND',attempts=0,provider_id=NULL,error='',next_at=?,updated_at=? WHERE id=?",LocalDateTime.now(ZoneOffset.UTC),LocalDateTime.now(ZoneOffset.UTC),id);
        return Result.success();
    }
}
