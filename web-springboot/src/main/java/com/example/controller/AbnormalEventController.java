package com.example.controller;

import com.baomidou.mybatisplus.core.metadata.IPage;
import com.example.common.Result;
import com.example.common.exception.BusinessException;
import com.example.dto.Abnormal.*;
import com.example.service.AbnormalEventService;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import org.springframework.security.access.prepost.PreAuthorize;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

/**
 * 异常事件控制器
 */
@Tag(name = "异常事件", description = "异常事件管理相关接口")
@RestController
@RequestMapping("/Abnormal-event")
@RequiredArgsConstructor
public class AbnormalEventController {

    private final AbnormalEventService AbnormalEventService;

    /**
     * 创建异常事件
     */
    @Operation(summary = "创建异常事件", description = "创建新的异常事件记录")
    @PostMapping
    @PreAuthorize("hasRole('ADMIN')")
    public Result<Long> createAbnormalEvent(@RequestBody @Valid AbnormalEventCreateDTO dto) {
        return Result.success(AbnormalEventService.createAbnormalEvent(dto));
    }

    /**
     * 处理异常事件
     */
    @Operation(summary = "处理异常事件", description = "处理异常事件并记录处理结果")
    @PostMapping("/{id}/handle")
    public Result<Void> handleAbnormalEvent(@PathVariable Long id, @RequestBody @Valid AbnormalEventHandleDTO dto) {
        if (!id.equals(dto.getId())) {
            throw new BusinessException("路径ID与请求体ID不一致");
        }
        AbnormalEventService.handleAbnormalEvent(dto);
        return Result.success();
    }

    /**
     * 更新异常事件
     */
    @Operation(summary = "更新异常事件", description = "更新异常事件信息")
    @PutMapping("/{id}")
    @PreAuthorize("hasRole('ADMIN')")
    public Result<Void> updateAbnormalEvent(@PathVariable Long id, @RequestBody @Valid AbnormalEventUpdateDTO dto) {
        if (!id.equals(dto.getId())) {
            throw new BusinessException("路径ID与请求体ID不一致");
        }
        AbnormalEventService.updateAbnormalEvent(dto);
        return Result.success();
    }

    /**
     * 分页查询异常事件列表
     */
    @Operation(summary = "分页查询异常事件", description = "分页查询异常事件列表")
    @GetMapping("/page")
    public Result<IPage<AbnormalEventVO>> getAbnormalEventPage(AbnormalEventQueryDTO dto) {
        return Result.success(AbnormalEventService.getAbnormalEventPage(dto));
    }

    /**
     * 获取异常事件详情
     */
    @Operation(summary = "获取异常事件详情", description = "根据ID获取异常事件详情")
    @GetMapping("/{id}")
    public Result<AbnormalEventVO> getAbnormalEventById(@PathVariable Long id) {
        return Result.success(AbnormalEventService.getAbnormalEventById(id));
    }

    /**
     * 更新异常事件状态
     */
    @Operation(summary = "更新异常事件状态", description = "更新异常事件的处理状态")
    @PutMapping("/{id}/status")
    public Result<Void> updateAbnormalEventStatus(@PathVariable Long id, @RequestBody @Valid StatusChange body) {
        Integer status = body.status();
        if (status == null || status < 0 || status > 2) {
            throw new BusinessException("状态值必须是 0、1 或 2");
        }
        AbnormalEventService.updateAbnormalEventStatus(id, status,body.version(),body.result());
        return Result.success();
    }
    public record StatusChange(@jakarta.validation.constraints.NotNull Integer status,
        @jakarta.validation.constraints.NotNull @jakarta.validation.constraints.Min(0) Long version,
        @jakarta.validation.constraints.Size(max=2000) String result){}

    /**
     * 删除异常事件
     */
    @Operation(summary = "删除异常事件", description = "根据ID删除异常事件")
    @DeleteMapping("/{id}")
    @PreAuthorize("hasRole('ADMIN')")
    public Result<Void> deleteAbnormalEvent(@PathVariable Long id) {
        AbnormalEventService.deleteAbnormalEvent(id);
        return Result.success();
    }

    /**
     * 批量删除异常事件
     */
    @Operation(summary = "批量删除异常事件", description = "批量删除异常事件")
    @DeleteMapping("/batch")
    @PreAuthorize("hasRole('ADMIN')")
    public Result<Void> batchDeleteAbnormalEvents(@RequestBody List<Long> ids) {
        if(ids==null || ids.isEmpty() || ids.size()>100 || ids.stream().anyMatch(id->id==null || id<=0))throw new BusinessException(400,"批量操作限1至100个有效编号");
        ids=new java.util.ArrayList<>(new java.util.LinkedHashSet<>(ids));
        AbnormalEventService.batchDeleteAbnormalEvents(ids);
        return Result.success();
    }
} 
