package com.example.detection;

import com.example.common.exception.BusinessException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import lombok.RequiredArgsConstructor;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import java.time.*;
import java.util.*;

@Service
@RequiredArgsConstructor
public class RiskTemplates {
    private final JdbcTemplate jdbc;
    private final ObjectMapper json;
    static final List<String> FIELDS = List.of("classes","confidence","dwellSeconds","graceSeconds","reminderSeconds","level","escalateSeconds");

    public record Published(String id,int version,String name,ObjectNode parameters,Long actorId,String publishedAt) {
        public RiskPolicy.TemplateRef ref() { return new RiskPolicy.TemplateRef(id,version,name); }
    }
    public record Recommendation(long revision, RiskPolicy.TemplateRef template) {}
    public record Catalog(List<Published> versions, Recommendation recommendation) {}

    private Published published(Map<String,Object> row) {
        try {
            return new Published((String)row.get("template_id"), ((Number)row.get("version_no")).intValue(),
                (String)row.get("name"), (ObjectNode)json.readTree((String)row.get("parameters")),
                (Long)row.get("actor_id"), UtcValues.value(row.get("published_at")).toString());
        } catch(java.io.IOException e) { throw new IllegalStateException("Invalid stored template",e); }
    }
    public Published version(String id,int version) {
        var rows=jdbc.queryForList("SELECT * FROM risk_template_version WHERE template_id=? AND version_no=?",id,version);
        if(rows.isEmpty())throw new BusinessException(404,"指定的模板版本不存在");
        return published(rows.get(0));
    }
    public Recommendation recommendation() {
        var row=jdbc.queryForMap("SELECT d.revision,d.template_id,d.version_no,v.name FROM risk_template_default d LEFT JOIN risk_template_version v ON v.template_id=d.template_id AND v.version_no=d.version_no WHERE d.singleton_id=1");
        var id=(String)row.get("template_id");
        return new Recommendation(((Number)row.get("revision")).longValue(),id==null?null:
            new RiskPolicy.TemplateRef(id,((Number)row.get("version_no")).intValue(),(String)row.get("name")));
    }
    public Catalog catalog() {
        return new Catalog(jdbc.queryForList("SELECT * FROM risk_template_version ORDER BY template_id,version_no DESC")
            .stream().map(this::published).toList(),recommendation());
    }
    public Published publish(String id,int previous,String name,JsonNode parameters,long actor) {
        if(name==null || name.isBlank() || name.strip().length()>80 || parameters==null || !parameters.isObject())
            throw new BusinessException(400,"请填写模板名称和判定参数");
        if(previous<0 || previous==Integer.MAX_VALUE)throw new BusinessException(400,"模板版本无效");
        if(previous>0)version(id,previous);
        ObjectNode candidate=(ObjectNode)json.valueToTree(RiskPolicy.observation().values());
        candidate.put("enabled",true);
        for(String field:FIELDS)candidate.set(field,parameters.path(field));
        RiskPolicy validated=RiskPolicy.parse(json,candidate.toString(),0);
        ObjectNode canonical=json.valueToTree(validated.values());
        canonical.retain(FIELDS);
        try {
            jdbc.update("INSERT INTO risk_template_version(template_id,version_no,name,parameters,actor_id,published_at) VALUES(?,?,?,?,?,?)",
                id,previous+1,name.strip(),canonical.toString(),actor,LocalDateTime.now(ZoneOffset.UTC));
        } catch(DuplicateKeyException e) { throw new BusinessException(409,"模板已有新版本，请重新加载"); }
        return version(id,previous+1);
    }
    public void recommend(long revision,RiskPolicy.TemplateRef target,long actor) {
        if(target!=null)version(target.id(),target.version());
        int changes=jdbc.update("UPDATE risk_template_default SET revision=revision+1,template_id=?,version_no=?,actor_id=?,updated_at=? WHERE singleton_id=1 AND revision=?",
            target==null?null:target.id(),target==null?null:target.version(),actor,LocalDateTime.now(ZoneOffset.UTC),revision);
        if(changes==0)throw new BusinessException(409,"全局默认已变更，请重新加载");
    }
}
