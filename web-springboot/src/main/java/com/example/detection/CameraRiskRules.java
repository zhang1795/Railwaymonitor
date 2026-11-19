package com.example.detection;

import com.example.common.exception.BusinessException;
import com.example.security.CurrentUser;
import com.example.entity.Camera;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import lombok.RequiredArgsConstructor;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.time.*;
import java.util.*;

@Service
@RequiredArgsConstructor
public class CameraRiskRules {
    private final JdbcTemplate jdbc;
    private final ObjectMapper json;
    private final RiskTemplates templates;

    public void addSummaries(List<Camera> records) {
        if(records.isEmpty())return;
        var policies=effective(records.stream().map(Camera::getId).toList());
        records.forEach(camera->camera.setRiskRule(policies.get(camera.getId())));
    }
    public Map<Long,Map<String,Object>> effective(List<Long> ids) {
        var policies=new HashMap<Long,Map<String,Object>>();
        var query=new org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate(jdbc);
        query.query("""
            SELECT c.id,t.enabled,CASE WHEN t.enabled=TRUE THEN s.policy ELSE r.policy END AS policy
            FROM camera c LEFT JOIN camera_risk_rule r ON r.camera_id=c.id
            LEFT JOIN monitoring_task t ON t.camera_id=c.id
            LEFT JOIN session_risk_policy s ON s.session_id=t.session_id
            WHERE c.id IN (:ids) AND c.deleted=0
            """, Map.of("ids",ids),(org.springframework.jdbc.core.RowCallbackHandler)rs->{
                String text=rs.getString("policy");
                if(text==null && rs.getBoolean("enabled")){
                    policies.put(rs.getLong("id"),null);
                }else{
                    var policy=text==null?RiskPolicy.observation():RiskPolicy.snapshot(json,text);
                    policies.put(rs.getLong("id"),policy.values());
                }
            });
        return policies;
    }
    public RiskPolicy current(long camera,boolean lock) {
        var rows=jdbc.queryForList("SELECT policy,revision FROM camera_risk_rule WHERE camera_id=?"+(lock?" FOR UPDATE":""),camera);
        return rows.isEmpty()?RiskPolicy.observation():parse(rows.get(0));
    }
    private RiskPolicy parse(Map<String,Object> row) {
        return RiskPolicy.parse(json,(String)row.get("policy"),((Number)row.get("revision")).longValue());
    }
    private RiskPolicy editable(long camera,long expected) {
        if(jdbc.queryForList("SELECT id FROM camera WHERE id=? AND deleted=0 FOR UPDATE",camera).isEmpty())
            throw new BusinessException(404,"摄像头不存在");
        if(!jdbc.queryForList("SELECT camera_id FROM monitoring_task WHERE camera_id=? AND enabled=TRUE FOR UPDATE",camera).isEmpty())
            throw new BusinessException(409,"请先停用该路后台检测再修改规则");
        var current=current(camera,true);
        if(expected!=current.revision())throw new BusinessException(409,"摄像头规则已变更，请重新加载");
        return current;
    }
    private RiskPolicy store(long camera,RiskPolicy previous,ObjectNode values,RiskPolicy.TemplateRef source,long actor) {
        values.remove("template");
        if(source!=null)values.set("template",json.valueToTree(source));
        var policy=RiskPolicy.parse(json,values.toString(),previous.revision()+1);
        String text=json.valueToTree(policy.values()).toString();
        var now=LocalDateTime.now(ZoneOffset.UTC);
        if(previous.revision()==0)
            jdbc.update("INSERT INTO camera_risk_rule(camera_id,revision,enabled,policy,updated_at) VALUES(?,?,?,?,?)",camera,policy.revision(),policy.enabled(),text,now);
        else jdbc.update("UPDATE camera_risk_rule SET revision=?,enabled=?,policy=?,updated_at=? WHERE camera_id=?",policy.revision(),policy.enabled(),text,now,camera);
        jdbc.update("INSERT INTO camera_risk_revision(camera_id,revision,template_id,policy,actor_id,changed_at) VALUES(?,?,?,?,?,?)",
            camera,policy.revision(),source==null?null:source.id(),text,actor,now);
        return policy;
    }
    @Transactional
    public RiskPolicy save(long camera,ObjectNode body,long actor) {
        var previous=editable(camera,body.path("revision").isIntegralNumber()?body.path("revision").asLong():-1);
        var source=previous.template();
        if(body.has("template")){
            var ref=body.get("template");
            source=ref.isNull()?null:templates.version(ref.path("id").asText(),ref.path("version").asInt()).ref();
        }
        ObjectNode values=body.deepCopy();
        values.remove(List.of("template","overrides"));
        if(source!=null){
            var base=templates.version(source.id(),source.version());
            ObjectNode canonical=json.valueToTree(RiskPolicy.parse(json,values.toString(),0).values());
            ObjectNode oldValues=json.valueToTree(previous.values());
            boolean keepExisting=source.equals(previous.template()) && !body.path("resetOverrides").asBoolean();
            var overrides=values.putArray("overrides");
            for(String field:RiskTemplates.FIELDS){
                boolean retained=keepExisting && previous.overrides().contains(field) && canonical.get(field).equals(oldValues.get(field));
                if(retained || !canonical.get(field).equals(base.parameters().get(field)))overrides.add(field);
            }
        }
        return store(camera,previous,values,source,actor);
    }
    // Called inside the camera registration transaction, after the new id has been allocated.
    public void initialize(long camera) {
        var recommended=templates.recommendation().template();
        if(recommended==null)return;
        var template=templates.version(recommended.id(),recommended.version());
        var observation=RiskPolicy.observation();
        ObjectNode values=json.valueToTree(observation.values());
        values.setAll(template.parameters());
        store(camera,observation,values,template.ref(),CurrentUser.principal().id());
    }

