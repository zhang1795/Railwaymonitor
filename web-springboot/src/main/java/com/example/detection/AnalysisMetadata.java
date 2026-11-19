package com.example.detection;

import com.example.common.exception.BusinessException;
import com.fasterxml.jackson.databind.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.MessageDigest;
import java.time.*;
import java.util.*;

public record AnalysisMetadata(String body,String sha,long storageBytes,int frameCount,String model) {
    public static AnalysisMetadata read(Path video,JsonNode registration,ObjectMapper json,Instant start,Instant end)throws Exception{
        Path sidecar=video.resolveSibling(video.getFileName().toString().replace(".mp4",".analysis.json"));
        if(Files.isSymbolicLink(sidecar) || !Files.isRegularFile(sidecar))throw new BusinessException(425,"检测采样元数据尚未可读");
        long size=Files.size(sidecar);FrameResultValidator.require(size>0 && size<=3*1024*1024);
        var envelope=json.readTree(Files.readAllBytes(sidecar));
        for(String key:List.of("id","workerId","cameraId","sessionId","file","sha256","bytes","startedAt","endedAt","kind","clockSource","analysisSha256","analysisBytes"))FrameResultValidator.require(envelope.path("registration").path(key).equals(registration.path(key)));
        String body=envelope.path("analysisJson").asText();byte[] raw=body.getBytes(StandardCharsets.UTF_8);
        FrameResultValidator.require(raw.length>0 && raw.length<=2*1024*1024 && raw.length==registration.path("analysisBytes").asLong());
        String sha=HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(raw));FrameResultValidator.require(sha.equals(registration.path("analysisSha256").asText()));
        var value=json.readTree(raw);FrameResultValidator.identity(value);
        FrameResultValidator.require(value.path("cameraId").asText().equals(registration.path("cameraId").asText()) && value.path("sessionId").asText().equals(registration.path("sessionId").asText()) && value.path("kind").asText().equals("DETECTION_SAMPLES") && value.path("timeSource").asText().equals("DECODER_RECEIVED_AT") && value.path("sourceTimestampVerified").isBoolean() && !value.path("sourceTimestampVerified").asBoolean());
        var frames=value.path("frames");int count=value.path("frameCount").asInt();
        long duration=value.path("durationMs").asLong();double fps=value.path("maxSampleFps").asDouble();
        FrameResultValidator.require(frames.isArray() && count>0 && count<=64 && frames.size()==count && duration>0 && duration<=35_000 && Math.abs(Duration.between(start,end).toMillis()-duration)<=2 && Double.isFinite(fps) && fps>=.1 && fps<=5 && value.path("droppedSamples").asLong()>=0);
        long lastOffset=-1,lastSequence=0;
        for(var frame:frames){
            FrameResultValidator.frame(frame);long offset=frame.path("offsetMs").asLong(-1),sequence=frame.path("frameSeq").asLong();
            FrameResultValidator.require(offset>lastOffset && offset<duration && sequence>lastSequence && Math.abs(Duration.between(start,FrameResultValidator.timestamp(frame,"observedAt")).toMillis()-offset)<=2);
            if(lastOffset==-1)FrameResultValidator.require(offset==0);
            lastOffset=offset;lastSequence=sequence;
        }
        return new AnalysisMetadata(body,sha,size,count,value.path("modelSha256").asText());
    }
}
