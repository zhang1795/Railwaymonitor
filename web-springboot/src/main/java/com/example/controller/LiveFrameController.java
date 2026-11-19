package com.example.controller;

import com.example.common.Result;
import com.example.common.exception.BusinessException;
import com.example.detection.FrameResultValidator;
import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.node.ObjectNode;
import jakarta.servlet.http.HttpServletRequest;
import lombok.RequiredArgsConstructor;
import org.springframework.http.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.bind.annotation.*;
import javax.imageio.ImageIO;
import java.io.*;
import java.time.*;
import java.util.*;

@RestController @RequiredArgsConstructor
public class LiveFrameController {
    private final JdbcTemplate jdbc;private final ObjectMapper json;
    private final LinkedHashMap<Long,ObjectNode> latest=new LinkedHashMap<>();
    private static final int MAX=512*1024;
    private static final List<String> FIELDS=List.of("version","cameraId","sessionId","generation","frameSeq","sourceFrameSeq","observedAt","processedAt","modelSha256","sourceWidth","sourceHeight","width","height","quality","timeSource","objects","totalObjects","truncated","trails","jpeg");
    @PostMapping(value="/_evidence/live-frame",consumes="application/json")
    public ResponseEntity<?> ingest(HttpServletRequest request)throws Exception{
        byte[] body=request.getInputStream().readNBytes(MAX+1);if(body.length>MAX)return ResponseEntity.status(413).body(Result.error(413,"检测帧过大"));
        JsonNode value;try{value=json.readTree(body);}catch(com.fasterxml.jackson.core.JsonProcessingException invalid){throw new BusinessException(400,"检测帧JSON无效");}FrameResultValidator.identity(value);FrameResultValidator.frame(value);
        String worker=SecurityContextHolder.getContext().getAuthentication().getName();
        if(!worker.equals(value.path("workerId").asText()) || !value.path("timeSource").asText().equals("DECODER_RECEIVED_AT"))throw new BusinessException(400,"检测帧来源无效");
        Instant observed=FrameResultValidator.timestamp(value,"observedAt");
        if(Duration.between(observed,Instant.now()).compareTo(Duration.ofSeconds(30))>0)throw new BusinessException(410,"检测帧已过期");
        long camera=value.path("cameraId").asLong();
        var tasks=jdbc.queryForList("SELECT t.session_id,t.generation,t.enabled,t.state FROM monitoring_task t JOIN camera c ON c.id=t.camera_id WHERE t.camera_id=? AND t.worker_id=? AND c.deleted=0",camera,worker);
        if(tasks.isEmpty())throw new BusinessException(403,"检测帧与任务不匹配");
        var task=tasks.get(0);
        if(!Boolean.TRUE.equals(task.get("enabled")) || !"RUNNING".equals(task.get("state")) || !value.path("sessionId").asText().equals(task.get("session_id")) || value.path("generation").asInt()!=((Number)task.get("generation")).intValue())throw new BusinessException(409,"检测帧会话已失效");
        byte[] jpeg;try{jpeg=Base64.getDecoder().decode(value.path("jpeg").asText());}catch(Exception invalid){throw new BusinessException(400,"检测图像无效");}
        if(jpeg.length<4 || (jpeg[0]&255)!=255 || (jpeg[1]&255)!=216)throw new BusinessException(400,"检测图像格式无效");
        try(var input=ImageIO.createImageInputStream(new ByteArrayInputStream(jpeg))){
            var readers=ImageIO.getImageReaders(input);if(!readers.hasNext())throw new BusinessException(400,"检测图像无法解码");
            var reader=readers.next();try{reader.setInput(input);FrameResultValidator.require(reader.getWidth(0)==value.path("width").asInt() && reader.getHeight(0)==value.path("height").asInt() && reader.getFormatName().equalsIgnoreCase("JPEG"));if(reader.read(0)==null)throw new BusinessException(400,"检测图像无法解码");}finally{reader.dispose();}
        }
        ObjectNode safe=json.createObjectNode();for(String field:FIELDS)if(value.has(field))safe.set(field,value.get(field));
        synchronized(latest){
            var previous=latest.get(camera);
            if(previous==null || !previous.path("sessionId").asText().equals(safe.path("sessionId").asText()) || previous.path("frameSeq").asLong()<safe.path("frameSeq").asLong()){
                latest.remove(camera);latest.put(camera,safe);
                while(latest.size()>9)latest.remove(latest.keySet().iterator().next());
            }
        }
        return ResponseEntity.ok(Result.success(Map.of("accepted",true)));
    }
    @GetMapping("/monitoring/{camera}/frame")
    public ResponseEntity<?> current(@PathVariable long camera,@RequestParam(defaultValue="0") long after,@RequestParam(defaultValue="") String session){
        var tasks=jdbc.queryForList("SELECT t.enabled,t.state,t.session_id FROM camera c LEFT JOIN monitoring_task t ON t.camera_id=c.id WHERE c.id=? AND c.deleted=0",camera);
        if(tasks.isEmpty())throw new BusinessException(404,"摄像头不存在");
        var task=tasks.get(0);ObjectNode value;String state;
        synchronized(latest){value=latest.get(camera);}
        if(!Boolean.TRUE.equals(task.get("enabled")))state="DISABLED";
        else if("STARTING".equals(task.get("state")))state="WAITING";
        else if(!"RUNNING".equals(task.get("state")))state="SOURCE_ERROR";
        else if(value==null || !value.path("sessionId").asText().equals(task.get("session_id")))state="WAITING";
        else if(Duration.between(FrameResultValidator.timestamp(value,"observedAt"),Instant.now()).toMillis()>5000)state="EXPIRED";
        else state="FRESH";
        var result=json.createObjectNode();result.put("state",state);result.put("serverTime",Instant.now().toString());
        if(state.equals("FRESH")){
            result.put("observedAgeMs",Math.max(0,Duration.between(FrameResultValidator.timestamp(value,"observedAt"),Instant.now()).toMillis()));
            boolean unchanged=session.equals(value.path("sessionId").asText()) && after==value.path("frameSeq").asLong();result.put("unchanged",unchanged);
            if(!unchanged)result.set("frame",value);
        }
        return ResponseEntity.ok().cacheControl(CacheControl.noStore()).body(Result.success(result));
    }
}
