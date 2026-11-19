package com.example.detection;

import com.example.common.exception.BusinessException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.*;

public record RiskPolicy(boolean enabled,List<Integer> classes,double x1,double y1,double x2,double y2,
                         double confidence,int dwellSeconds,int graceSeconds,int reminderSeconds,
                         int level,int escalateSeconds,long revision,TemplateRef template,List<String> overrides) {
    public record TemplateRef(String id,int version,String name) {}
    public RiskPolicy(boolean enabled,List<Integer> classes,double x1,double y1,double x2,double y2,
                      double confidence,int dwellSeconds,int graceSeconds,int reminderSeconds,int level,int escalateSeconds,long revision) {
        this(enabled,classes,x1,y1,x2,y2,confidence,dwellSeconds,graceSeconds,reminderSeconds,level,escalateSeconds,revision,null,List.of());
    }
    public static RiskPolicy observation(){return new RiskPolicy(false,List.of(),0,0,1,1,.5,2,3,60,1,180,0);}
    public static RiskPolicy snapshot(ObjectMapper json,String text) {
        try {
            JsonNode node=json.readTree(text);
            return parse(json,node,node.path("revision").asLong());
        }catch(java.io.IOException e){throw new IllegalStateException("Invalid stored risk policy",e);}
    }
    public static RiskPolicy parse(ObjectMapper json,String text,long revision) {
        try{return parse(json,json.readTree(text),revision);}
        catch(java.io.IOException e){throw new BusinessException(400,"风险规则格式无效");}
    }
    private static RiskPolicy parse(ObjectMapper json,JsonNode n,long revision) {
        try {
            if(!n.path("enabled").isBoolean())throw new IllegalArgumentException();
            var classes=new ArrayList<Integer>();
            if(!n.path("classes").isArray() || n.path("classes").size()>13)throw new IllegalArgumentException();
            for(var value:n.path("classes")){
                if(!value.isIntegralNumber() || !value.canConvertToInt() || value.asInt()<0 || value.asInt()>12)throw new IllegalArgumentException();
                if(!classes.contains(value.asInt()))classes.add(value.asInt());
            }
            Collections.sort(classes);
            var roi=n.path("roi");if(!roi.isArray() || roi.size()!=4)throw new IllegalArgumentException();
            for(var value:roi)if(!value.isNumber() || !Double.isFinite(value.asDouble()) || value.asDouble()<0 || value.asDouble()>1)throw new IllegalArgumentException();
            double x1=roi.get(0).asDouble(),y1=roi.get(1).asDouble(),x2=roi.get(2).asDouble(),y2=roi.get(3).asDouble();
            if(!n.path("confidence").isNumber())throw new IllegalArgumentException();
            double score=n.path("confidence").asDouble(-1);
            if(x2<=x1 || y2<=y1 || !Double.isFinite(score) || score<0 || score>1 || (n.path("enabled").asBoolean() && classes.isEmpty()))throw new IllegalArgumentException();
            var overrides=new ArrayList<String>();
            for(JsonNode key:n.path("overrides"))if(RiskTemplates.FIELDS.contains(key.asText()))overrides.add(key.asText());
            return new RiskPolicy(n.path("enabled").asBoolean(),List.copyOf(classes),x1,y1,x2,y2,score,
                integer(n,"dwellSeconds",0,60),integer(n,"graceSeconds",1,30),integer(n,"reminderSeconds",10,3600),
                integer(n,"level",1,5),integer(n,"escalateSeconds",0,86400),revision,
                n.hasNonNull("template")?json.treeToValue(n.get("template"),TemplateRef.class):null,List.copyOf(overrides));
        }catch(Exception e){throw new BusinessException(400,"无效风险规则：检查类别、区域、分数与时间范围");}
    }
    private static int integer(JsonNode n,String key,int min,int max){
        var value=n.path(key);if(!value.isIntegralNumber() || !value.canConvertToInt() || value.asLong()<min || value.asLong()>max)throw new IllegalArgumentException();return value.asInt();
    }
    public boolean qualifies(JsonNode event){
        var b=event.path("bbox");double width=event.path("frameWidth").asDouble(),height=event.path("frameHeight").asDouble();
        double footX=(b.get(0).asDouble()+b.get(2).asDouble())/2/width,footY=b.get(3).asDouble()/height;
        return classes.contains(event.path("classId").asInt()) && event.path("confidence").asDouble()>=confidence && footX>=x1 && footX<=x2 && footY>=y1 && footY<=y2;
    }
    public Map<String,Object> values(){
        var n=new LinkedHashMap<String,Object>();n.put("enabled",enabled);n.put("classes",classes);n.put("roi",List.of(x1,y1,x2,y2));
        n.put("confidence",confidence);n.put("dwellSeconds",dwellSeconds);n.put("graceSeconds",graceSeconds);n.put("reminderSeconds",reminderSeconds);
        n.put("level",level);n.put("escalateSeconds",escalateSeconds);n.put("revision",revision);
        if(template!=null){n.put("template",template);n.put("overrides",overrides);}
        return n;
    }
}
