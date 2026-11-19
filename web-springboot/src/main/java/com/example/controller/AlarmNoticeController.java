package com.example.controller;

import com.example.common.Result;
import com.example.common.exception.BusinessException;
import com.example.security.CurrentUser;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import lombok.RequiredArgsConstructor;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.annotation.*;
import org.springframework.web.bind.annotation.*;
import java.time.*;
import java.util.*;

/** Persistent notifications and account receipts, independent of human resolution. */
@RestController @RequestMapping("/alarm-notices") @RequiredArgsConstructor
public class AlarmNoticeController {
    private final JdbcTemplate jdbc;
    public record ReadRequest(@Size(max=100) List<@NotNull @Positive Long> ids,
                              @Size(max=100) List<@NotNull @Positive Long> noticeIds) {}
    @GetMapping @Transactional(readOnly=true,isolation=Isolation.REPEATABLE_READ)
    public Result<Map<String,Object>> unread(@RequestParam(required=false) Long beforeId,@RequestParam(defaultValue="20") int size){
        if(size<1 || size>100 || beforeId!=null && beforeId<1)throw new BusinessException(400,"无效的提醒分页参数");
        long user=CurrentUser.principal().id();
        String unseen=" FROM alarm_notice n JOIN abnormal_event e ON e.id=n.alarm_id WHERE e.deleted=0 AND NOT EXISTS (SELECT 1 FROM alarm_notice_receipt r WHERE r.user_id=? AND r.notice_id=n.id)";
        long count=jdbc.queryForObject("SELECT COUNT(*)"+unseen,Long.class,user);
        var args=new ArrayList<Object>();args.add(user);String boundary="";
        if(beforeId!=null){boundary=" AND n.id<?";args.add(beforeId);}args.add(size+1);
        var rows=jdbc.query("SELECT n.id AS notice_id,n.kind,n.created_at,e.id,e.camera_id,e.location,e.type,e.event_time"+unseen+boundary+" ORDER BY n.id DESC LIMIT ?",(rs,index)->{
            var row=new LinkedHashMap<String,Object>();row.put("id",rs.getString("id"));row.put("noticeId",rs.getString("notice_id"));
            row.put("kind",rs.getString("kind"));row.put("noticeTime",rs.getObject("created_at",LocalDateTime.class).atOffset(ZoneOffset.UTC).toString());
            row.put("cameraId",rs.getString("camera_id"));row.put("location",rs.getString("location"));row.put("type",rs.getString("type"));
            row.put("eventTime",rs.getObject("event_time",LocalDateTime.class));return row;
        },args.toArray());
        boolean more=rows.size()>size;if(more)rows=new ArrayList<>(rows.subList(0,size));
        var result=new LinkedHashMap<String,Object>();result.put("unreadCount",count);result.put("items",rows);
        result.put("nextBeforeId",more?rows.get(rows.size()-1).get("noticeId"):null);return Result.success(result);
    }
    @PostMapping("/read") @Transactional
    public Result<Void> read(@RequestBody @Valid ReadRequest body){
        boolean alarms=body.ids()!=null && !body.ids().isEmpty(),notices=body.noticeIds()!=null && !body.noticeIds().isEmpty();
        if(alarms==notices)throw new BusinessException(400,"请选择明确的告警或提醒 ID，不能同时指定");
        long user=CurrentUser.principal().id();LocalDateTime now=LocalDateTime.now(ZoneOffset.UTC);
        if(alarms){
            // Older clients acknowledge FIRST only, never future/ongoing notifications.
            for(Long alarm:new LinkedHashSet<>(body.ids())){
                jdbc.update("INSERT IGNORE INTO alarm_notice_read(user_id,alarm_id,read_at) SELECT ?,id,? FROM abnormal_event WHERE id=? AND deleted=0",user,now,alarm);
                jdbc.update("INSERT IGNORE INTO alarm_notice_receipt(user_id,notice_id,read_at) SELECT ?,n.id,? FROM alarm_notice n JOIN abnormal_event a ON a.id=n.alarm_id WHERE a.id=? AND a.deleted=0 AND n.kind='FIRST'",user,now,alarm);
            }
        }else for(Long notice:new LinkedHashSet<>(body.noticeIds())){
            jdbc.update("INSERT IGNORE INTO alarm_notice_receipt(user_id,notice_id,read_at) SELECT ?,n.id,? FROM alarm_notice n JOIN abnormal_event a ON a.id=n.alarm_id WHERE n.id=? AND a.deleted=0",user,now,notice);
            jdbc.update("INSERT IGNORE INTO alarm_notice_read(user_id,alarm_id,read_at) SELECT ?,n.alarm_id,? FROM alarm_notice n JOIN abnormal_event a ON a.id=n.alarm_id WHERE n.id=? AND n.kind='FIRST' AND a.deleted=0",user,now,notice);
        }
        return Result.success();
    }
}
