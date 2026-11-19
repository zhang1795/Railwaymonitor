package com.example.security;

import com.example.common.Result;
import com.example.common.exception.BusinessException;
import com.example.detection.SourcePolicy;
import com.example.mapper.UserMapper;
import jakarta.servlet.http.HttpServletRequest;
import lombok.RequiredArgsConstructor;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.bind.annotation.*;
import java.security.SecureRandom;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.*;
import static com.example.detection.DetectionIngestService.*;

@RestController @RequiredArgsConstructor
public class PreviewController {
    private final JdbcTemplate jdbc;
    private final UserMapper users;
    private final SourcePolicy sources;
    public record GrantRequest(String grant,Long cameraId){}
    @PostMapping("/preview/grant") public Result<Map<String,String>> create(HttpServletRequest request){
        var user=CurrentUser.principal();byte[] bytes=new byte[32];new SecureRandom().nextBytes(bytes);
        String token=Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);Instant expiry=Instant.now().plusSeconds(180);
        jdbc.update("DELETE FROM preview_grant WHERE expires_at<?",utc(Instant.now()));
        if(jdbc.queryForObject("SELECT COUNT(*) FROM preview_grant WHERE session_id=?",Integer.class,request.getSession().getId())>=10)
            throw new BusinessException(429,"预览连接授权数量达到上限");
        jdbc.update("INSERT INTO preview_grant VALUES(?,?,?,?,?)",hash(token),user.id(),request.getSession().getId(),user.version(),utc(expiry));
        return Result.success(Map.of("grant",token,"expiresAt",expiry.toString()));
    }
    @PostMapping("/preview/grant/renew") public Result<Map<String,String>> renew(@RequestBody GrantRequest body,HttpServletRequest request){
        var user=CurrentUser.principal();Instant expiry=Instant.now().plusSeconds(180);
        if(body.grant()==null || jdbc.update("UPDATE preview_grant SET expires_at=? WHERE token_hash=? AND user_id=? AND session_id=? AND expires_at>?",
            utc(expiry),hash(body.grant()),user.id(),request.getSession().getId(),utc(Instant.now()))!=1)
            throw new BusinessException(401,"预览授权已过期");
        return Result.success(Map.of("expiresAt",expiry.toString()));
    }
    @PostMapping("/_internal/preview/resolve") public Result<Map<String,Object>> resolve(@RequestBody GrantRequest body){
        if(body.grant()==null || !body.grant().matches("[A-Za-z0-9_-]{43}"))throw new BusinessException(401,"无效预览授权");
        var grants=jdbc.queryForList("SELECT * FROM preview_grant WHERE token_hash=? AND expires_at>?",hash(body.grant()),utc(Instant.now()));
        if(grants.isEmpty())throw new BusinessException(401,"预览授权已失效");
        var grant=grants.get(0);var user=users.selectById(((Number)grant.get("user_id")).longValue());
        if(user==null || user.getStatus()!=1 || user.getSecurityVersion()!=((Number)grant.get("security_version")).longValue() || Boolean.TRUE.equals(user.getPasswordChangeRequired()))
            throw new BusinessException(401,"预览身份已失效");
        var result=new LinkedHashMap<String,Object>();result.put("userId",user.getId());
        Object storedExpiry=grant.get("expires_at");
        var expiry=storedExpiry instanceof Timestamp time ? time.toLocalDateTime() : (java.time.LocalDateTime)storedExpiry;
        result.put("expiresAt",expiry.toInstant(java.time.ZoneOffset.UTC).toString());
        if(body.cameraId()!=null){
            var rows=jdbc.queryForList("SELECT rtsp_url FROM camera WHERE id=? AND deleted=0",body.cameraId());
            if(rows.isEmpty())throw new BusinessException(404,"摄像头不存在");
            result.put("videoUrl",sources.validate((String)rows.get(0).get("rtsp_url")));
        }
        return Result.success(result);
    }
}
