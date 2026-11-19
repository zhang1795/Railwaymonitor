package com.example.detection;
import java.time.*;
import java.util.*;
/** UTC DATETIME columns must not be serialized as server-local timestamps. */
public final class UtcValues {
    private UtcValues(){}
    public static Object value(Object input){
        if(input instanceof java.sql.Timestamp time)return time.toLocalDateTime().atOffset(ZoneOffset.UTC).toString();
        if(input instanceof LocalDateTime time)return time.atOffset(ZoneOffset.UTC).toString();
        return input;
    }
    public static Map<String,Object> map(Map<String,Object> input){input.replaceAll((key,item)->value(item));return input;}
}
