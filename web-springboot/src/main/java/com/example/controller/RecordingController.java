package com.example.controller;

import com.example.common.Result;
import com.example.common.exception.BusinessException;
import com.example.detection.DetectionIngestService;
import com.example.detection.UtcValues;
import com.example.detection.AnalysisMetadata;
import com.fasterxml.jackson.databind.*;
import jakarta.servlet.http.HttpServletRequest;
import lombok.RequiredArgsConstructor;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.*;
import org.springframework.http.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.*;
import java.nio.file.*;
import java.security.MessageDigest;
import java.time.*;
import java.util.*;

/** Single-node/shared-volume source recordings. Only registered closed files are served. */
@RestController @RequiredArgsConstructor
public class RecordingController {
    private final JdbcTemplate jdbc;private final ObjectMapper json;
    private final org.springframework.transaction.support.TransactionTemplate tx;
    private final java.util.concurrent.ExecutorService maintenance=java.util.concurrent.Executors.newSingleThreadExecutor(r->{var thread=new Thread(r,"recording-retention");thread.setDaemon(true);return thread;});
    private final java.util.concurrent.atomic.AtomicBoolean pruning=new java.util.concurrent.atomic.AtomicBoolean();
    @Value("${railway.recording-root:workspace/runtime/full-recordings}") private String storage;
    @Value("${railway.recording-max-bytes:2000000000000}") private long budget;
    @Value("${railway.evidence-max-bytes:1073741824}") private long imageBudget;
    @Value("${railway.recording-retention-days:30}") private int days;
    private Path path(String name){
        if(!name.matches("[A-Za-z0-9_-]{1,150}\\.mp4"))throw new BusinessException(400,"无效录像文件");
        Path root=Path.of(storage).toAbsolutePath().normalize(),file=root.resolve(name);
        if(Files.isSymbolicLink(root) || Files.isSymbolicLink(file))throw new BusinessException(400,"录像路径无效");
        return file;
    }
    private String hash(Path file)throws Exception{
        var digest=MessageDigest.getInstance("SHA-256");byte[] buffer=new byte[65536];
        try(var input=Files.newInputStream(file)){int count;while((count=input.read(buffer))>=0)digest.update(buffer,0,count);}
        return HexFormat.of().formatHex(digest.digest());
    }
    @PostMapping(value="/_evidence/recordings",consumes="application/json") @Transactional
    public ResponseEntity<?> register(HttpServletRequest request)throws Exception{
        byte[] body=request.getInputStream().readNBytes(8193);if(body.length>8192)return ResponseEntity.status(413).body(Result.error(413,"录像元数据过大"));
        JsonNode value;try{value=json.readTree(body);}catch(com.fasterxml.jackson.core.JsonProcessingException invalid){throw new BusinessException(400,"录像JSON无效");}
        if(value==null || !value.isObject())throw new BusinessException(400,"录像JSON无效");String worker=SecurityContextHolder.getContext().getAuthentication().getName();
        String session=value.path("sessionId").asText(),id=value.path("id").asText(),name=value.path("file").asText(),sha=value.path("sha256").asText();
        boolean analysis=value.path("kind").asText().equals("DETECTION_SAMPLES");
        if(!session.matches("[a-f0-9]{32}") || !id.matches("[a-f0-9]{64}") || !sha.matches("[a-f0-9]{64}") || !worker.equals(value.path("workerId").asText()) || !Set.of("FULL_SOURCE","DETECTION_SAMPLES").contains(value.path("kind").asText()) || !value.path("cameraId").asText().matches("[0-9]{1,18}"))throw new BusinessException(400,"录像来源无效");
        long camera=value.path("cameraId").asLong(),size=value.path("bytes").asLong();
        if(!name.startsWith(camera+"_"+session+"_") || !value.path("clockSource").asText().equals(analysis?"INFERENCE_SAMPLES_RECEIVED_AT":"RECORDER_WALL_CLOCK_ESTIMATE"))throw new BusinessException(400,"录像文件与会话不匹配");
        if(size<=0 || size>64*1024*1024)throw new BusinessException(400,"录像片段大小无效");
        var sessions=jdbc.queryForList("SELECT created_at,ended_at,generation FROM monitoring_session WHERE session_id=? AND worker_id=? AND camera_id=?",session,worker,camera);
        if(sessions.isEmpty())throw new BusinessException(403,"录像会话与来源不匹配");
        Instant start,end;
        try{start=OffsetDateTime.parse(value.path("startedAt").asText()).toInstant();end=OffsetDateTime.parse(value.path("endedAt").asText()).toInstant();}
        catch(Exception e){throw new BusinessException(400,"录像时间格式无效");}
        if(end.isBefore(start) || Duration.between(start,end).getSeconds()>600 || end.isAfter(Instant.now().plusSeconds(60)))throw new BusinessException(400,"录像时间范围无效");
        if(days>0 && end.isBefore(Instant.now().minus(Duration.ofDays(days))))throw new BusinessException(410,"录像登记已超过保留期");
        var created=sessions.get(0).get("created_at");Instant sessionStart=(created instanceof java.sql.Timestamp t?t.toLocalDateTime():(LocalDateTime)created).toInstant(ZoneOffset.UTC);
        if(start.isBefore(sessionStart.minusSeconds(60)))throw new BusinessException(400,"录像早于会话");
        var ended=sessions.get(0).get("ended_at");
        if(ended!=null && end.isAfter((ended instanceof java.sql.Timestamp t?t.toLocalDateTime():(LocalDateTime)ended).toInstant(ZoneOffset.UTC).plusSeconds(60)))throw new BusinessException(400,"录像晚于会话结束");
        if(!id.equals(DetectionIngestService.hash(worker+"\n"+session+"\n"+name+"\n"+sha)))throw new BusinessException(400,"录像身份校验失败");
        jdbc.queryForList("SELECT id FROM evidence_storage_lock WHERE id=1 FOR UPDATE");
        var previous=jdbc.queryForList("SELECT * FROM recording_clip WHERE id=?",id);
        if(!previous.isEmpty()){
            var prior=previous.get(0);
            var before=prior.get("started_at");var after=prior.get("ended_at");
            LocalDateTime oldStart=before instanceof java.sql.Timestamp t?t.toLocalDateTime():(LocalDateTime)before;
            LocalDateTime oldEnd=after instanceof java.sql.Timestamp t?t.toLocalDateTime():(LocalDateTime)after;
            if(!sha.equals(prior.get("sha256")) || ((Number)prior.get("bytes")).longValue()!=size || !DetectionIngestService.utc(start).equals(oldStart) || !DetectionIngestService.utc(end).equals(oldEnd))throw new BusinessException(409,"录像来源被复用或元数据已变化");
            var oldAnalysis=jdbc.queryForList("SELECT manifest_sha256 FROM recording_analysis WHERE clip_id=?",id);
            if(analysis!=!oldAnalysis.isEmpty() || analysis && !value.path("analysisSha256").asText().equals(oldAnalysis.get(0).get("manifest_sha256")))throw new BusinessException(409,"检测采样元数据发生变化");
            return ResponseEntity.ok(Result.success(Map.of("registered",true,"expired",previous.get(0).get("expired_at")!=null)));
        }
        Path file=path(name);
        if(!Files.isRegularFile(file))return ResponseEntity.status(425).body(Result.error(425,"共享录像卷尚未可读，请重试"));
        if(Files.size(file)!=size || !hash(file).equals(sha))throw new BusinessException(409,"录像完整性校验失败");
        try(var input=Files.newInputStream(file)){byte[] header=input.readNBytes(12);if(header.length<12 || !new String(header,4,4,java.nio.charset.StandardCharsets.US_ASCII).equals("ftyp"))throw new BusinessException(400,"录像不是MP4容器");}
        AnalysisMetadata metadata=analysis?AnalysisMetadata.read(file,value,json,start,end):null;
        if(metadata!=null && json.readTree(metadata.body()).path("generation").asInt()!=((Number)sessions.get(0).get("generation")).intValue())throw new BusinessException(400,"检测采样代次与会话不匹配");
        long used=jdbc.queryForObject("SELECT COALESCE(SUM(v.bytes+COALESCE(a.manifest_bytes,0)),0) FROM recording_clip v LEFT JOIN recording_analysis a ON a.clip_id=v.id WHERE v.expired_at IS NULL",Long.class);
        if(budget<=imageBudget || used+size+(metadata==null?0:metadata.storageBytes())>budget-imageBudget)return ResponseEntity.status(507).body(Result.error(507,"媒体预算不足，关键事件已保留"));
        jdbc.update("INSERT INTO recording_clip(id,worker_id,camera_id,session_id,file_name,sha256,bytes,started_at,ended_at,registered_at) VALUES(?,?,?,?,?,?,?,?,?,?)",id,worker,camera,session,name,sha,size,DetectionIngestService.utc(start),DetectionIngestService.utc(end),DetectionIngestService.utc(Instant.now()));
        if(metadata!=null)jdbc.update("INSERT INTO recording_analysis(clip_id,model_sha256,frame_count,manifest_sha256,manifest_bytes,manifest_json) VALUES(?,?,?,?,?,?)",id,metadata.model(),metadata.frameCount(),metadata.sha(),metadata.storageBytes(),metadata.body());
        return ResponseEntity.ok(Result.success(Map.of("registered",true)));
    }
    private Map<String,Object> asset(Map<String,Object> row,String url){
        var result=new LinkedHashMap<String,Object>();
        for(String key:List.of("id","camera_id","started_at","ended_at","bytes","sha256"))result.put(key,UtcValues.value(row.get(key)));
        result.put("state",expired(row)?"EXPIRED":Files.isRegularFile(path((String)row.get("file_name")))?"READY":"UNAVAILABLE");
        boolean analysis=row.get("analysis_clip_id")!=null;
        result.put("kind",analysis?"DETECTION_SAMPLES":"FULL_SOURCE");result.put("clockSource",analysis?"INFERENCE_SAMPLES_RECEIVED_AT":"RECORDER_WALL_CLOCK_ESTIMATE");result.put("url",url+row.get("id"));
        if(analysis){result.put("analysisUrl",url+row.get("id")+"/analysis");result.put("frameCount",row.get("frame_count"));result.put("modelSha256",row.get("model_sha256"));}
        return result;
    }
    private boolean expired(Map<String,Object> row){
        if(row.get("expired_at")!=null)return true;
        var end=row.get("ended_at");var value=end instanceof java.sql.Timestamp t?t.toLocalDateTime():(LocalDateTime)end;
        return days>0 && value.toInstant(ZoneOffset.UTC).isBefore(Instant.now().minus(Duration.ofDays(days)));
    }
    public List<Map<String,Object>> forAlarm(long alarm){
        var rows=jdbc.queryForList("SELECT v.*,r.clip_id AS analysis_clip_id,r.frame_count,r.model_sha256 FROM recording_clip v LEFT JOIN recording_analysis r ON r.clip_id=v.id JOIN risk_incident i ON i.camera_id=v.camera_id AND i.session_id=v.session_id JOIN abnormal_event a ON a.id=i.alarm_id WHERE a.id=? AND a.deleted=0 AND v.started_at<=TIMESTAMPADD(SECOND,5,a.last_seen) AND v.ended_at>=TIMESTAMPADD(SECOND,-5,a.first_seen) ORDER BY v.ended_at DESC,v.id DESC LIMIT 100",alarm);
        return rows.stream().map(row->asset(row,"/api/Abnormal-event/"+alarm+"/recordings/")).toList();
    }
    @GetMapping("/camera/{camera}/recordings") public Result<Map<String,Object>> list(@PathVariable long camera,@RequestParam(required=false) String startTime,@RequestParam(required=false) String endTime,@RequestParam(required=false) String beforeEnd,@RequestParam(required=false) String beforeId){
        if(jdbc.queryForObject("SELECT COUNT(*) FROM camera WHERE id=? AND deleted=0",Integer.class,camera)==0)throw new BusinessException(404,"摄像头不存在");
        Instant end,start;try{end=endTime==null?Instant.now():OffsetDateTime.parse(endTime).toInstant();start=startTime==null?end.minus(Duration.ofDays(1)):OffsetDateTime.parse(startTime).toInstant();}catch(Exception e){throw new BusinessException(400,"录像查询时间无效");}
        if(end.isBefore(start) || Duration.between(start,end).compareTo(Duration.ofDays(31))>0)throw new BusinessException(400,"录像查询范围最多31天");
        var args=new ArrayList<Object>(List.of(camera,DetectionIngestService.utc(start),DetectionIngestService.utc(end)));String boundary="";
        if(beforeEnd!=null || beforeId!=null){
            try{if(beforeId==null || !beforeId.matches("[a-f0-9]{64}"))throw new IllegalArgumentException();var cutoff=DetectionIngestService.utc(OffsetDateTime.parse(beforeEnd).toInstant());boundary=" AND (ended_at<? OR (ended_at=? AND id<?))";args.addAll(List.of(cutoff,cutoff,beforeId));}catch(Exception e){throw new BusinessException(400,"录像分页无效");}
        }
        var rows=jdbc.queryForList("SELECT v.*,a.clip_id AS analysis_clip_id,a.frame_count,a.model_sha256 FROM recording_clip v LEFT JOIN recording_analysis a ON a.clip_id=v.id WHERE camera_id=? AND ended_at>=? AND started_at<=?"+boundary+" ORDER BY ended_at DESC,id DESC LIMIT 101",args.toArray());
        boolean more=rows.size()>100;if(more)rows=new ArrayList<>(rows.subList(0,100));
        var result=new LinkedHashMap<String,Object>();result.put("items",rows.stream().map(row->asset(row,"/api/camera/"+camera+"/recordings/")).toList());
        result.put("next",more?Map.of("beforeEnd",UtcValues.value(rows.get(99).get("ended_at")),"beforeId",rows.get(99).get("id")):null);result.put("retentionDays",days);result.put("budgetBytes",budget);
        return Result.success(result);
    }
    private ResponseEntity<Resource> serve(Map<String,Object> row)throws Exception{
        if(expired(row))throw new BusinessException(410,"录像已按保留策略过期");
        Path file=path((String)row.get("file_name"));if(!Files.isRegularFile(file))throw new BusinessException(404,"录像暂不可用");
        if(Files.size(file)!=((Number)row.get("bytes")).longValue() || !hash(file).equals(row.get("sha256")))throw new BusinessException(409,"录像完整性校验失败");
        return ResponseEntity.ok().contentType(MediaType.parseMediaType("video/mp4")).cacheControl(CacheControl.noStore()).header(HttpHeaders.ACCEPT_RANGES,"bytes").contentLength(Files.size(file)).body(new FileSystemResource(file));
    }
    @GetMapping("/camera/{camera}/recordings/{clip}") public ResponseEntity<Resource> read(@PathVariable long camera,@PathVariable String clip)throws Exception{
        var rows=jdbc.queryForList("SELECT v.* FROM recording_clip v JOIN camera c ON c.id=v.camera_id WHERE v.id=? AND v.camera_id=? AND c.deleted=0",clip,camera);
        if(rows.isEmpty())throw new BusinessException(404,"录像不存在");return serve(rows.get(0));
    }
    @GetMapping("/Abnormal-event/{alarm}/recordings/{clip}") public ResponseEntity<Resource> readAlarm(@PathVariable long alarm,@PathVariable String clip)throws Exception{
        if(forAlarm(alarm).stream().noneMatch(row->row.get("id").equals(clip)))throw new BusinessException(404,"录像与事件不匹配");
        return serve(jdbc.queryForMap("SELECT * FROM recording_clip WHERE id=?",clip));
    }
    private ResponseEntity<?> analysis(Map<String,Object> row)throws Exception{
        if(expired(row))throw new BusinessException(410,"检测采样已过期");
        var data=jdbc.queryForList("SELECT manifest_json,manifest_sha256 FROM recording_analysis WHERE clip_id=?",row.get("id"));
        if(data.isEmpty() || data.get(0).get("manifest_json")==null)throw new BusinessException(404,"此录像没有检测采样元数据");
        String body=(String)data.get(0).get("manifest_json");
        if(!DetectionIngestService.hash(body).equals(data.get(0).get("manifest_sha256")))throw new BusinessException(409,"检测元数据完整性校验失败");
        return ResponseEntity.ok().cacheControl(CacheControl.noStore()).body(Result.success(json.readTree(body)));
    }
    @GetMapping("/camera/{camera}/recordings/{clip}/analysis") public ResponseEntity<?> analysisCamera(@PathVariable long camera,@PathVariable String clip)throws Exception{
        var rows=jdbc.queryForList("SELECT v.* FROM recording_clip v JOIN camera c ON c.id=v.camera_id WHERE v.camera_id=? AND v.id=? AND c.deleted=0",camera,clip);
        if(rows.isEmpty())throw new BusinessException(404,"录像不存在");return analysis(rows.get(0));
    }
    @GetMapping("/Abnormal-event/{alarm}/recordings/{clip}/analysis") public ResponseEntity<?> analysisAlarm(@PathVariable long alarm,@PathVariable String clip)throws Exception{
        if(forAlarm(alarm).stream().noneMatch(row->row.get("id").equals(clip)))throw new BusinessException(404,"录像与事件不匹配");
        return analysis(jdbc.queryForMap("SELECT * FROM recording_clip WHERE id=?",clip));
    }
    @Scheduled(initialDelayString="${railway.recording-maintenance-ms:60000}",fixedDelayString="${railway.recording-maintenance-ms:60000}") public void scheduleExpiry(){
        if(!pruning.compareAndSet(false,true))return;
        maintenance.execute(()->{try{tx.executeWithoutResult(status->expire());}finally{pruning.set(false);}});
    }
    @jakarta.annotation.PreDestroy public void close(){maintenance.shutdownNow();}
    @Transactional public void expire(){
        if(days<1)return;
        jdbc.queryForList("SELECT id FROM evidence_storage_lock WHERE id=1 FOR UPDATE");
        var rows=jdbc.queryForList("SELECT id,file_name FROM recording_clip WHERE ended_at<? AND expired_at IS NULL ORDER BY ended_at LIMIT 100",DetectionIngestService.utc(Instant.now().minus(Duration.ofDays(days))));
        for(var row:rows){
            Path file=path((String)row.get("file_name"));
            try{Files.deleteIfExists(file);Files.deleteIfExists(file.resolveSibling(file.getFileName().toString().replace(".mp4",".full-source.json")));Files.deleteIfExists(file.resolveSibling(file.getFileName().toString().replace(".mp4",".analysis.json")));}
            catch(java.io.IOException e){continue;}
            jdbc.update("UPDATE recording_clip SET expired_at=? WHERE id=?",DetectionIngestService.utc(Instant.now()),row.get("id"));
            jdbc.update("UPDATE recording_analysis SET manifest_json=NULL,manifest_bytes=0 WHERE clip_id=?",row.get("id"));
        }
    }
}
