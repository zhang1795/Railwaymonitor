package com.example.controller;

import com.example.common.Result;
import com.example.common.exception.BusinessException;
import com.example.detection.*;
import com.example.security.CurrentUser;
import com.fasterxml.jackson.databind.JsonNode;
import lombok.RequiredArgsConstructor;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.*;
import java.util.*;

@RestController
@RequestMapping("/risk-templates")
@PreAuthorize("hasRole('ADMIN')")
@RequiredArgsConstructor
public class RiskTemplateController {
    private final RiskTemplates templates;
    private final CameraRiskRules cameras;
    public record Edit(String name,Integer previous,JsonNode parameters) {}
    public record DefaultEdit(Long revision,RiskPolicy.TemplateRef template) {}

    @GetMapping @Transactional(readOnly=true)
    public Result<RiskTemplates.Catalog> list() { return Result.success(templates.catalog()); }

    @PostMapping
    public Result<RiskTemplates.Published> create(@RequestBody Edit edit) {
        return Result.success(templates.publish(UUID.randomUUID().toString(),0,edit.name(),edit.parameters(),CurrentUser.principal().id()));
    }
    @PostMapping("/{id}/versions")
    public Result<RiskTemplates.Published> publish(@PathVariable String id,@RequestBody Edit edit) {
        if(edit.previous()==null || edit.previous()<1)throw new BusinessException(400,"缺少模板基础版本");
        return Result.success(templates.publish(id,edit.previous(),edit.name(),edit.parameters(),CurrentUser.principal().id()));
    }
    @PutMapping("/default")
    public Result<Void> recommend(@RequestBody DefaultEdit edit) {
        if(edit.revision()==null)throw new BusinessException(400,"缺少全局默认版本");
        templates.recommend(edit.revision(),edit.template(),CurrentUser.principal().id());
        return Result.success();
    }
    @GetMapping("/{id}/{version}/impact") @Transactional(readOnly=true)
    public Result<List<CameraRiskRules.Impact>> impact(@PathVariable String id,@PathVariable int version) {
        return Result.success(cameras.impact(templates.version(id,version)));
    }
    @PostMapping("/{id}/{version}/upgrade")
    public Result<Void> upgrade(@PathVariable String id,@PathVariable int version,@RequestBody List<CameraRiskRules.Upgrade> selected) {
        cameras.upgrade(id,version,selected,CurrentUser.principal().id());
        return Result.success();
    }
}
