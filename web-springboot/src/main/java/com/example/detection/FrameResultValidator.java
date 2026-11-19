package com.example.detection;

import com.example.common.exception.BusinessException;
import com.fasterxml.jackson.databind.*;
import java.time.*;
import java.util.*;

/** Bounded display metadata; never used as an alarm-ingestion protocol. */
public final class FrameResultValidator {
    private FrameResultValidator(){}
    public static void require(boolean valid){if(!valid)throw new BusinessException(400,"检测帧元数据无效");}
    public static Instant timestamp(JsonNode value,String key){
        try{return OffsetDateTime.parse(value.path(key).asText()).toInstant();}
        catch(Exception error){throw new BusinessException(400,"检测帧时间无效");}
    }
    public static void identity(JsonNode value){
        require(value!=null && value.isObject());
        require(value.path("version").asInt()==1 && value.path("cameraId").asText().matches("[0-9]{1,18}") && value.path("sessionId").asText().matches("[a-f0-9]{32}") && value.path("generation").canConvertToInt() && value.path("generation").asInt()>0 && value.path("modelSha256").asText().matches("[a-f0-9]{64}"));
        int width=value.path("width").asInt(),height=value.path("height").asInt();
        long source=(long)value.path("sourceWidth").asInt()*value.path("sourceHeight").asInt();
        require(width>=2 && width<=640 && height>=2 && height<=480 && source>0 && source<=16_777_216L);
    }
    private static void unit(JsonNode number){require(number.isNumber() && Double.isFinite(number.asDouble()) && number.asDouble()>=0 && number.asDouble()<=1);}
    private static void point(JsonNode point){require(point.isArray() && point.size()==2);unit(point.get(0));unit(point.get(1));}
    public static void frame(JsonNode value){
        require(value.path("frameSeq").isIntegralNumber() && value.path("frameSeq").asLong()>0 && value.path("sourceFrameSeq").isIntegralNumber() && value.path("sourceFrameSeq").asLong()>=value.path("frameSeq").asLong());
        var observed=timestamp(value,"observedAt");var processed=timestamp(value,"processedAt");
        require(!processed.isBefore(observed) && !processed.isAfter(Instant.now().plusSeconds(5)) && Duration.between(observed,processed).compareTo(Duration.ofMinutes(10))<=0);
        require(Set.of("DECODE_CHECKED","UNVERIFIED").contains(value.path("quality").asText()));
        var objects=value.path("objects");require(objects.isArray() && objects.size()<=64 && value.path("totalObjects").isIntegralNumber() && value.path("totalObjects").asInt()>=objects.size() && value.path("totalObjects").asInt()<=10000 && value.path("truncated").isBoolean());
        var tracks=new HashSet<String>();
        for(var object:objects){
            int cls=object.path("classId").asInt(-1);require(cls>=0 && cls<DetectionIngestService.NAMES.size());
            require(DetectionIngestService.NAMES.get(cls).equals(object.path("className").asText()) && DetectionIngestService.LABELS.get(cls).equals(object.path("label").asText()));
            unit(object.path("confidence"));var box=object.path("bbox");require(box.isArray() && box.size()==4);
            for(var number:box)unit(number);
            require(box.get(2).asDouble()>box.get(0).asDouble() && box.get(3).asDouble()>box.get(1).asDouble());
            var track=object.path("trackId");require(track.isNull() || track.isTextual() && track.asText().matches("[0-9]{1,18}"));
            if(!track.isNull())require(tracks.add(track.asText()));
        }
        if(value.has("trails")){
            var trails=value.path("trails");require(trails.isArray() && trails.size()<=64);
            for(var trail:trails){require(tracks.contains(trail.path("trackId").asText()) && trail.path("points").isArray() && trail.path("points").size()<=30);for(var coordinate:trail.path("points"))point(coordinate);}
        }
    }
}
