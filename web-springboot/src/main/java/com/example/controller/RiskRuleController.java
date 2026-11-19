package com.example.controller;
import com.example.common.Result;
import com.example.common.exception.BusinessException;
import com.example.detection.CameraRiskRules;
import com.example.security.CurrentUser;
import com.fasterxml.jackson.databind.node.ObjectNode;
import lombok.RequiredArgsConstructor;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;
import java.util.*;

@RestController @RequestMapping("/camera/{camera}/risk-rule") @RequiredArgsConstructor
public class RiskRuleController {
    private final JdbcTemplate jdbc;
    private final CameraRiskRules rules;
    @GetMapping public Result<Map<String,Object>> get(@PathVariable long camera){
        if(jdbc.queryForObject("SELECT COUNT(*) FROM camera WHERE id=? AND deleted=0",Integer.class,camera)==0)throw new BusinessException(404,"摄像头不存在");
        var result=rules.current(camera,false).values();
        var photos=jdbc.queryForList("SELECT v.id,v.alarm_id,v.captured_at FROM alarm_evidence v JOIN abnormal_event a ON a.id=v.alarm_id WHERE a.camera_id=? AND a.deleted=0 ORDER BY v.captured_at DESC LIMIT 1",camera);
        if(!photos.isEmpty()){
            var photo=photos.get(0);result.put("preview",Map.of("url","/api/Abnormal-event/"+photo.get("alarm_id")+"/evidence/"+photo.get("id"),"capturedAt",com.example.detection.UtcValues.value(photo.get("captured_at"))));
        }
        return Result.success(result);
    }
    @GetMapping("/effective")
    public Result<Map<String,Object>> effective(@PathVariable long camera){
        var result=rules.effective(List.of(camera));
        if(!result.containsKey(camera))throw new BusinessException(404,"摄像头不存在");
        return Result.success(result.get(camera));
    }
    @GetMapping("/history") @PreAuthorize("hasRole('ADMIN')")
    public Result<List<Map<String,Object>>> history(@PathVariable long camera){
        return Result.success(jdbc.queryForList("SELECT revision,policy,actor_id,changed_at FROM camera_risk_revision WHERE camera_id=? ORDER BY revision DESC LIMIT 100",camera)
            .stream().map(com.example.detection.UtcValues::map).toList());
    }
    @PutMapping @PreAuthorize("hasRole('ADMIN')")
    public Result<Map<String,Object>> save(@PathVariable long camera,@RequestBody ObjectNode body){
        return Result.success(rules.save(camera,body,CurrentUser.principal().id()).values());
    }
}
