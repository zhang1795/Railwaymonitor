package com.example.detection;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

@Service @RequiredArgsConstructor
public class RiskPolicyService {
    private final JdbcTemplate jdbc;private final ObjectMapper json;
    public RiskPolicy capture(String session,long camera){
        var saved=jdbc.queryForList("SELECT policy FROM session_risk_policy WHERE session_id=?",session);
        if(!saved.isEmpty())return RiskPolicy.snapshot(json,(String)saved.get(0).get("policy"));
        var rows=jdbc.queryForList("SELECT policy,revision FROM camera_risk_rule WHERE camera_id=?",camera);
        var policy=rows.isEmpty()?RiskPolicy.observation():RiskPolicy.parse(json,(String)rows.get(0).get("policy"),((Number)rows.get(0).get("revision")).longValue());
        int inserted=jdbc.update("INSERT IGNORE INTO session_risk_policy(session_id,policy) VALUES(?,?)",session,json.valueToTree(policy.values()).toString());
        if(inserted==1)return policy;
        // A concurrent capture committed first. Read its immutable snapshot even under repeatable read.
        String winner=jdbc.queryForObject("SELECT policy FROM session_risk_policy WHERE session_id=? FOR UPDATE",String.class,session);
        return RiskPolicy.snapshot(json,winner);
    }
}
