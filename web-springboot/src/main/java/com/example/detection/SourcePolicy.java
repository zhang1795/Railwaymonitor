package com.example.detection;
import com.example.common.exception.BusinessException;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import java.net.URI;
import java.util.*;

@Component
public class SourcePolicy {
    private final Set<String> hosts;
    public SourcePolicy(@Value("${railway.camera-hosts:127.0.0.1,localhost,::1}") String allowed) {
        hosts=new HashSet<>(Arrays.asList(allowed.split(",")));
    }
    public String validate(String source) {
        try {
            URI uri=URI.create(source);
            if(!Set.of("rtsp","rtsps").contains(uri.getScheme()) || !hosts.contains(uri.getHost()) ||
               uri.getFragment()!=null || source.length()>1000) throw new IllegalArgumentException();
            return source;
        } catch(Exception e) { throw new BusinessException(400,"摄像头流地址不符合服务器允许的协议/主机配置"); }
    }
}