    public record Upgrade(long cameraId,long revision) {}
    public record Impact(long cameraId,String name,long revision,boolean running,int fromVersion,ObjectNode before,ObjectNode after) {}
    private ObjectNode upgraded(RiskPolicy current,RiskTemplates.Published target) {
        ObjectNode result=json.valueToTree(current.values());
        for(String key:RiskTemplates.FIELDS){
            // Keep explicit overrides even when an intermediate release happens to match their values.
            if(!current.overrides().contains(key))result.set(key,target.parameters().get(key));
        }
        return result;
    }
    public List<Impact> impact(RiskTemplates.Published target) {
        var rows=jdbc.queryForList("""
            SELECT c.id,c.name,r.policy,r.revision,t.enabled AS running FROM camera_risk_revision h
            JOIN camera_risk_rule r ON r.camera_id=h.camera_id AND r.revision=h.revision
            JOIN camera c ON c.id=r.camera_id AND c.deleted=0
            LEFT JOIN monitoring_task t ON t.camera_id=c.id WHERE h.template_id=? ORDER BY c.id
            """,target.id());
        var result=new ArrayList<Impact>();
        for(var row:rows){
            var current=parse(row);
            int from=current.template().version();
            if(from>=target.version())continue;
            ObjectNode before=json.valueToTree(current.values());
            result.add(new Impact(((Number)row.get("id")).longValue(),(String)row.get("name"),current.revision(),
                Boolean.TRUE.equals(row.get("running")) || row.get("running") instanceof Number n && n.intValue()!=0,
                from,before.retain(RiskTemplates.FIELDS),upgraded(current,target).retain(RiskTemplates.FIELDS)));
        }
        return result;
    }
    @Transactional
    public void upgrade(String id,int version,List<Upgrade> selected,long actor) {
        if(selected==null || selected.isEmpty() || selected.size()>100 || selected.stream().anyMatch(Objects::isNull) ||
            selected.stream().map(Upgrade::cameraId).distinct().count()!=selected.size())throw new BusinessException(400,"请选择 1 至 100 路不同的摄像头");
        var target=templates.version(id,version);
        for(var item:selected.stream().sorted(Comparator.comparingLong(Upgrade::cameraId)).toList()){
            var current=editable(item.cameraId(),item.revision());
            var ref=current.template();
            if(ref==null || !id.equals(ref.id()) || ref.version()>=version)throw new BusinessException(409,"摄像头的模板版本已变化");
            var values=upgraded(current,target);
            store(item.cameraId(),current,values,target.ref(),actor);
        }
    }
}
