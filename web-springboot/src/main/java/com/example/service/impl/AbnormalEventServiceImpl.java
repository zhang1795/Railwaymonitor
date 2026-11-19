package com.example.service.impl;

import cn.hutool.core.bean.BeanUtil;
import cn.hutool.core.util.StrUtil;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.metadata.IPage;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.baomidou.mybatisplus.extension.service.impl.ServiceImpl;
import com.example.common.exception.BusinessException;
import com.example.dto.Abnormal.AbnormalEventCreateDTO;
import com.example.dto.Abnormal.AbnormalEventHandleDTO;
import com.example.dto.Abnormal.AbnormalEventQueryDTO;
import com.example.dto.Abnormal.AbnormalEventUpdateDTO;
import com.example.dto.Abnormal.AbnormalEventVO;
import com.example.entity.Camera;
import com.example.entity.AbnormalEvent;
import com.example.entity.User;
import com.example.mapper.AbnormalEventMapper;
import com.example.service.CameraService;
import com.example.service.AbnormalEventService;
import com.example.service.UserService;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.client.RestTemplate;

import java.time.LocalDateTime;
import com.example.security.CurrentUser;
import java.time.format.DateTimeFormatter;
import java.util.List;

/**
 * 异常事件服务实现类
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class AbnormalEventServiceImpl extends ServiceImpl<AbnormalEventMapper, AbnormalEvent> implements AbnormalEventService {

    private final CameraService cameraService;
    private final UserService userService;
    private final org.springframework.jdbc.core.JdbcTemplate jdbc;

    @Value("${file.server.url}")
    private String fileServerUrl;

    @Override
    @Transactional(rollbackFor = Exception.class)
    public Long createAbnormalEvent(AbnormalEventCreateDTO dto) {
        // 校验摄像头是否存在
        Camera camera = cameraService.getById(dto.getCameraId());
        if (camera == null) {
            throw new BusinessException("摄像头不存在");
        }

        // 创建事件
        AbnormalEvent AbnormalEvent = BeanUtil.copyProperties(dto, AbnormalEvent.class);
        // 设置状态为未处理
        AbnormalEvent.setStatus(0);

        // 保存事件
        save(AbnormalEvent);
        jdbc.update("INSERT IGNORE INTO alarm_notice(alarm_id,kind,bucket,created_at) VALUES(?,'FIRST',0,?)",AbnormalEvent.getId(),java.time.LocalDateTime.now(java.time.ZoneOffset.UTC));

        // FIRST is the durable in-app notification. No simulated SMS delivery.

        return AbnormalEvent.getId();
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void handleAbnormalEvent(AbnormalEventHandleDTO dto) {
        // 查询事件
        AbnormalEvent AbnormalEvent = getById(dto.getId());
        if (AbnormalEvent == null) {
            throw new BusinessException("事件不存在");
        }

        // 校验处理人是否存在
        User handler = userService.getById(CurrentUser.principal().id());
        if (handler == null) {
            throw new BusinessException("处理人不存在");
        }

        // 更新事件信息
        audit(dto.getId(),"HANDLE",2,dto.getHandleResult(),dto.getVersion());
        LocalDateTime now=LocalDateTime.now();
        // Only write human-owned fields. A detection snapshot may have
        // advanced while this request was reading the event and handler.
        boolean updated=lambdaUpdate().eq(com.example.entity.AbnormalEvent::getId,dto.getId())
                .set(com.example.entity.AbnormalEvent::getHandlerId,handler.getId())
                .set(com.example.entity.AbnormalEvent::getHandleTime,now)
                .set(com.example.entity.AbnormalEvent::getHandleResult,dto.getHandleResult())
                .set(com.example.entity.AbnormalEvent::getStatus,2)
                .set(com.example.entity.AbnormalEvent::getUpdateTime,now).update();
        if(!updated)throw new BusinessException(409,"事件已变更或删除，请刷新后重试");
    }

    @Override
    public IPage<AbnormalEventVO> getAbnormalEventPage(AbnormalEventQueryDTO dto) {
        // 构建查询条件
        LambdaQueryWrapper<AbnormalEvent> wrapper = new LambdaQueryWrapper<AbnormalEvent>()
                .eq(dto.getCameraId() != null, AbnormalEvent::getCameraId, dto.getCameraId())
                .like(StrUtil.isNotBlank(dto.getLocation()), AbnormalEvent::getLocation, dto.getLocation())
                .eq(dto.getLevel() != null, AbnormalEvent::getLevel, dto.getLevel())
                .eq(dto.getStatus() != null, AbnormalEvent::getStatus, dto.getStatus())
                .eq(dto.getHandlerId() != null, AbnormalEvent::getHandlerId, dto.getHandlerId())
                .ge(dto.getStartTime() != null, AbnormalEvent::getEventTime, dto.getStartTime())
                .le(dto.getEndTime() != null, AbnormalEvent::getEventTime, dto.getEndTime())
                .orderByDesc(AbnormalEvent::getEventTime).orderByDesc(AbnormalEvent::getId);

        if(Boolean.TRUE.equals(dto.getUnreadOnly()))wrapper.apply("EXISTS (SELECT 1 FROM alarm_notice n WHERE n.alarm_id=abnormal_event.id AND NOT EXISTS (SELECT 1 FROM alarm_notice_receipt nr WHERE nr.notice_id=n.id AND nr.user_id={0}))",CurrentUser.principal().id());

        // 执行分页查询
        IPage<AbnormalEvent> page = page(new Page<>(Math.max(1,dto.getCurrent()), Math.max(1,Math.min(100,dto.getSize()))), wrapper);

        // 转换返回结果
        var converted=enrich(page.getRecords(),false);
        return page.convert(event->converted.get(event.getId()));
    }

    @Override
    public AbnormalEventVO getAbnormalEventById(Long id) {
        // 查询事件
        AbnormalEvent AbnormalEvent = getById(id);
        if (AbnormalEvent == null) {
            throw new BusinessException("事件不存在");
        }

        // 转换返回结果
        return enrich(java.util.List.of(AbnormalEvent),true).get(id);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void updateAbnormalEventStatus(Long id, Integer status, Long version, String result) {
        // 查询事件
        AbnormalEvent AbnormalEvent = getById(id);
        if (AbnormalEvent == null) {
            throw new BusinessException("事件不存在");
        }

        // 更新状态
        if(status==null || status<0 || status>2)throw new BusinessException(400,"状态无效");
        if(status==2 && (result==null || result.isBlank()))throw new BusinessException(400,"完成处理须填写处理结果");
        LocalDateTime now=LocalDateTime.now();
        audit(id,"STATUS",status,result,version);
        var change=lambdaUpdate().eq(com.example.entity.AbnormalEvent::getId,id)
                .set(com.example.entity.AbnormalEvent::getStatus,status)
                .set(com.example.entity.AbnormalEvent::getUpdateTime,now);
        if(status==2)change.set(com.example.entity.AbnormalEvent::getHandlerId,CurrentUser.principal().id())
                .set(com.example.entity.AbnormalEvent::getHandleTime,now)
                .set(com.example.entity.AbnormalEvent::getHandleResult,result);
        if(!change.update())throw new BusinessException(409,"事件已变更或删除，请刷新后重试");
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void updateAbnormalEvent(AbnormalEventUpdateDTO dto) {
        if (dto.getType() != null && !com.example.detection.DetectionIngestService.LABELS.contains(dto.getType())) {
            throw new BusinessException(400,"无效的核验类别");
        }
        // 查询事件
        AbnormalEvent AbnormalEvent = getById(dto.getId());
        if (AbnormalEvent == null) {
            throw new BusinessException("事件不存在");
        }

        // 如果更新了摄像头，校验摄像头是否存在
        if (dto.getCameraId() != null && !dto.getCameraId().equals(AbnormalEvent.getCameraId())) {
            if (AbnormalEvent.getSourceKey() != null) {
                throw new BusinessException(400,"自动告警的来源摄像头不可修改");
            }
            Camera camera = cameraService.getById(dto.getCameraId());
            if (camera == null) {
                throw new BusinessException("摄像头不存在");
            }
        }

        // 更新事件信息
        audit(dto.getId(),"EDIT",null,dto.getDescription(),dto.getVersion());
        boolean updated=lambdaUpdate().eq(com.example.entity.AbnormalEvent::getId,dto.getId())
                .set(dto.getCameraId()!=null,com.example.entity.AbnormalEvent::getCameraId,dto.getCameraId())
                .set(dto.getLocation()!=null,com.example.entity.AbnormalEvent::getLocation,dto.getLocation())
                .set(dto.getLevel()!=null,com.example.entity.AbnormalEvent::getLevel,dto.getLevel())
                .set(dto.getImageUrl()!=null,com.example.entity.AbnormalEvent::getImageUrl,dto.getImageUrl())
                .set(dto.getDescription()!=null,com.example.entity.AbnormalEvent::getDescription,dto.getDescription())
                .set(dto.getType()!=null,com.example.entity.AbnormalEvent::getType,dto.getType())
                .set(com.example.entity.AbnormalEvent::getManualOverride,true)
                .set(com.example.entity.AbnormalEvent::getUpdateTime,LocalDateTime.now()).update();
        if(!updated)throw new BusinessException(409,"事件已变更或删除，请刷新后重试");
    }

    /** Batch enrichment keeps page queries independent of page size. */
    private java.util.Map<Long,AbnormalEventVO> enrich(List<AbnormalEvent> events,boolean detail) {
        var result=new java.util.LinkedHashMap<Long,AbnormalEventVO>();
        if(events.isEmpty())return result;
        for(var event:events){
            var vo=BeanUtil.copyProperties(event,AbnormalEventVO.class);
            vo.setRisk(java.util.Map.of("kind","LEGACY","state","UNKNOWN"));
            result.put(event.getId(),vo);
        }
        Object[] ids=events.stream().map(AbnormalEvent::getId).toArray();
        String in=String.join(",",java.util.Collections.nCopies(ids.length,"?"));
        for(var row:jdbc.queryForList("SELECT a.id,c.name AS camera_name,u.real_name AS handler_name,COALESCE(v.version,0) AS edit_version FROM abnormal_event a LEFT JOIN camera c ON c.id=a.camera_id LEFT JOIN `user` u ON u.id=a.handler_id LEFT JOIN alarm_edit_version v ON v.alarm_id=a.id WHERE a.id IN ("+in+")",ids)){
            var vo=result.get(((Number)row.get("id")).longValue());
            vo.setCameraName((String)row.get("camera_name"));vo.setHandlerName((String)row.get("handler_name"));
            vo.setVersion(((Number)row.get("edit_version")).longValue());
        }
        for(var row:jdbc.queryForList("SELECT alarm_id,kind,state,risk_level,risk_since,missing_since,last_observed,association FROM risk_incident WHERE alarm_id IN ("+in+")",ids))
            result.get(((Number)row.get("alarm_id")).longValue()).setRisk(com.example.detection.UtcValues.map(row));
        if(detail)for(var vo:result.values())vo.setUnreadNoticeIds(jdbc.queryForList("SELECT CAST(n.id AS CHAR) FROM alarm_notice n WHERE n.alarm_id=? AND NOT EXISTS (SELECT 1 FROM alarm_notice_receipt r WHERE r.notice_id=n.id AND r.user_id=?) ORDER BY n.id DESC LIMIT 100",String.class,vo.getId(),CurrentUser.principal().id()));
        return result;
    }

    /**
     * 删除异常事件
     */
    @Override
    @Transactional(rollbackFor = Exception.class)
    public void deleteAbnormalEvent(Long id) {
        // 删除前检查记录是否存在
        AbnormalEvent event = getById(id);
        if (event == null) {
            throw new RuntimeException("异常事件不存在");
        }

        // Soft deletion retains controlled evidence until its retention policy.
        // 执行删除
        removeById(id);
    }

    /**
     * 批量删除异常事件
     */
    @Override
    @Transactional(rollbackFor = Exception.class)
    public void batchDeleteAbnormalEvents(List<Long> ids) {
        // 删除前检查记录是否存在
        List<AbnormalEvent> events = listByIds(ids);
        if (events.size() != ids.size()) {
            throw new RuntimeException("部分异常事件不存在");
        }

        // 执行批量删除
        removeBatchByIds(ids);
    }
    private void audit(long id,String action,Integer status,String result,Long version){
        if(version==null || version<0)throw new BusinessException(400,"缺少有效记录版本，请刷新后重试");
        var rows=jdbc.queryForList("SELECT status FROM abnormal_event WHERE id=? AND deleted=0 FOR UPDATE",id);
        if(rows.isEmpty())throw new BusinessException(409,"事件已删除，请刷新后重试");
        int previous=((Number)rows.get(0).get("status")).intValue();
        jdbc.update("INSERT IGNORE INTO alarm_edit_version(alarm_id,version) VALUES(?,0)",id);
        // A locking read is required under InnoDB REPEATABLE READ: the request
        // may already hold an older snapshot from its initial detail lookup.
        long current=jdbc.queryForObject("SELECT version FROM alarm_edit_version WHERE alarm_id=? FOR UPDATE",Long.class,id);
        if(version!=current)throw new BusinessException(409,"其他人员已修改该记录，请刷新后核对；当前输入尚未保存");
        jdbc.update("UPDATE alarm_edit_version SET version=version+1 WHERE alarm_id=?",id);
        jdbc.update("INSERT INTO alarm_handling_audit(alarm_id,user_id,action,before_status,after_status,result,created_at) VALUES(?,?,?,?,?,?,?)",id,CurrentUser.principal().id(),action,previous,status==null?previous:status,result,java.time.LocalDateTime.now(java.time.ZoneOffset.UTC));
    }

}
