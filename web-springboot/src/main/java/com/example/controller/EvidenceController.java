package com.example.controller;

import com.example.common.Result;
import com.example.common.exception.BusinessException;
import com.example.detection.DetectionIngestService;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.http.HttpServletRequest;
import lombok.RequiredArgsConstructor;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.*;
import javax.imageio.ImageIO;
import java.io.*;
import java.nio.file.*;
import java.security.MessageDigest;
import java.time.*;
import java.util.*;

@RestController @RequiredArgsConstructor
public class EvidenceController {
    private final JdbcTemplate jdbc;private final ObjectMapper json;
    private static final int MAX=2*1024*1024;
    @Value("${railway.evidence-root:workspace/runtime/risk-evidence}") private String storage;
    @Value("${railway.evidence-max-bytes:1073741824}") private long quota;
    @Value("${railway.evidence-service-key:}") private String serviceKey;
    private Path root()throws IOException{
        Path path=Path.of(storage).toAbsolutePath().normalize();Files.createDirectories(path);try{Files.setPosixFilePermissions(path,java.nio.file.attribute.PosixFilePermissions.fromString("rwx------"));}catch(UnsupportedOperationException ignored){}return path;
    }
    @PostMapping(value="/_evidence/{eventId}",consumes="image/jpeg") @Transactional
    public ResponseEntity<?> upload(@PathVariable String eventId,HttpServletRequest request)throws Exception{
        if(!eventId.matches("[a-f0-9]{32}"))return ResponseEntity.badRequest().body(Result.error(400,"无效证据来源"));
        if(request.getContentLengthLong()>MAX)return ResponseEntity.status(413).body(Result.error(413,"截图超过2MiB"));
        byte[] body=request.getInputStream().readNBytes(MAX+1);
        if(body.length>MAX)return ResponseEntity.status(413).body(Result.error(413,"截图超过2MiB"));
        String worker=SecurityContextHolder.getContext().getAuthentication().getName();
        var receipts=jdbc.queryForList("SELECT payload,status FROM detection_receipt WHERE worker_id=? AND event_id=?",worker,eventId);
        if(receipts.isEmpty())return ResponseEntity.status(425).body(Result.error(425,"观测尚未入库，请重试"));
        if(!receipts.get(0).get("status").equals("APPLIED"))return ResponseEntity.badRequest().body(Result.error(400,"观测被隔离"));
        var event=json.readTree((String)receipts.get(0).get("payload"));
        if(!event.path("state").asText().equals("ACTIVE"))return ResponseEntity.badRequest().body(Result.error(400,"截图须对应实际匹配观测"));
        String source=DetectionIngestService.hash(worker+"\n"+event.path("cameraId").asText()+"\n"+event.path("sessionId").asText()+"\n"+event.path("trackId").asText());
        long sequence=event.path("sequence").asLong();
        var links=jdbc.queryForList("SELECT l.alarm_id FROM alarm_source_link l JOIN abnormal_event a ON a.id=l.alarm_id WHERE l.source_key=? AND l.first_sequence<=? AND (l.last_sequence IS NULL OR l.last_sequence>=?) AND a.deleted=0",source,sequence,sequence);
        if(links.isEmpty())return ResponseEntity.ok(Result.success(Map.of("stored",false,"reason","no_matching_incident")));
        long alarm=((Number)links.get(0).get("alarm_id")).longValue();
        jdbc.queryForList("SELECT id FROM evidence_storage_lock WHERE id=1 FOR UPDATE");
        var existing=jdbc.queryForList("SELECT sha256 FROM alarm_evidence WHERE worker_id=? AND event_id=?",worker,eventId);
        String digest=HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(body));
        if(!existing.isEmpty()){
            if(!digest.equals(existing.get(0).get("sha256")))return ResponseEntity.status(409).body(Result.error(409,"同一证据来源的内容不一致"));
            return ResponseEntity.ok(Result.success(Map.of("stored",true)));
        }
        if(jdbc.queryForObject("SELECT COUNT(*) FROM alarm_evidence WHERE alarm_id=?",Integer.class,alarm)>=3)return ResponseEntity.ok(Result.success(Map.of("stored",false,"reason","incident_image_limit")));
        if(body.length<4 || (body[0]&255)!=255 || (body[1]&255)!=216)return ResponseEntity.badRequest().body(Result.error(400,"仅接受JPEG截图"));
        try(var input=ImageIO.createImageInputStream(new ByteArrayInputStream(body))){
            var readers=ImageIO.getImageReaders(input);if(!readers.hasNext())throw new BusinessException(400,"无效截图");
            var reader=readers.next();try{reader.setInput(input);long pixels=(long)reader.getWidth(0)*reader.getHeight(0);
                if(pixels>4_194_304L || pixels<=0 || !reader.getFormatName().equalsIgnoreCase("JPEG"))throw new BusinessException(400,"截图尺寸或格式无效");
                if(reader.read(0)==null)throw new BusinessException(400,"截图无法解码");
            }finally{reader.dispose();}
        }catch(IOException | IllegalArgumentException invalid){throw new BusinessException(400,"截图无法解码");}
        Path root=root();
        String id=DetectionIngestService.hash(worker+"\n"+eventId+"\n"+digest),name=id+".jpg";
        Path destination=root.resolve(name);long used;
        try(var paths=Files.list(root)){used=paths.filter(Files::isRegularFile).mapToLong(path->{try{return Files.size(path);}catch(IOException e){throw new UncheckedIOException(e);}}).sum();}
        if(quota<MAX || used+(Files.exists(destination)?0:body.length)>quota)return ResponseEntity.status(507).body(Result.error(507,"证据存储配额不足，关键告警已保留"));
        boolean created=false;
        try{
            Path temp=Files.createTempFile(root,".incoming-",".tmp");
            try{
                try(var channel=java.nio.channels.FileChannel.open(temp,StandardOpenOption.WRITE,StandardOpenOption.TRUNCATE_EXISTING)){
                    var buffer=java.nio.ByteBuffer.wrap(body);while(buffer.hasRemaining())channel.write(buffer);channel.force(true);
                }
                try{Files.createLink(destination,temp);created=true;}
                catch(FileAlreadyExistsException ignored){
                    if(Files.size(destination)!=body.length || !MessageDigest.isEqual(Files.readAllBytes(destination),body))throw new IOException("Evidence file conflict");
                }
                try(var directory=java.nio.channels.FileChannel.open(root,StandardOpenOption.READ)){directory.force(true);}
            }finally{Files.deleteIfExists(temp);}
            jdbc.update("INSERT INTO alarm_evidence VALUES(?,?,?,?,?,?,?,?,?)",id,alarm,worker,eventId,name,digest,body.length,
                DetectionIngestService.utc(OffsetDateTime.parse(event.path("lastSeen").asText()).toInstant()),DetectionIngestService.utc(Instant.now()));
            return ResponseEntity.ok(Result.success(Map.of("stored",true,"id",id)));
        }catch(Exception e){if(created)Files.deleteIfExists(destination);throw e;}
    }
    @GetMapping("/Abnormal-event/{alarm}/evidence/{asset}")
    public ResponseEntity<byte[]> image(@PathVariable long alarm,@PathVariable String asset)throws Exception{
        if(!asset.matches("[a-f0-9]{64}"))throw new BusinessException(404,"截图不存在");
        var rows=jdbc.queryForList("SELECT v.file_name,v.sha256 FROM alarm_evidence v JOIN abnormal_event a ON a.id=v.alarm_id WHERE v.id=? AND v.alarm_id=? AND a.deleted=0",asset,alarm);
        if(rows.isEmpty())throw new BusinessException(404,"截图不存在");
        String name=(String)rows.get(0).get("file_name");if(!name.matches("[a-f0-9]{64}\\.jpg"))throw new BusinessException(404,"截图不可用");
        Path path=root().resolve(name);if(!Files.isRegularFile(path))throw new BusinessException(404,"截图文件不可用");
        byte[] body;try(var input=Files.newInputStream(path)){body=input.readNBytes(MAX+1);}
        if(body.length>MAX || !HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(body)).equals(rows.get(0).get("sha256")))throw new BusinessException(409,"截图完整性校验失败");
        return ResponseEntity.ok().contentType(MediaType.IMAGE_JPEG).cacheControl(CacheControl.noStore()).body(body);
    }
    public Map<String,Object> assets(long alarm)throws Exception{
        var rows=jdbc.queryForList("SELECT id,captured_at,bytes,sha256,file_name FROM alarm_evidence WHERE alarm_id=? ORDER BY captured_at,id",alarm);
        var assets=new ArrayList<Map<String,Object>>();
        for(var row:rows){String id=(String)row.get("id"),name=(String)row.get("file_name");
            boolean present=name.matches("[a-f0-9]{64}\\.jpg") && Files.isRegularFile(root().resolve(name));
            assets.add(Map.of("id",id,"capturedAt",com.example.detection.UtcValues.value(row.get("captured_at")),"bytes",row.get("bytes"),"sha256",row.get("sha256"),"state",present?"READY":"UNAVAILABLE","url","/api/Abnormal-event/"+alarm+"/evidence/"+id));
        }
        return Map.of("configured",serviceKey.length()>=32,"images",assets,"videoState","NOT_UPLOADED");
    }
}
